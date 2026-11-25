# Real Dataset Validation — v0.5.2

## Dataset used

- Dataset: Weather in Szeged 2006–2016 (`weatherHistory.csv`)
- Source: Kaggle dataset by Norbert Budincsevity
- Dataset page: https://www.kaggle.com/datasets/budincsevity/szeged-weather
- File used: the `weatherHistory.csv` file supplied by the user in this conversation
- Shape: 96,453 rows × 12 columns

This is a real historical weather dataset. It is useful for validating general CSV profiling, datetime detection, categorical/numeric feature handling, missing-value counting, and report exports. It is **not a manufacturing dataset**, so this test does not establish manufacturing-domain validation.

## Results

| Check | Result |
|---|---:|
| Dataset upload and analysis endpoint | Passed |
| Rows | 96,453 |
| Columns | 12 |
| Duplicate rows detected | 24 |
| Missing values detected | 517 |
| Data dictionary rows | 12 |
| Missing metadata entries | 8 |
| Dictionary Excel download | HTTP 200; valid XLSX payload |
| Dictionary PDF download | HTTP 200; valid PDF payload (`%PDF`) |
| Missing metadata Excel download | HTTP 200; valid XLSX payload |
| Missing metadata PDF download | HTTP 200; valid PDF payload (`%PDF`) |

## Bug found and fixed during real-data validation

The dataset represents missing precipitation values with the lowercase text token `null`. The previous CSV reader preserved it as ordinary text, which caused the missing-value count to be understated. Version 0.5.2 treats empty cells, whitespace-only cells, and the exact lowercase token `null` as missing. It continues to preserve labels such as `NA`, `NULL`, `N/A`, and `unknown` as literal text.

## Automated tests

- `pytest -q`: **76 passed**
- Python compile check: passed
- PDF and XLSX report endpoints exercised through FastAPI TestClient.

## AI provider limitation

The real dataset test used the local fallback (`LLM_MODE=off`). No live Gemini API call was made because no API key was configured. Gemini integration remains optional and must be verified with the user's own API key.

## Manufacturing-specific follow-up

For manufacturing-domain validation, use a manufacturing dataset such as UCI's AI4I 2020 Predictive Maintenance Dataset. UCI explicitly describes AI4I as a synthetic dataset reflecting industrial predictive-maintenance data; it should not be described as real plant telemetry. Dataset page: https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset.
