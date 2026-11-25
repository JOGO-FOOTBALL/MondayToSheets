"""All settings in one place.

Each setting is read from an environment variable first, then from .streamlit/secrets.toml (local only),
then the default below. Secrets have no default: they come from the environment, then the local files
(.env / secrets.toml), then Azure Key Vault.
"""

import json
import os
import tomllib
from functools import cache
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


# --- Schedule ---
# The program wakes up every SYNC_INTERVAL_SECONDS (or, with RUN_ONCE=true, is started that often by a scheduled
# job) and runs each sync whose own "every_minutes" has come round. FORCE=true runs all syncs right away.
SYNC_INTERVAL_SECONDS = int(get_setting("SYNC_INTERVAL_SECONDS", 600))
RUN_ONCE = str(get_setting("RUN_ONCE", "false")).lower() == "true"
FORCE = str(get_setting("FORCE", "false")).lower() == "true"
ONLY = [n.strip() for n in str(get_setting("ONLY", "")).split(",") if n.strip()]  # e.g. ONLY="433 Awards 2026"

# --- Instagram metrics from our database, by sheet column -> field in socials_db.fetch_post_metrics ---
INSTAGRAM_METRICS = {
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

# --- What to sync: one block per monday board ---
# board_id:        the number in the monday board URL
# spreadsheet_id:  the ID in the Google Sheet URL (share the sheet with the service account as Editor)
# tab:             the only tab that is written; other tabs are never touched
# columns:         monday column titles, in this order. A title that exists twice on the board uses the first one.
# every_minutes (optional): how often, default every SYNC_INTERVAL_SECONDS. A multiple of 10, e.g. 180 = every 3 hours
#                  (at 00:00, 03:00, 06:00, ... UTC).
# post_link_column (optional): add INSTAGRAM_METRICS after the columns, looked up by the link in this column
SYNCS = [
    {
        "name": "433 Awards 2026",
        "board_id": "18437648212",
        "spreadsheet_id": "1tjCpL-27djrMfVj4DTzosXvCWIn9e5VkfqonVEHE_-c",  # 433 Awards 2026 - Approach
        "tab": "Monday",
        "columns": [
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
        ],
        "post_link_column": "Post Link (My Del.)",
    },
    {
        "name": "Deal Tracker",
        "board_id": "4676673163",
        "spreadsheet_id": "1EOlohxDUypR1hBATPy3KgTdU5NaGWTVDafMAAImiB1k",  # Outreach
        "tab": "Deal Tracker",
        "every_minutes": 180,
        "columns": [
            "Name",
            "Project name",
            "Project no.",
            "LC date",
            "*SM & targets *Import*",
            "SM",
            "My Companies",
            "My contacts",
            "Agency",
            "Industry",
            "Category",
            "Stage",
            "Lead stage",
            "Likelyhood",
            "Deal length*",
            "Deal creation date*",
            "Close Date*",
            "Last Updated",
            "Item ID",
            "Type of deal",
            "Group",
            "Creation date*",
            "Deal closing month",
            "Deal closing Quarter",
            "Team",
            "Event",
            "Type",
            "Account"
        ],
    },
]

# --- Azure Key Vault with the data science database login (same as Player_relationship) ---
AZURE_VAULT_URL = get_setting("AZURE_VAULT_URL", "https://ds433kv.vault.azure.net/")
DSDB_SECRETS = {
    "host": "DatasciencePsqlServerUrlProd",
    "port": "DatasciencePsqlServerPortProd",
    "dbname": "DatasciencePsqlServerDatabaseProd",
    "user": "DatasciencePsqlServerUsernameProd",
    "password": "DatasciencePsqlServerPasswordProd",
}
MONDAY_TOKEN_SECRET = "MondayApiToken"
GOOGLE_SA_SECRET = "MondayToSheetsGoogleServiceAccount"


# --- Secrets: read when first used ---
@cache
def _vault_client():
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient

    return SecretClient(AZURE_VAULT_URL, DefaultAzureCredential())


def _vault_secret(name):
    """One secret from Key Vault, as the service principal in AZURE_TENANT_ID, AZURE_CLIENT_ID and
    AZURE_CLIENT_SECRET (passed in by the Airflow DAG; locally from .env)."""
    return _vault_client().get_secret(name).value.strip()


def monday_api_token():
    """MONDAY_API_TOKEN from the environment, then secrets.toml, then Key Vault."""
    token = os.environ.get("MONDAY_API_TOKEN") or _file_settings.get("MONDAY_API_TOKEN")
    return token or _vault_secret(MONDAY_TOKEN_SECRET)


def google_service_account():
    """The service account key: GOOGLE_SERVICE_ACCOUNT_JSON (full JSON), then [gcp_service_account] in
    secrets.toml, then the full JSON from Key Vault."""
    if os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"):
        return json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    if "gcp_service_account" in _file_settings:
        return dict(_file_settings["gcp_service_account"])
    return json.loads(_vault_secret(GOOGLE_SA_SECRET))


def dsdb_login():
    """Database login from Key Vault."""
    return {key: _vault_secret(name) for key, name in DSDB_SECRETS.items()}
