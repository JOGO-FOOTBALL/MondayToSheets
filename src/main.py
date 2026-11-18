"""Copy a monday.com board into a Google Sheet tab, with Instagram metrics from our database.

Each sync reads the whole board and rewrites the tab, so new items appear, changes come through
and deleted items disappear. In loop mode the sheet is only written when something changed.
"""

import hashlib
import json
import logging
import time

from src import config
from src.monday_client import cell_value, fetch_board
from src.sheets_writer import write_tab
from src.socials_db import fetch_post_metrics, shortcode

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("azure").setLevel(logging.WARNING)
log = logging.getLogger("monday-to-sheets")


def build_table(board):
    """Header and rows: the MONDAY_COLUMNS from the board, then the DB_COLUMNS from our database."""
    column_ids = {}
    for title in config.MONDAY_COLUMNS:
        match = next((c["id"] for c in board["columns"] if c["title"] == title), None)
        if match is None:
            log.warning("Column '%s' is not on the board (renamed?), it stays empty", title)
        column_ids[title] = match

    rows = []
    for item in board["items"]:
        rows.append([
            item["name"] if column_id == "name" else cell_value(item, column_id) if column_id else ""
            for column_id in column_ids.values()
        ])

    add_db_columns(rows)
    return config.MONDAY_COLUMNS + list(config.DB_COLUMNS), rows


def add_db_columns(rows):
    """Append the DB_COLUMNS to each row, looked up by the post link. Empty when the database fails."""
    link_index = config.MONDAY_COLUMNS.index(config.POST_LINK_COLUMN)
    try:
        metrics = fetch_post_metrics([row[link_index] for row in rows if row[link_index]])
    except Exception:
        log.exception("Could not read the database; metric columns stay empty this round")
        metrics = {}

    for row in rows:
        post = metrics.get(shortcode(row[link_index]), {})
        row += ["" if post.get(field) is None else post[field] for field in config.DB_COLUMNS.values()]


def sync(previous_hash=None):
    board = fetch_board(config.MONDAY_BOARD_ID)
    header, rows = build_table(board)

    table_hash = hashlib.sha256(json.dumps([header, rows], default=str).encode()).hexdigest()
    if table_hash == previous_hash:
        log.info("No changes")
        return table_hash

    write_tab(header, rows)
    log.info("Synced %d items from '%s' to tab '%s'", len(rows), board["name"], config.SHEET_TAB)
    return table_hash


def main():
    if config.RUN_ONCE:
        sync()
        return

    table_hash = None
    while True:
        try:
            table_hash = sync(table_hash)
        except Exception:
            log.exception("Sync failed, trying again next round")
        time.sleep(config.SYNC_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
