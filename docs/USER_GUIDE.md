# User guide

1. Start the FastAPI application using the README instructions.
2. Upload a CSV or XLSX dataset. A feature metadata file is optional.
3. If a metadata file is supplied, descriptions entered by the user are displayed unchanged.
4. If a description is not supplied, the system creates a short neutral description. If Gemini is configured, it generates a short evidence-based description instead.
5. Review the description source (`user_supplied`, `ai_generated`, or `system_generated`). Confirm AI-generated descriptions before treating them as authoritative.
6. Download the data dictionary and metadata review reports.

Descriptions are optional. If a description is supplied, it is shown unchanged. If absent, a concise local description is generated; a configured LLM can generate a more fluent evidence-based description. Description absence is never listed as a metadata gap and never affects completeness. Unknown numeric unit applicability remains a separate review item.

## Gemini AI configuration
Set `LLM_MODE=gemini`, `GEMINI_API_KEY`, and optionally `GEMINI_MODEL=gemini-2.5-flash` in `.env`. Restart the app after changing configuration. The application uses the official `google-genai` SDK. An OpenAI-compatible provider remains available as an alternative. The model receives only missing feature names, detected data types, units if supplied, and basic observed statistics. It does not receive the dataset rows. If the model is unavailable or returns invalid output, the safe system-generated descriptions remain in place.
