# Gemini setup

This project uses Google's official `google-genai` Python SDK with `gemini-2.5-flash` for optional feature-description generation.

## 1. Get an API key

Create a Gemini API key in Google AI Studio: https://aistudio.google.com/app/apikey

## 2. Configure the application

Copy `.env.example` to `.env` and set:

```env
LLM_MODE=gemini
GEMINI_API_KEY=PASTE_YOUR_API_KEY_HERE
GEMINI_MODEL=gemini-2.5-flash
MAX_UPLOAD_MB=25
```

Never commit `.env` or share your API key. The `.gitignore` excludes `.env`.

## 3. Install and run

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Restart the server after editing `.env`.

## 4. What is sent to Gemini?

Only missing feature names, detected data types, supplied units, and basic column-level observed statistics are sent. The application does not send raw dataset rows. User-supplied descriptions are excluded from the request and preserved exactly.

Gemini must return one short description for every requested feature. The application validates the feature names and response shape. Ambiguous sensor identifiers must remain explicitly unidentified. AI-generated descriptions should be reviewed by the user.

## 5. Fallback behaviour

If `GEMINI_API_KEY` is blank, the provider is unavailable, or the response is invalid, the application keeps its local descriptions and continues processing. The UI reports that AI generation was unavailable.

## 6. Model and cost

The default model is configurable through `GEMINI_MODEL`. Requests are made only for columns whose descriptions are missing. Review Google's current Gemini API pricing and quotas before using this with large datasets or in a public deployment.
