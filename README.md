# PS 192 — Manufacturing Dataset Documentation Assistant

A local-first application that profiles manufacturing datasets, matches user-provided metadata, identifies missing documentation, and produces Excel reports.

## What it does
- Upload CSV/XLSX process data and an optional metadata CSV/XLSX.
- Preview the dataset and calculate deterministic column statistics.
- Match metadata by feature/column name (normalized matching only).
- Generate concise fallback descriptions for every feature; preserve user-provided descriptions exactly.
- Optionally call Google Gemini 2.5 Flash for grounded descriptions (recommended), or an OpenAI-compatible endpoint.
- Export a data dictionary and missing-metadata report as Excel files.

## Safety rules
- The application never infers sensor meaning from a column name or values.
- It never invents units, approved limits, thresholds, or manufacturer specifications.
- Min/max are observed dataset values, not approved operating limits.
- The LLM receives compact column-level evidence, not the complete raw dataset.
- If no LLM is configured, the application clearly labels its neutral fallback descriptions.
- Original column names and raw values are preserved.

## Run locally
Python 3.10+ is recommended.

```bash
cd ps192_manufacturing_assistant
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env   # Windows; on macOS/Linux use: cp .env.example .env
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

No database is required. Uploaded files are processed in memory; generated reports are stored under the local `reports/` folder.

## Gemini AI description generation (recommended)
The application includes a direct integration with Google Gemini using the official `google-genai` Python SDK. Create an API key in Google AI Studio, then copy `.env.example` to `.env` and set:

```env
LLM_MODE=gemini
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
```

Restart the application after changing `.env`. When enabled, Gemini generates descriptions only for features without a user-provided description. It receives column names, detected data types, units if supplied, and basic observed statistics—not raw dataset rows. User-provided descriptions are never sent to Gemini or overwritten.

If the API key is missing, Gemini is unavailable, or the response fails validation, the application retains its local fallback descriptions. AI-generated descriptions should be reviewed before being treated as authoritative. Keep API keys private and do not commit `.env` to Git.

To use another OpenAI-compatible provider instead, set `LLM_MODE=openai_compatible`, `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL`.

## Metadata file format
A CSV/XLSX file can contain columns such as:
- `feature_name` (or `feature`, `column_name`, `field`)
- `description`
- `unit` (or `units`)
- `measurement_range` (optional; treated only as user-supplied text)
- `unit_applicable` (optional yes/no field; use it to confirm whether a numeric feature requires a unit)

Example:

| feature_name | description | unit |
|---|---|---|
| feature_name | description | unit | unit_applicable |
|---|---|---|---|
| spindle_speed | Rotational speed recorded by the machine | rpm | yes |
| batch_id | Batch identifier | | no |

Metadata descriptions and units are displayed as user-supplied content. The app does not verify whether they are technically correct.

## API
- `GET /api/health`
- `POST /api/analyze` (multipart: `dataset`, optional `metadata`)
- `GET /api/reports/{report_id}/{kind}` where kind is `dictionary` or `missing`

## Tests
```bash
pytest -q
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/USER_GUIDE.md](docs/USER_GUIDE.md), and [docs/GEMINI_SETUP.md](docs/GEMINI_SETUP.md) for design, usage, and Gemini setup details.


### Description behaviour (v0.5.0)
- User-provided descriptions are displayed unchanged.
- If a description is supplied, it is displayed exactly as entered.
- If it is missing, the application generates a concise description locally; when an LLM is configured, it can generate a more fluent evidence-based description.
- Ambiguous sensor names are never assigned guessed meanings.
- Descriptions are optional, are not included in missing-metadata gaps, and never affect feature completeness.
- Configure an external LLM only when you are comfortable sending column names, detected types and basic statistics to that provider. Dataset rows are not sent.


## Version 0.5.2 — Report summary UI

The results page now shows a compact report overview immediately before the detailed data dictionary and missing-metadata tables. It summarizes row/feature counts, description coverage, AI-generated description count, metadata gaps, missing cells, and duplicate rows. The overview is derived from the actual analysis response; it does not invent findings.


## Version 0.5.2 updates

- Quick report summary now includes the total missing-cell count as a separate metric.
- Both the data dictionary and missing-metadata report can be downloaded as Excel (`.xlsx`) or PDF (`.pdf`).
- PDF exports use the same analysed report rows as the Excel exports.
- Empty, whitespace-only, and lowercase `null` CSV cells are counted as missing; literal labels such as `NA`, `NULL`, `N/A`, and `unknown` remain text.
- See `REAL_DATASET_TEST_REPORT.md` for the real Kaggle dataset validation results.
