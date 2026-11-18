"""Read all items of a monday.com board through the GraphQL API."""

import json
import logging
import time

import requests

from src import config

log = logging.getLogger(__name__)

API_URL = "https://api.monday.com/v2"
API_VERSION = "2025-04"
PAGE_SIZE = 100

# For these column types `text` is empty; the visible value is in display_value.
_ITEM_FIELDS = """
    id name group { id }
    column_values {
        id text
        ... on MirrorValue { display_value }
        ... on BoardRelationValue { display_value }
        ... on DependencyValue { display_value }
        ... on FormulaValue { display_value }
    }
"""


def _query(query, variables, attempts=5):
    headers = {"Authorization": config.monday_api_token(), "API-Version": API_VERSION}
    for attempt in range(1, attempts + 1):
        res = requests.post(API_URL, json={"query": query, "variables": variables}, headers=headers, timeout=60)
        body = res.json() if res.headers.get("Content-Type", "").startswith("application/json") else {}
        errors = json.dumps(body.get("errors", ""))
        busy = res.status_code == 429 or res.status_code >= 500 or "complexity" in errors.lower()
        if busy and attempt < attempts:
            log.warning("monday API busy (HTTP %s), retrying", res.status_code)
            time.sleep(10 * attempt)
            continue
        if res.status_code != 200 or body.get("errors"):
            raise RuntimeError(f"monday API error (HTTP {res.status_code}): {errors or res.text}"[:1000])
        return body["data"]


def fetch_board(board_id):
    """Return the board's name, columns (in board order) and all items (in board order)."""
    data = _query(
        f"""query ($ids: [ID!], $limit: Int!) {{
              boards(ids: $ids) {{
                name
                groups {{ id position }}
                columns {{ id title }}
                items_page(limit: $limit) {{ cursor items {{ {_ITEM_FIELDS} }} }}
              }}
            }}""",
        {"ids": [board_id], "limit": PAGE_SIZE},
    )
    if not data["boards"]:
        raise RuntimeError(f"Board {board_id} not found, or the token has no access to it")
    board = data["boards"][0]

    items, cursor = board["items_page"]["items"], board["items_page"]["cursor"]
    while cursor:
        page = _query(
            f"""query ($cursor: String!, $limit: Int!) {{
                  next_items_page(cursor: $cursor, limit: $limit) {{ cursor items {{ {_ITEM_FIELDS} }} }}
                }}""",
            {"cursor": cursor, "limit": PAGE_SIZE},
        )["next_items_page"]
        items += page["items"]
        cursor = page["cursor"]

    # Board order: by group position; the API keeps the order within a group.
    group_position = {g["id"]: float(g["position"]) for g in board["groups"]}
    items.sort(key=lambda it: group_position.get((it.get("group") or {}).get("id"), float("inf")))
    return {"name": board["name"], "columns": board["columns"], "items": items}


def cell_value(item, column_id):
    """The value as shown in monday."""
    for cv in item["column_values"]:
        if cv["id"] == column_id:
            return cv.get("display_value") or cv.get("text") or ""
    return ""
