from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_analyze_csv_and_download():
    csv = b"sensor_01,status\n10,on\n20,off\n"
    response = client.post("/api/analyze", files={"dataset": ("sample.csv", csv, "text/csv")})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["columns"] == 2
    assert len(body["dictionary"]) == 2
    report = client.get(f"/api/reports/{body['report_id']}/dictionary")
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("application/vnd.openxmlformats")


def test_frontend_assets_are_served():
    page = client.get("/").text
    assert "Dataset documentation" in page
    assert "Quick report summary" in page
    assert 'id="report-summary-text"' in page
    js = client.get("/static/app.js")
    css = client.get("/static/styles.css")
    assert js.status_code == 200 and "summaryParts" in js.text
    assert css.status_code == 200 and ".report-summary" in css.text

def test_xlsx_datetime_preview_is_json_serializable():
    import io, pandas as pd
    data=io.BytesIO(); pd.DataFrame({"recorded_at":pd.to_datetime(["2026-01-01","2026-01-02"]),"value":[1,2]}).to_excel(data,index=False)
    r=client.post("/api/analyze",files={"dataset":("dated.xlsx",data.getvalue(),"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code==200 and r.json()["preview"][0]["recorded_at"].startswith("2026-01-01")

def test_excel_formula_like_text_is_protected(tmp_path,monkeypatch):
    from app import reports
    from openpyxl import load_workbook
    monkeypatch.setattr(reports.config,"REPORT_DIR",str(tmp_path))
    rid=reports.create_reports([{"feature":"=HYPERLINK(\"https://bad.invalid\")","description":"@SUM(A1:A2)"}],[])
    ws=load_workbook(tmp_path/f"{rid}_dictionary.xlsx",data_only=True).active
    assert ws.cell(2,1).value.startswith("'=") and ws.cell(2,2).value.startswith("'@")

def test_upload_size_limit(monkeypatch):
    import app.main as main_module
    monkeypatch.setattr(main_module,"MAX_UPLOAD_MB",0)
    assert client.post("/api/analyze",files={"dataset":("tiny.csv",b"x\n1\n","text/csv")}).status_code==413

def test_both_report_formats_are_available():
    csv = b"machine_speed,temperature\n1200,72\n1250,74\n"
    response = client.post("/api/analyze", files={"dataset": ("machine.csv", csv, "text/csv")})
    assert response.status_code == 200, response.text
    report_id = response.json()["report_id"]
    for kind in ("dictionary", "missing"):
        excel = client.get(f"/api/reports/{report_id}/{kind}/xlsx")
        pdf = client.get(f"/api/reports/{report_id}/{kind}/pdf")
        assert excel.status_code == 200
        assert "spreadsheetml" in excel.headers["content-type"]
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.content.startswith(b"%PDF")

def test_quick_summary_contains_total_missing_values():
    page = client.get("/").text
    assert 'id="s-missing-values"' in page
    js = client.get("/static/app.js").text
    assert '$("s-missing-values").textContent' in js
    assert 'setDownloadLinks("dict")' in js
    assert 'setDownloadLinks("missing")' in js
