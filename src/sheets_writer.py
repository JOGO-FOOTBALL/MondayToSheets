"""Write the table into one tab of the Google Sheet. Other tabs are never touched."""

from datetime import datetime

import gspread

from src import config


def write_tab(header, rows):
    sheet = gspread.service_account_from_dict(config.google_service_account()).open_by_key(config.SPREADSHEET_ID)
    try:
        tab = sheet.worksheet(config.SHEET_TAB)
    except gspread.WorksheetNotFound:
        tab = sheet.add_worksheet(title=config.SHEET_TAB, rows=len(rows) + 1, cols=len(header))

    data = [header] + rows

    # Only grow the grid, never shrink it: deleting rows or columns would break formulas in
    # other tabs that point at this one. Clearing the values removes items deleted in monday.
    if tab.row_count < len(data) or tab.col_count < len(header):
        tab.resize(rows=max(tab.row_count, len(data)), cols=max(tab.col_count, len(header)))
    tab.clear()  # values only, formatting stays
    tab.update(values=data, range_name="A1", value_input_option="RAW")  # RAW: never read as formulas

    _format_db_columns(sheet, tab, header)
    tab.freeze(rows=1)
    tab.format("1:1", {"textFormat": {"bold": True}})
    tab.update_note("A1", f"Last sync: {datetime.now():%d-%m-%Y %H:%M}")


def _format_db_columns(sheet, tab, header):
    """Percent format for PERCENT_COLUMNS, plain format for the other database columns.

    Resetting matters when the column order changes: otherwise a column that moves into the old
    Engagement rate position keeps the % format (345 would show as 34500%).
    """
    requests = []
    for title in config.DB_COLUMNS:
        col = header.index(title)
        number_format = {"numberFormat": {"type": "PERCENT", "pattern": "0.00%"}} if title in config.PERCENT_COLUMNS else {}
        requests.append({
            "repeatCell": {
                "range": {"sheetId": tab.id, "startRowIndex": 1, "startColumnIndex": col, "endColumnIndex": col + 1},
                "cell": {"userEnteredFormat": number_format},
                "fields": "userEnteredFormat.numberFormat",
            }
        })
    sheet.batch_update({"requests": requests})
