"""Read the items of a monday.com board through the GraphQL API, only for the columns we need."""

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
    column_values(ids: $columns) {
        id text
        ... on MirrorValue { display_value }
        ... on BoardRelationValue { display_value }
        ... on DependencyValue { display_value }
        ... on FormulaValue { display_value }
    }
"""


def _query(query, variables, attempts=6):
    headers = {"Authorization": config.monday_api_token(), "API-Version": API_VERSION}
    for attempt in range(1, attempts + 1):
        res = requests.post(API_URL, json={"query": query, "variables": variables}, headers=headers, timeout=60)
        body = res.json() if res.headers.get("Content-Type", "").startswith("application/json") else {}
        errors = body.get("errors") or []

        # Rate limits come back as HTTP 429, or as HTTP 200 with an error that says how long to wait.
        wait = max([e.get("extensions", {}).get("retry_in_seconds") or 0 for e in errors] + [0])
        limited = res.status_code == 429 or wait or any("limit" in json.dumps(e).lower() for e in errors)
        if (limited or res.status_code >= 500) and attempt < attempts:
            wait = (wait or 10 * attempt) + 1
            log.warning("monday API limit reached, waiting %ss", wait)
            time.sleep(wait)
            continue
        if res.status_code != 200 or errors:
            raise RuntimeError(f"monday API error (HTTP {res.status_code}): {json.dumps(errors) or res.text}"[:1000])
        return body["data"]


def fetch_board(board_id, titles):
    """The board name, the column id for each of the given titles (same order), and all items in board order."""
    board = _query(
        "query ($ids: [ID!]) { boards(ids: $ids) { name columns { id title } groups { id position } } }",
        {"ids": [board_id]},
    )["boards"]
    if not board:
        raise RuntimeError(f"Board {board_id} not found, or the token has no access to it")
    board = board[0]

    # One id per title, in the same order (a list, so a title listed twice still gets its own column).
    column_ids = []
    for title in titles:
        match = next((c["id"] for c in board["columns"] if c["title"] == title), None)
        if match is None:
            log.warning("Column '%s' is not on board '%s' (renamed?), it stays empty", title, board["name"])
        column_ids.append(match)
    wanted = sorted({cid for cid in column_ids if cid and cid != "name"})

    page = _query(
        f"""query ($ids: [ID!], $columns: [String!], $limit: Int!) {{
              boards(ids: $ids) {{ items_page(limit: $limit) {{ cursor items {{ {_ITEM_FIELDS} }} }} }}
            }}""",
        {"ids": [board_id], "columns": wanted, "limit": PAGE_SIZE},
    )["boards"][0]["items_page"]
    items = page["items"]
    while page["cursor"]:
        page = _query(
            f"""query ($cursor: String!, $columns: [String!], $limit: Int!) {{
                  next_items_page(cursor: $cursor, limit: $limit) {{ cursor items {{ {_ITEM_FIELDS} }} }}
                }}""",
            {"cursor": page["cursor"], "columns": wanted, "limit": PAGE_SIZE},
        )["next_items_page"]
        items += page["items"]

    # Board order: by group position; the API keeps the order within a group.
    group_position = {g["id"]: float(g["position"]) for g in board["groups"]}
    items.sort(key=lambda it: group_position.get((it.get("group") or {}).get("id"), float("inf")))
    return {"name": board["name"], "column_ids": column_ids, "items": items}


def cell_value(item, column_id):
    """The value as shown in monday."""
    if column_id == "name":
        return item["name"]
    for cv in item["column_values"]:
        if cv["id"] == column_id:
            return cv.get("display_value") or cv.get("text") or ""
    return ""
