# Complaint Compass (PS-19)
Goal: top 10 recurring complaint issues, deduplicated across channels, ranked by reach, severity and recency, filterable by demographics.

## Stack
Python 3.11, sentence-transformers, umap-learn, hdbscan, FastAPI, SQLite. Frontend: plain HTML/CSS/JS in web/ (no build step, no npm), served by the FastAPI app at /. Offline sample data lives in web/sample/sample.js.

## Rules
- All model calls go through pipeline/llm.py and are cached on disk by prompt hash.
- Every pipeline stage is idempotent and reads/writes compass.db.
- Scoring formula lives only in api/scoring.py; weights come from the request.
- Dedupe counts unique customers per issue, always after filters are applied.
- Hide segments with fewer than 20 customers.
- Never use real personal data. Mask emails and phone numbers at ingest.
- Run pytest before every commit. Commit after each working phase.
- Ask before adding a dependency.

## Commands
python pipeline/run_all.py | uvicorn api.main:app --reload | cd web && npm run dev | pytest
