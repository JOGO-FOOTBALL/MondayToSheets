"""All settings in one place.

Each setting is read from an environment variable first, then from .streamlit/secrets.toml (local only),
then the default below. Secrets have no default.
"""

import json
import os
import tomllib
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # local .env, never committed

_SECRETS_FILE = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"
_file_settings = tomllib.loads(_SECRETS_FILE.read_text(encoding="utf-8-sig")) if _SECRETS_FILE.exists() else {}


def get_setting(key, default=None):
    value = os.environ.get(key, _file_settings.get(key, default))
    if value is None:
        raise RuntimeError(f"Setting '{key}' is missing (environment variable or {_SECRETS_FILE}).")
    return value


# --- monday board to copy ---
MONDAY_BOARD_ID = get_setting("MONDAY_BOARD_ID", "18437648212")  # P8893 | CC | 433 Awards 2026

# --- Google Sheet: only this tab is ever written; other tabs are never touched ---
SPREADSHEET_ID = get_setting("SPREADSHEET_ID", "1tjCpL-27djrMfVj4DTzosXvCWIn9e5VkfqonVEHE_-c")  # 433 Awards 2026 - Approach
SHEET_TAB = get_setting("SHEET_TAB", "Monday")

# --- Schedule: RUN_ONCE=true syncs once and exits (for a scheduled job); otherwise it loops ---
SYNC_INTERVAL_SECONDS = int(get_setting("SYNC_INTERVAL_SECONDS", 600))
RUN_ONCE = str(get_setting("RUN_ONCE", "false")).lower() == "true"

# --- Columns from monday, by their title on the board, in this order ---
# A title that exists twice on the board (e.g. "Publish date") uses the first one.
MONDAY_COLUMNS = [
    "Name",
    "PM status",
    "Publish date",
    "Account",
    "Post Link (My Del.)",
    "Post Link Story (My Del.)",
    "Tag post #",
    "Collab post #",
    "Collab post",
    "Caption",
    "Paid partner",
    "GD Need",
    "Final files [GD]",
    "Brief [GD]",
    "Brief files [GD]",
    "Asset link",
    "Publish note",
    "Latest Item name",
    "SM",
    "PM",
    "GD",
    "Project name",
]

# --- Columns from our database, added after the monday columns, in this order ---
# The post is looked up by the Instagram link in POST_LINK_COLUMN.
# Sheet column -> field in socials_db.fetch_post_metrics.
POST_LINK_COLUMN = "Post Link (My Del.)"
DB_COLUMNS = {
    "Views": "views",
    "Reach": "reach",
    "Interactions": "interactions",  # likes + comments + saved + shares
    "Engagement rate": "engagement_rate",  # interactions / reach
    "Likes": "likes",
    "Comments": "comments",
    "Shares": "shares",
    "Saves": "saved",
    "Reposts": "reposts",
    "Thumbnail": "thumbnail_url_abs",
}
PERCENT_COLUMNS = ["Engagement rate"]

# --- Azure Key Vault with the data science database login (same as Player_relationship) ---
AZURE_VAULT_URL = get_setting("AZURE_VAULT_URL", "https://ds433kv.vault.azure.net/")
DSDB_SECRETS = {
    "host": "DatasciencePsqlServerUrlProd",
    "port": "DatasciencePsqlServerPortProd",
    "dbname": "DatasciencePsqlServerDatabaseProd",
    "user": "DatasciencePsqlServerUsernameProd",
    "password": "DatasciencePsqlServerPasswordProd",
}


# --- Secrets: read when first used ---
def monday_api_token():
    return get_setting("MONDAY_API_TOKEN")


def google_service_account():
    """The service account key: GOOGLE_SERVICE_ACCOUNT_JSON (full JSON), or [gcp_service_account] in secrets.toml."""
    if "gcp_service_account" in _file_settings and "GOOGLE_SERVICE_ACCOUNT_JSON" not in os.environ:
        return dict(_file_settings["gcp_service_account"])
    return json.loads(get_setting("GOOGLE_SERVICE_ACCOUNT_JSON"))


def dsdb_login():
    """Database login from Key Vault. In Azure via the managed identity; locally via AZURE_TENANT_ID,
    AZURE_CLIENT_ID and AZURE_CLIENT_SECRET (environment or .env)."""
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient

    client = SecretClient(AZURE_VAULT_URL, DefaultAzureCredential())
    return {key: client.get_secret(name).value.strip() for key, name in DSDB_SECRETS.items()}
