"""Ingest Azure DevOps Analytics (OData) into Delta tables for Genie.

Runs as a Databricks job (see resources.jobs.ado_analytics_ingest in
databricks.yml). Reads the same OData feed the app's live dashboard queries,
and lands two tables Genie can answer questions over:

  {catalog}.{schema}.work_items           — current work items (one row each)
  {catalog}.{schema}.work_item_daily      — daily counts by state (trend history)

Secrets: ado/ado_org_url + ado/ado_pat (the same scope the app uses). The
principal running the job needs READ on that scope.
"""
import argparse
import base64
from datetime import date, timedelta

import requests
from pyspark.sql import SparkSession
from pyspark.sql.types import LongType, StringType, StructField, StructType

ODATA_VERSION = "v4.0-preview"
SNAPSHOT_DAYS = 90

spark = SparkSession.builder.getOrCreate()
from pyspark.dbutils import DBUtils  # noqa: E402

dbutils = DBUtils(spark)


def _auth_header(pat: str) -> str:
    return "Basic " + base64.b64encode(f":{pat}".encode()).decode()


def odata_rows(base: str, headers: dict, entity: str, params: dict) -> list[dict]:
    """Fetch all pages of an OData query (follows @odata.nextLink)."""
    url = f"{base}/_odata/{ODATA_VERSION}/{entity}"
    rows: list[dict] = []
    while url:
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        resp.raise_for_status()
        body = resp.json()
        rows.extend(body.get("value", []))
        url = body.get("@odata.nextLink")
        params = {}  # nextLink already carries the query
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="main")
    ap.add_argument("--schema", default="ado_analytics")
    ap.add_argument("--project", default="", help="ADO project name (defaults to all via org root is not supported; set one)")
    args = ap.parse_args()

    org_url = dbutils.secrets.get("ado", "ado_org_url").strip().rstrip("/")
    pat = dbutils.secrets.get("ado", "ado_pat").strip()
    project = args.project.strip()
    if not project:
        try:
            project = dbutils.secrets.get("ado", "ado_project").strip()
        except Exception:
            raise SystemExit(
                "No project set. Pass --project <name> in the job task parameters, "
                "or create the ado/ado_project secret."
            )
    analytics_base = org_url.replace("https://dev.azure.com", "https://analytics.dev.azure.com")
    base = f"{analytics_base}/{project}"
    headers = {"Authorization": _auth_header(pat), "Accept": "application/json"}

    fq = f"{args.catalog}.{args.schema}"
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {fq}")

    # -- current work items ----------------------------------------------------
    items = odata_rows(
        base,
        headers,
        "WorkItems",
        {
            "$select": "WorkItemId,Title,WorkItemType,State,StateCategory,CreatedDate,ChangedDate,CompletedDate",
            "$expand": "AssignedTo($select=UserName)",
        },
    )
    flat = [
        {
            "work_item_id": r.get("WorkItemId"),
            "title": r.get("Title"),
            "type": r.get("WorkItemType"),
            "state": r.get("State"),
            "state_category": r.get("StateCategory"),
            "assigned_to": (r.get("AssignedTo") or {}).get("UserName"),
            "created_date": r.get("CreatedDate"),
            "changed_date": r.get("ChangedDate"),
            "completed_date": r.get("CompletedDate"),
        }
        for r in items
    ]
    # Explicit schema: inference fails when a column (e.g. completed_date) is all-NULL.
    items_schema = StructType(
        [
            StructField("work_item_id", LongType()),
            StructField("title", StringType()),
            StructField("type", StringType()),
            StructField("state", StringType()),
            StructField("state_category", StringType()),
            StructField("assigned_to", StringType()),
            StructField("created_date", StringType()),
            StructField("changed_date", StringType()),
            StructField("completed_date", StringType()),
        ]
    )
    if flat:
        (
            spark.createDataFrame(flat, schema=items_schema)
            .selectExpr(
                "work_item_id",
                "title",
                "type",
                "state",
                "state_category",
                "assigned_to",
                "to_timestamp(created_date) AS created_date",
                "to_timestamp(changed_date) AS changed_date",
                "to_timestamp(completed_date) AS completed_date",
            )
            .write.mode("overwrite")
            .saveAsTable(f"{fq}.work_items")
        )
    print(f"work_items: {len(flat)} rows -> {fq}.work_items")

    # -- daily state counts (trend history) -------------------------------------
    start = (date.today() - timedelta(days=SNAPSHOT_DAYS)).isoformat()
    daily = odata_rows(
        base,
        headers,
        "WorkItemSnapshot",
        {
            "$apply": (
                f"filter(DateValue ge {start}Z)"
                "/groupby((DateValue,State,StateCategory),aggregate($count as Count))"
            )
        },
    )
    flat_daily = [
        {
            "date": str(r.get("DateValue"))[:10],
            "state": r.get("State"),
            "state_category": r.get("StateCategory"),
            "count": int(r.get("Count", 0)),
        }
        for r in daily
    ]
    daily_schema = StructType(
        [
            StructField("date", StringType()),
            StructField("state", StringType()),
            StructField("state_category", StringType()),
            StructField("count", LongType()),
        ]
    )
    if flat_daily:
        (
            spark.createDataFrame(flat_daily, schema=daily_schema)
            .selectExpr("to_date(date) AS date", "state", "state_category", "count")
            .write.mode("overwrite")
            .saveAsTable(f"{fq}.work_item_daily")
        )
    print(f"work_item_daily: {len(flat_daily)} rows -> {fq}.work_item_daily")


if __name__ == "__main__":
    main()
