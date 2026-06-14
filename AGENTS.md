# TOEIC Study Agent Rules

## Project State
- incubating

## Scope
- Personal TOEIC vocabulary and reading-prep study web app.
- Focus first on vocabulary in sentence context, repeated practice, wrong-answer tracking, and weak-word review.

## Source Of Truth
- App code: `app/`
- Ingest scripts: `scripts/`
- Private source materials: `materials/`
- Generated private study data: `private-data/generated/`

## Run And Verification
- Generate study data from private materials: `npm run ingest`
- Run local app server: `npm run start`
- Open: `http://localhost:5174/app/`
- Quick syntax check: `npm run check`

## Change Safety Rules
- Do not commit or publish `materials/`.
- Do not commit or publish `private-data/` because it can contain extracted source text.
- Keep the web app usable without login or cloud storage.
- Store study progress in the browser only unless the user explicitly asks for another storage model.
- Support manual export/import for moving progress between devices.

## Material Adoption
- Put newly collected source files in `materials/inbox/`.
- Run `npm run ingest` after adding materials.
- Keep source files organized under `materials/` by publisher/source family.
- Preserve original file names unless there is a specific cleanup task.

## Migration Note
- This project was created inside an existing workspace and uses the workspace AGENTS.md rules.
- The current private materials predate the app and were organized into `materials/` during initial setup.
