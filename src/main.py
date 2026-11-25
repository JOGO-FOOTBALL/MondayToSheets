"""Copy monday.com boards into Google Sheet tabs, optionally with Instagram metrics from our database.

Each sync reads the board and rewrites its tab, so new items appear, changes come through and deleted
items disappear. In loop mode a tab is only written when something changed. The boards are listed in
config.SYNCS.
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


def build_table(sync, board):
    """Header and rows: the sync's monday columns, then the Instagram metrics if it has a post_link_column."""
    column_ids = board["column_ids"]
    header = list(sync["columns"])
    rows = [[cell_value(item, cid) if cid else "" for cid in column_ids] for item in board["items"]]

    if sync.get("post_link_column"):
        add_instagram_metrics(rows, sync["columns"].index(sync["post_link_column"]))
        header += list(config.INSTAGRAM_METRICS)

    # Never write a table whose values are shifted against the header.
    if any(len(row) != len(header) for row in rows):
        raise RuntimeError(f"{sync['name']}: rows do not match the {len(header)} columns, not writing")
    return header, rows


def add_instagram_metrics(rows, link_index):
    """Append the INSTAGRAM_METRICS to each row, looked up by the post link. Empty when the database fails."""
    try:
        metrics = fetch_post_metrics([row[link_index] for row in rows if row[link_index]])
    except Exception:
        log.exception("Could not read the database; metric columns stay empty this round")
        metrics = {}

    for row in rows:
        post = metrics.get(shortcode(row[link_index]), {})
        row += ["" if post.get(field) is None else post[field] for field in config.INSTAGRAM_METRICS.values()]


def sync_one(sync, previous_hash=None):
    board = fetch_board(sync["board_id"], sync["columns"])
    header, rows = build_table(sync, board)

    table_hash = hashlib.sha256(json.dumps([header, rows], default=str).encode()).hexdigest()
    if table_hash == previous_hash:
        log.info("%s: no changes", sync["name"])
        return table_hash

    write_tab(sync["spreadsheet_id"], sync["tab"], header, rows)
    log.info("%s: synced %d items from '%s' to tab '%s'", sync["name"], len(rows), board["name"], sync["tab"])
    return table_hash


def is_due(sync, last_run, now):
    """Whether a sync should run now, given its every_minutes.

    In loop mode the program remembers when each sync last ran. A scheduled job (RUN_ONCE) remembers
    nothing between runs, so there a sync runs in the first job of each slot on the clock: with
    every_minutes=180 and a job every 10 minutes, that is the job between 00:00 and 00:10 UTC, 03:00, etc.
    """
    every = sync.get("every_minutes", config.SYNC_INTERVAL_SECONDS // 60) * 60
    if config.FORCE or every <= config.SYNC_INTERVAL_SECONDS:
        return True
    if config.RUN_ONCE:
        return now % every < config.SYNC_INTERVAL_SECONDS
    return last_run is None or now - last_run >= every - 60


def sync_all(state):
    """Run every sync that is due; one failing board does not stop the others."""
    now = time.time()
    for sync in config.SYNCS:
        name = sync["name"]
        if config.ONLY and name not in config.ONLY:
            continue
        if not is_due(sync, state.get(name, {}).get("last_run"), now):
            continue
        try:
            table_hash = sync_one(sync, state.get(name, {}).get("hash"))
            state[name] = {"hash": table_hash, "last_run": now}
        except Exception:
            log.exception("%s: sync failed", name)


def main():
    state = {}
    while True:
        sync_all(state)
        if config.RUN_ONCE:
            return
        time.sleep(config.SYNC_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
