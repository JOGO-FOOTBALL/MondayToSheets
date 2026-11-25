# MondayToSheets

Copies monday boards into Google Sheet tabs, so people without monday can see them. Configured in
`SYNCS` in `src/config.py`:

| Board | Sheet → tab | How often |
|---|---|---|
| [P8893 \| CC \| 433 Awards 2026](https://433-force.monday.com/boards/18437648212) | [433 Awards 2026 - Approach](https://docs.google.com/spreadsheets/d/1tjCpL-27djrMfVj4DTzosXvCWIn9e5VkfqonVEHE_-c/edit) → **Monday** | every 10 minutes |
| [Deal Tracker](https://433-force.monday.com/boards/4676673163) | [Outreach](https://docs.google.com/spreadsheets/d/1EOlohxDUypR1hBATPy3KgTdU5NaGWTVDafMAAImiB1k/edit) → **Deal Tracker** | every 3 hours |

For the Awards board, Instagram metrics (views, reach, likes, ...) from the data science database are added for
each item with a **Post Link (My Del.)**.

- Each sync reads the board and rewrites its tab: new items appear, changes come through, deleted items
  disappear. Only the values are replaced; formatting stays.
- Only the configured tabs are written. Other tabs are never read or changed.
- Read-only on monday and the database. One board failing does not stop the others.

## Code

| File | What it does |
|---|---|
| `src/main.py` | The sync: board → table → sheet, for each board that is due. Runs once (`RUN_ONCE=true`) or in a loop. |
| `src/config.py` | **All settings**: the boards (`SYNCS`) with their sheet, tab, columns and frequency; Key Vault secret names. |
| `src/monday_client.py` | Reads the items of a board, only for the configured columns (monday GraphQL API). |
| `src/socials_db.py` | Looks up Instagram posts by link in `socials_analytics.instagram_posts` / `instagram_collab_posts`. |
| `src/sheets_writer.py` | Writes the table into the tab. |

To add a board or change columns, edit `SYNCS` in `src/config.py` (and share a new sheet with the service account
`monday-to-sheets@instagram-491416.iam.gserviceaccount.com` as Editor). `every_minutes` sets how often a board
syncs (default every 10 minutes; 180 = at 00:00, 03:00, ... UTC). The Instagram metrics are in `INSTAGRAM_METRICS`:
interactions = likes + comments + saves + shares; engagement rate = interactions / reach.

## Deploy (Azure)

1. **Image:** a push to `main` builds the image and pushes it to ACR as `monday-to-sheets` (`:latest` and
   `:<date>-<sha>`), see `.github/workflows/build-push-image.yml`. Needs the repository secrets `ACR_SERVER`,
   `ACR_USERNAME` and `ACR_PASSWORD`.
2. **Run it every 10 minutes**, one of:
   - **Container Apps Job (preferred):** trigger *Schedule*, cron `*/10 * * * *`, env `RUN_ONCE=true`.
     Each run takes about 30 seconds.
   - **Container App** with min replicas = 1 and no `RUN_ONCE`: the container loops and syncs every 10 minutes.
3. **Environment variables:**

   | Name | Secret | Value |
   |---|---|---|
   | `MONDAY_API_TOKEN` | yes | monday personal API token (same as the Music_tool) |
   | `GOOGLE_SERVICE_ACCOUNT_JSON` | yes | full JSON key of `monday-to-sheets@instagram-491416.iam.gserviceaccount.com` |
   | `RUN_ONCE` | no | `true` for the Job |

4. **Key Vault access:** give the container's managed identity the role **Key Vault Secrets User** on `ds433kv`
   (same as Player_relationship). It reads `DatasciencePsqlServer{Url,Port,Database,Username,Password}Prod`.
   Without a managed identity, set `AZURE_TENANT_ID`, `AZURE_CLIENT_ID` and `AZURE_CLIENT_SECRET` instead.
5. **Network:** outgoing HTTPS to `api.monday.com`, the Google APIs and `ds433kv.vault.azure.net`, and port 5432
   to the dsdb Postgres server (`*.postgres.database.azure.com`). No incoming traffic, no storage.

**Check:** the log shows lines like `433 Awards 2026: synced 190 items from 'P8893 | CC | 433 Awards 2026' to tab 'Monday'`,
and every 3 hours one for `Deal Tracker` (about 3,300 items, takes about a minute).
If the database can't be reached, the monday data is still written and only the metric columns stay empty
(the log shows `Could not read the database`).

## Run locally

```bash
pip install -r requirements.txt
RUN_ONCE=true FORCE=true python -m src.main   # all boards once, now
RUN_ONCE=true FORCE=true ONLY="433 Awards 2026" python -m src.main   # one board (name from SYNCS)
python -m src.main                            # keeps running, each board on its own schedule
```

Local secrets: `MONDAY_API_TOKEN` and the Google key (as a `[gcp_service_account]` table) in
`.streamlit/secrets.toml`, and the `AZURE_*` values in `.env`. Both files are in `.gitignore` and `.dockerignore`.
