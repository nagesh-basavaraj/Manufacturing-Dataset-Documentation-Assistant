from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from .config import MAX_UPLOAD_MB
from .processing import read_table, parse_metadata, profile_dataset
from .llm import enrich_descriptions
from .reports import create_reports, report_path

app = FastAPI(title="PS 192 Manufacturing Dataset Documentation Assistant", version="0.5.2")
BASE = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE / "static" / "index.html").read_text(encoding="utf-8")

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "PS 192 Manufacturing Dataset Documentation Assistant"}

@app.post("/api/analyze")
async def analyze(dataset: UploadFile = File(...), metadata: UploadFile | None = File(None)):
    allowed = (".csv", ".xlsx", ".xlsm")
    name = dataset.filename or "dataset.csv"
    if not name.lower().endswith(allowed):
        raise HTTPException(400, "Dataset must be CSV or XLSX.")
    data = await dataset.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"Dataset exceeds {MAX_UPLOAD_MB} MB.")
    if not data:
        raise HTTPException(400, "Dataset file is empty.")
    try:
        df = read_table(name, data)
        if df.empty or len(df.columns) == 0:
            raise ValueError("Dataset has no rows or columns.")
        meta_df = None
        if metadata and metadata.filename:
            mname = metadata.filename
            if not mname.lower().endswith(allowed):
                raise ValueError("Metadata file must be CSV or XLSX.")
            mdata = await metadata.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
            if len(mdata) > MAX_UPLOAD_MB * 1024 * 1024:
                raise HTTPException(413, f"Metadata file exceeds {MAX_UPLOAD_MB} MB.")
            meta_df = read_table(mname, mdata)
        meta = parse_metadata(meta_df)
        dictionary, missing, summary = profile_dataset(df, meta)
        dictionary, ai_status = enrich_descriptions(dictionary)
        report_id = create_reports(dictionary, missing)
        import json
        preview = json.loads(df.head(8).to_json(orient="records", date_format="iso"))
        return {
            "summary": summary, "preview_columns": [str(c) for c in df.columns],
            "preview": preview, "dictionary": dictionary, "missing_metadata": missing,
            "ai_status": ai_status, "report_id": report_id
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, str(exc))

@app.get("/api/reports/{report_id}/{kind}")
def download_report(report_id: str, kind: str):
    return _download_report_file(report_id, kind, "xlsx")

@app.get("/api/reports/{report_id}/{kind}/{file_format}")
def download_report_format(report_id: str, kind: str, file_format: str):
    return _download_report_file(report_id, kind, file_format)

def _download_report_file(report_id: str, kind: str, file_format: str):
    try:
        path = report_path(report_id, kind, file_format)
        media_type = ("application/pdf" if file_format == "pdf" else
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        return FileResponse(path, filename=f"PS192_{kind}_report.{file_format}", media_type=media_type)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
