# TOEIC Study

Personal TOEIC vocabulary study app built around private study materials.

## Published App

The GitHub Pages build publishes only `app/`, so it is playable with the bundled sample data.

For the full personal dataset:

1. On the machine with source materials, run `npm run ingest`.
2. Open the app locally and export the loaded study data, or use `private-data/generated/study-items.json`.
3. On another device, open the published app and use `study-items.json 가져오기`.
4. Export/import progress JSON when moving study records between browsers.

Study progress stays in each browser's storage. There is no login or external database.

## Structure

- `materials/`: original PDFs, MP3s, and documents. Keep private.
- `materials/inbox/`: drop new materials here before ingestion.
- `private-data/generated/`: extracted local study data. Keep private.
- `app/`: static web app.
- `scripts/`: local processing scripts.

## Workflow

1. Add source materials under `materials/inbox/` or an existing source folder.
2. Run `npm run ingest`.
3. Run `npm run start`.
4. Open `http://localhost:5174/app/`.
5. Use export/import in the app when moving progress or data to another device.

The app uses browser storage for study progress. There is no account system or cloud database.
