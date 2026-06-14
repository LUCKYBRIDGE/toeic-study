# TOEIC Study

Personal TOEIC vocabulary study app built around private study materials.

## Published App

The GitHub Pages build publishes only `app/`, so it is playable with the bundled sample data.

For the full personal dataset:

1. On the machine with source materials, run `npm run ingest`.
2. Review `private-data/generated/quality-report.md`.
3. Use `private-data/generated/study-items.approved.json` only after items have full sentence, translation, and grammar approval.
4. Use `private-data/generated/study-items.lexicon-approved.json` only as a word-meaning review source, not as final sentence/grammar study data.
5. On another device, open the published app and use `study-items.json 가져오기` for a reviewed dataset.
6. Export/import progress JSON when moving study records between browsers.

Study progress stays in each browser's storage. There is no login or external database.

## Study Features

- Sentence and short-paragraph vocabulary questions are supported.
- Each answer attempt stores correctness and elapsed time.
- A correct answer can still be marked as uncertain, so guessed words stay in review.
- Words can be manually flagged for review even when they were answered correctly.

## Data Quality Rule

Do not treat raw extracted data as study material.

- `study-items.json`: raw extraction candidates.
- `study-items.lexicon-approved.json`: word and Korean-meaning candidates that passed automatic cleanup.
- `study-items.approved.json`: final study data only. Items belong here only after the English sentence, Korean sentence translation, and grammar note are also checked.

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
