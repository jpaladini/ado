"""App configuration, sourced from environment / Databricks App env + secrets."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Azure DevOps org base URL, e.g. https://dev.azure.com/my-org
    ado_org_url: str = ""
    # Personal Access Token (injected from a Databricks secret in prod)
    ado_pat: str = ""
    # Genie Space ID for NL analytics. Optional env override; when unset, the app
    # tries the ado/genie_space_id secret at runtime (see app/genie.py).
    genie_space_id: str = ""
    # Where the ingest job lands the analytics Delta tables.
    analytics_catalog: str = "workspace"
    analytics_schema: str = "ado_analytics"
    # App-state store (settings, audit log, AI sessions) — Delta via the warehouse.
    store_catalog: str = "workspace"
    store_schema: str = "ado_companion_app"

    @property
    def ado_configured(self) -> bool:
        return bool(self.ado_org_url and self.ado_pat and "CHANGE_ME" not in self.ado_org_url)


settings = Settings()
