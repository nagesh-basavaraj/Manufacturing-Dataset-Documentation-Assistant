# Architecture

The application uses a deliberately small local architecture:

1. **Frontend:** plain HTML, CSS, and JavaScript. It uploads files and renders results.
2. **API:** FastAPI exposes health, analysis, and report-download routes.
3. **Processing:** Pandas reads CSV/XLSX files, validates headers, matches optional metadata, and calculates deterministic statistics.
4. **LLM adapter:** an optional OpenAI-compatible endpoint generates descriptions only for features without user descriptions. User-provided descriptions are preserved unchanged. A conservative local generator is the fallback.
5. **Reports:** OpenPyXL (through Pandas) writes the data dictionary and missing-metadata Excel workbooks.

No database, agent framework, vector database, or deployment service is required.

## Processing flow

`Upload → Parse → Validate → Profile → Match metadata → Check completeness → Generate missing descriptions safely → Generate Excel reports → Render results`

Python is the source of truth for numeric calculations. The LLM is not used to calculate statistics.
