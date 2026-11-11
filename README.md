# Complaint Compass

Complaints arrive by email, voice, chatbot and social media, worded differently, often from the same customer more than once. Complaint Compass groups them into real issues, counts each affected customer once, and ranks the top 10 with a formula you can see and adjust. Filters and a heatmap show which customer groups each problem hits hardest. Built for PS-19.

![Top issues](docs/screenshots/1-top-issues.png)

## Run the demo

```
pip install -r requirements.txt
python demo.py
```

`demo.py` starts the API and dashboard, checks `/api/health`, and opens http://127.0.0.1:8000/. It never calls a model unless you pass `--live`; everything comes from `compass.db` and the cached answers in `.llm_cache/`.

| Command | What it does |
| --- | --- |
| `python demo.py` | Use the existing results and open the dashboard |
| `python demo.py --check` | Start, confirm the API is healthy, stop. Run this before going on stage |
| `python demo.py --rescore` | Re-run naming, dedupe, severity and scoring (stages 4 to 7), then open |
| `python demo.py --rebuild` | Re-run the whole pipeline (embeddings and clustering take a few minutes) |
| `python demo.py --rescore --live` | Same as `--rescore`, calling the model for anything not cached |

If the health check says issue names are keyword placeholders, the model naming step has not run yet; see **Model setup**.

If the API cannot start at all, open `web/index.html` directly in a browser. It shows built-in sample data with a banner saying so.

## Setup in full

Python 3.11 or 3.12.

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and choose a model provider (below).
3. The synthetic data is already in `data/`. To regenerate it: `python data/generate.py` (add `--llm` to have the model write the phrasings).
4. Run the pipeline: `python pipeline/run_all.py` (or `--from 04` to redo only naming onward, `--offline` to use cached answers only).
5. Start the app: `python demo.py`, or `uvicorn api.main:app --reload` for development.
6. Run the tests: `pytest`

### Model setup

All model calls go through `pipeline/llm.py` and are cached on disk by prompt hash, so each prompt is paid for once. About 430 calls cover the whole dataset: ~31 to name clusters, ~400 to score severity in batches of 20.

- **Anthropic:** set `ANTHROPIC_API_KEY`, `LLM_MODEL` (bulk work) and `LLM_MODEL_STRONG` (cluster naming).
- **Free OpenAI-compatible provider** (Groq, Google AI Studio and others): set `LLM_PROVIDER=openai_compat`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, and `SEVERITY_WORKERS=2` to stay under free rate limits.
- **Fallback chain:** number the settings `LLM_1_*`, `LLM_2_*`, ... (up to 9) and they are tried in order. When one runs out of quota, rejects its key, or stays rate-limited, it is skipped for the rest of the run and the next one answers; the console prints which provider took over. A short outage skips a provider for that one call only. Answers already cached from any provider are reused. Examples for all three setups are in `.env.example`.
- **No key:** the pipeline still runs. Issues are named from their most common words and severity uses a keyword rule. Both are flagged by `/api/health` and `demo.py`.

## How it works

```
data/*.csv ─► 01 ingest ─► 02 embed ─► 03 cluster ─► 04 name + merge ─► 05 dedupe ─► 06 severity ─► 07 score ─► compass.db ─► API + dashboard
```

| Stage | What happens |
| --- | --- |
| 1 Ingest | Masks emails, phone numbers and handles; stores only salted hashes of contacts; joins customer profiles |
| 2 Embed | Strips channel boilerplate (email greetings, hashtags, voice filler), then embeds with all-MiniLM-L6-v2 locally |
| 3 Cluster | UMAP then HDBSCAN (min cluster size 100); stray points join the nearest cluster above cosine 0.5 |
| 4 Name and merge | The model names each cluster from 15 samples; clusters merge only if centroids are above cosine 0.85 and names agree. The reason is kept |
| 5 Dedupe | Matches a complaint to a customer by id, then hashed contact, then text similarity within 7 days. Links repeats across issues (same customer, different channel, within 7 days, cosine 0.55 or more). Keeps a one-line reason per complaint |
| 6 Severity | Rubric scored by the model: money lost (0 to 3), legal or regulatory risk (0 to 3), repeat contact (0 to 2), churn language (0 to 2), with an evidence quote |
| 7 Score | Per-issue reach, severity, recency and segment lift |

**Score** = 100 × (w1 × reach + w2 × severity + w3 × recency), defaults 0.5, 0.3, 0.2, normalised to add to 1. Reach is unique customers divided by the largest issue's unique customers. Severity is the mean of each customer's worst complaint. Recency is the share of complaints in the last 14 days of the data. The formula lives only in `api/scoring.py`.

**Lift** = (share of a group reporting the issue) ÷ (share of all customers reporting it). 1.0 is average.

**Privacy floor:** any group under 20 customers is hidden everywhere: filters, heatmap and compare.

**Counts are recomputed after every filter change**, so reach is always unique customers inside the filtered group.

## Measured results

The data is synthetic with planted answers, so each part is scored against ground truth (`data/ground_truth.csv`).

| What | Result | How to reproduce |
| --- | --- | --- |
| Clustering | 31 clusters for 25 planted issues; purity 0.896, adjusted Rand index 0.759; 294 of 8,000 uncategorized | `pytest -s tests/test_clusters.py`, tune with `pipeline/tune_clusters.py` |
| Dedupe | Precision 0.93, recall 0.79 on 1,360 planted cross-channel repeats (recall was 0.70 before cross-issue linking) | `pytest -s tests/test_dedupe.py`, explain misses with `pipeline/diagnose_dedupe.py`, tune with `pipeline/tune_links.py` |
| Planted group skews | All four recovered: OTP failures 2.3× in Karnataka and 2.9× in Uttar Pradesh; fee confusion 3.1× for students; premium support wait 4.8× in the high income bracket; app usability 3.0× for age 55+ | Who is affected screen |

These figures come from a run with keyword names and keyword severity. Re-measure after the model steps run.

## Three-minute demo script

1. **The problem (20 s).** "Complaints come in through four channels, worded differently, and the same customer often complains twice. Counting messages overstates problems and hides who is hurt."
2. **The counter (20 s).** Point at the left panel: 8,000 complaints from 2,696 unique customers. On any issue row, show complaints versus unique customers.
3. **The ranking (30 s).** Point at a score bar: teal is reach, amber severity, violet recency. Drag Severity to the right; the rows reorder. Say the formula is printed under the sliders.
4. **Filter (25 s).** Choose Student status: Students. The fees issue moves to the top. Clear it and choose State: Karnataka; OTP failures move to the top.
5. **Who is affected (30 s).** Open the heatmap by State: OTP failures light up in Karnataka and Uttar Pradesh. Switch to Income bracket: premium support wait, marked "Outside the top 10", is 4.8× in the high bracket. A big issue for a small, valuable group would be lost in a plain top 10.
6. **Evidence (30 s).** Click the Karnataka OTP cell. Show the score breakdown, "101 complaints collapse to 87 unique customers", and an evidence card with its "Counted once" note naming the other channel.
7. **Compare (10 s).** Compare Karnataka with Maharashtra side by side.
8. **Close (15 s).** "Because the data has planted answers, we measured ourselves: clustering purity 0.90, dedupe precision 0.93 and recall 0.79, all four planted skews recovered. Next: real channel connectors, alerts when an issue spikes, and a what-if view of how many customers a fix would reach."

Back-ups: `python demo.py --check` before you start; if the API fails, open `web/index.html` for the sample view; keep a screen recording.

## Screens

| | |
| --- | --- |
| ![Top issues filtered to students](docs/screenshots/2-filtered-students.png) | ![Heatmap by state](docs/screenshots/3-heatmap-state.png) |
| ![Heatmap by income with a standout](docs/screenshots/4-heatmap-income.png) | ![Issue detail with evidence](docs/screenshots/5-issue-detail.png) |
| ![Compare two states](docs/screenshots/6-compare.png) | ![Phone layout](docs/screenshots/7-mobile.png) |

## API

| Endpoint | Returns |
| --- | --- |
| `GET /api/health` | Status, counts, and whether names and severity came from the model |
| `GET /api/issues` | Top issues. Filters: `country`, `state`, `age_group`, `is_student`, `income_bracket`. Weights: `w_reach`, `w_severity`, `w_recency` |
| `GET /api/issues/{id}` | One issue with why it ranks there, dedupe and merge notes, 3 to 5 evidence complaints. Same filters and weights |
| `GET /api/heatmap?dim=state` | Lift for the top 10 issues plus standouts (lift 2.0 or more for a group with 20+ reporting customers) |
| `GET /api/compare?dim=state&a=Karnataka&b=Maharashtra` | Two groups' top issues side by side |
| `GET /api/filters` | Filter values that pass the privacy floor |

## Layout

```
data/       generate.py and the synthetic CSVs (ground_truth.csv is hidden from the pipeline)
pipeline/   llm.py (only place that calls a model), stages 01-07, run_all.py, tune_*.py, diagnose_dedupe.py
api/        main.py (FastAPI), queries.py (all logic), scoring.py (formula), schemas.py
web/        index.html, app.js, styles.css: plain JS, no build step; sample/ for offline use
tests/      pytest suite, including checks against ground truth
docs/       screenshots
demo.py     one-command launcher
```

## Known limits

- Data is synthetic. Real channel connectors (Gmail, social APIs, call transcription) are out of scope; voice arrives as transcripts.
- About 4% of complaints stay uncategorized after clustering and are not counted in any issue.
- Dedupe can only link a repeat to its original when the customer is known (id or contact). Remaining misses are mostly repeats clustered into a different issue whose text is too dissimilar to link.
- Close issues can share a cluster (for example hidden fees and wrong bill). The model merge step and the confidence flag help; they do not eliminate it.
- Not built yet: the natural-language filter and the what-if view.
