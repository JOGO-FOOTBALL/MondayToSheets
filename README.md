# MondayToSheets

Copies the monday board [P8893 | CC | 433 Awards 2026](https://433-force.monday.com/boards/18437648212) every
10 minutes into the tab **Monday** of the Google Sheet
[433 Awards 2026 - Approach](https://docs.google.com/spreadsheets/d/1tjCpL-27djrMfVj4DTzosXvCWIn9e5VkfqonVEHE_-c/edit),
and adds Instagram metrics (views, reach, likes, ...) from the data science database for each item with a
**Post Link (My Del.)**.

- Each sync reads the whole board and rewrites the tab: new items appear, changes come through, deleted items
  disappear. Only the values are replaced; formatting stays.
- Only the tab **Monday** is written. Other tabs are never read or changed.
- Read-only on monday and the database.

## Code

| File | What it does |
|---|---|
| `src/main.py` | The sync: board → table → sheet. Runs once (`RUN_ONCE=true`) or in a loop. |
| `src/config.py` | **All settings**: board, sheet, which columns in which order, Key Vault secret names. |
| `src/monday_client.py` | Reads all items of the board (monday GraphQL API). |
| `src/socials_db.py` | Looks up Instagram posts by link in `socials_analytics.instagram_posts` / `instagram_collab_posts`. |
| `src/sheets_writer.py` | Writes the table into the tab. |

To change the columns, edit `MONDAY_COLUMNS` (monday column titles) and `DB_COLUMNS` (database metrics) in
`src/config.py`. Interactions = likes + comments + saves + shares; engagement rate = interactions / reach.

## Deploy (Airflow)

1. **Image:** a push to `main` builds the image and pushes it to ACR as `monday-to-sheets` (`:latest` and
   `:<date>-<sha>`), see `.github/workflows/build-push-image.yml`. Needs the repository secrets `ACR_SERVER`,
   `ACR_USERNAME` and `ACR_PASSWORD`.
2. **Run it every 10 minutes** with the Airflow DAG `dag_monday_to_sheets` (airflow repo): a
   `KubernetesPodOperator` with image `datascienceby433acr.azurecr.io/monday-to-sheets:latest`, command
   `python -m src.main` and schedule `*/10 * * * *`. Each run takes about 30 seconds.
3. **Environment variables** (set by the DAG; no secrets in the DAG itself):

   | Name | Value |
   |---|---|
   | `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` | the Airflow service principal, used to read Key Vault |
   | `AZURE_VAULT_URL` | `https://ds433kv.vault.azure.net/` |
   | `RUN_ONCE` | `true`: sync once and exit, so the Airflow task finishes |

4. **Key Vault secrets** in `ds433kv` (the service principal needs **Key Vault Secrets User** on it):

   | Secret | Value |
   |---|---|
   | `MondayApiToken` | monday personal API token (same as the Music_tool) |
   | `MondayToSheetsGoogleServiceAccount` | full JSON key of `monday-to-sheets@instagram-491416.iam.gserviceaccount.com`, pasted as is |
   | `DatasciencePsqlServer{Url,Port,Database,Username,Password}Prod` | data science database login (same as Player_relationship) |

5. **Network:** outgoing HTTPS to `api.monday.com`, the Google APIs and `ds433kv.vault.azure.net`, and port 5432
   to the dsdb Postgres server (`*.postgres.database.azure.com`). No incoming traffic, no storage.

**Check:** the log shows `Synced 178 items from 'P8893 | CC | 433 Awards 2026' to tab 'Monday'`.
If the database can't be reached, the monday data is still written and only the metric columns stay empty
(the log shows `Could not read the database`).

## Run locally

```bash
cp .env.example .env               # then fill in the AZURE_* values
pip install -r requirements.txt
python -m src.main                 # RUN_ONCE=true in .env: once; false: every 10 minutes
```

With only the `AZURE_*` values in `.env`, all secrets are read from Key Vault, exactly as in Airflow.
To skip Key Vault, set `MONDAY_API_TOKEN` / `GOOGLE_SERVICE_ACCOUNT_JSON` in `.env`, or put them in
`.streamlit/secrets.toml` (the Google key as a `[gcp_service_account]` table). The environment wins over
`secrets.toml`, which wins over Key Vault. `.env` and `.streamlit/` are in `.gitignore` and `.dockerignore`.
