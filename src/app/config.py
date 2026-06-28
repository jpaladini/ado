"""App configuration, sourced from environment / Databricks App env + secrets."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Azure DevOps org base URL, e.g. https://dev.azure.com/my-org
    ado_org_url: str = ""
    # Personal Access Token (injected from a Databricks secret in prod)
    ado_pat: str = ""

    @property
    def ado_configured(self) -> bool:
        return bool(self.ado_org_url and self.ado_pat and "CHANGE_ME" not in self.ado_org_url)


settings = Settings()
