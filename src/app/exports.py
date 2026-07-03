"""Artifact exports. Today: the Reports tab's flow metrics as an .xlsx workbook.

openpyxl only (pure Python — safe on the Databricks Apps runtime). PDF export
is deliberately deferred: weasyprint needs system cairo/pango, which the Apps
container may not provide; verify before adding it.

Every duration in the workbook is 5-day-workweek business days, matching the
tab and the copilot — one unit everywhere.
"""
from datetime import datetime, timezone
from io import BytesIO
from typing import Any


def _sheet(wb, title: str, headers: list[str], rows: list[list[Any]], widths: list[int]) -> None:
    from openpyxl.styles import Font

    ws = wb.create_sheet(title)
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append(r)
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
    ws.freeze_panes = "A2"


def _date_sk(sk: Any) -> str:
    s = str(sk)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else s


def reports_workbook(project: str, p: dict[str, Any]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()

    # -- Summary -----------------------------------------------------------------
    ws = wb.active
    ws.title = "Summary"
    k = p["kpis"]
    f = p.get("filters", {})
    rows = [
        ("Project", project),
        ("Range", p["range"]),
        ("Generated (UTC)", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")),
        ("Duration unit", "business days (Mon–Fri)"),
        ("Type filter", ", ".join(f.get("types", [])) or "all"),
        ("Assignee filter", ", ".join(f.get("assignees", [])) or "all"),
        (),
        ("Completed", k["throughput"]),
        ("Created", k["created"]),
        ("Net flow (created − completed)", k["netFlow"]),
        ("WIP now", k["wip"]),
        ("Cycle time p50 (bdays)", k["cycleP50"]),
        ("Cycle time p85 (bdays)", k["cycleP85"]),
        ("Oldest WIP (bdays)", k["oldestWipDays"]),
    ]
    for r in rows:
        ws.append(r)
    for row in ws.iter_rows(min_col=1, max_col=1):
        row[0].font = Font(bold=True)
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 24

    # -- Created vs completed ------------------------------------------------------
    by_date: dict[str, list[int]] = {}
    for r in p["createdPerDay"]:
        by_date.setdefault(_date_sk(r["dateSK"]), [0, 0])[0] = r["count"]
    for r in p["completedPerDay"]:
        by_date.setdefault(_date_sk(r["dateSK"]), [0, 0])[1] = r["count"]
    _sheet(
        wb, "Created vs completed",
        ["Date", "Created", "Completed"],
        [[d, c[0], c[1]] for d, c in sorted(by_date.items())],
        [14, 10, 12],
    )

    # -- Cycle times ---------------------------------------------------------------
    _sheet(
        wb, "Cycle times",
        ["ID", "Title", "Type", "Closed", "Cycle (bdays)", "Lead (bdays)"],
        [[i["id"], i["title"], i["type"], i["closedDate"], i["cycleBdays"], i["leadBdays"]]
         for i in p["cycleItems"]],
        [8, 50, 12, 12, 14, 14],
    )

    # -- Open items (aging WIP) ------------------------------------------------------
    _sheet(
        wb, "Open items",
        ["ID", "Title", "Type", "State", "Category", "Assignee", "Age (bdays)"],
        [[i["id"], i["title"], i["type"], i["state"], i["category"],
          i.get("assignee") or "Unassigned", i["ageBdays"]]
         for i in sorted(p["openItems"], key=lambda x: -x["ageBdays"])],
        [8, 50, 12, 14, 12, 22, 12],
    )

    # -- Cumulative flow --------------------------------------------------------------
    _sheet(
        wb, "Cumulative flow",
        ["Date", "State category", "Open items"],
        [[r["date"], r["category"], r["count"]] for r in p["cfd"]],
        [14, 16, 12],
    )

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
