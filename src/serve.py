"""Launcher for the Databricks App.

Databricks injects the port to bind via the DATABRICKS_APP_PORT env var.
Locally it defaults to 8000.
"""
import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("DATABRICKS_APP_PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")
