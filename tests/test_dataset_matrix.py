"""Thirty dataset scenarios through the full FastAPI analyze/report workflow."""
import io
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
CASES = [
("numeric",{"temperature":[20,21,22],"pressure":[1.1,1.2,1.3]}),
("mixed",{"cycle":[1,2,3],"state":["run","stop","run"]}),
("nulls",{"sensor_a":[1,None,3],"sensor_b":[None,None,4]}),
("all_null",{"unknown":[None,None,None]}),
("constant",{"constant_value":[7,7,7]}),
("unique",{"serial":["A1","A2","A3"]}),
("bool",{"active":[True,False,True]}),
("dates",{"recorded_at":["2026-01-01","2026-01-02","2026-01-03"]}),
("unicode",{"温度":[10,11,12],"状態":["稼働","停止","稼働"]}),
("spaces",{" Spindle Speed ":[100,110,120]}),
("punctuation",{"sensor-01/reading (%)":[2.1,2.2,2.3]}),
("one_row",{"x":[1],"y":["a"]}),
("many_rows",{"x":list(range(250)),"y":[i%4 for i in range(250)]}),
("many_columns",{f"feature_{i}":[i,i+1] for i in range(45)}),
("negative",{"vibration":[-1.0,-0.5,0.0]}),
("scientific",{"reading":[1e-9,2e-9,3e-9]}),
("decimal",{"flow":[0.001,0.002,0.003]}),
("text_commas",{"note":["part, A","part, B"]}),
("quotes",{"operator_note":['said "ok"',"line 2"]}),
("formula_strings",{"input_text":["=1+1","+SUM(A1:A2)","@test"]}),
("duplicate_rows",{"a":[1,1,2],"b":["x","x","y"]}),
("outlier",{"measurement":[1,1,1,10000]}),
("categorical_many",{"mode":[f"mode_{i%12}" for i in range(36)]}),
("empty_strings",{"label":["","x"," "]}),
("leading_zero",{"batch_code":["001","002","010"]}),
("sensor_ambiguous",{"ch_01":[3,4,5],"ch_02":[30,40,50]}),
("metadata_like",{"feature_name":["a","b"],"description":["x","y"]}),
("long_names",{"feature_"+"x"*90:[1,2]}),
("whitespace_values",{"status":[" on ","off ","  "]}),
("large_numeric",{"count":[10**8,10**9,10**10]}),
]
@pytest.mark.parametrize("case_name,data",CASES,ids=[x[0] for x in CASES])
def test_dataset_end_to_end_matrix(case_name,data):
    frame=pd.DataFrame(data); csv=frame.to_csv(index=False).encode("utf-8-sig")
    response=client.post("/api/analyze",files={"dataset":(f"{case_name}.csv",csv,"text/csv")})
    assert response.status_code==200,(case_name,response.text)
    result=response.json()
    assert result["summary"]["rows"]==len(frame)
    assert result["summary"]["columns"]==len(frame.columns)
    assert len(result["dictionary"])==len(frame.columns)
    assert len({x["feature"] for x in result["dictionary"]})==len(frame.columns)
    for item in result["dictionary"]:
        assert item["feature"] in [str(c) for c in frame.columns]
        assert item["data_type"] and item["description"]
        assert 0<=item["null_percent"]<=100
    for kind in ("dictionary","missing"):
        download=client.get(f"/api/reports/{result['report_id']}/{kind}")
        assert download.status_code==200,(case_name,kind,download.text)
        assert download.content[:2]==b"PK"

def test_xlsx_dataset_and_metadata_matching():
    data=io.BytesIO(); pd.DataFrame({"spindle_speed":[100,110],"state":["run","stop"]}).to_excel(data,index=False)
    meta=io.BytesIO(); pd.DataFrame({"feature_name":["Spindle Speed"],"description":["Rotational speed recorded by the machine"],"unit":["rpm"]}).to_excel(meta,index=False)
    response=client.post("/api/analyze",files={"dataset":("machine.xlsx",data.getvalue(),"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),"metadata":("metadata.xlsx",meta.getvalue(),"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert response.status_code==200,response.text
    spindle=next(x for x in response.json()["dictionary"] if x["feature"]=="spindle_speed")
    assert spindle["description"]=="Rotational speed recorded by the machine" and spindle["unit"]=="rpm"

def test_invalid_extension_rejected():
    assert client.post("/api/analyze",files={"dataset":("payload.exe",b"abc","application/octet-stream")}).status_code==400

def test_empty_file_rejected():
    assert client.post("/api/analyze",files={"dataset":("empty.csv",b"","text/csv")}).status_code==400

def test_metadata_without_feature_column_rejected():
    r=client.post("/api/analyze",files={"dataset":("data.csv",b"x\n1\n2\n","text/csv"),"metadata":("meta.csv",b"wrong,value\na,b\n","text/csv")})
    assert r.status_code==400

def test_preview_nulls_are_json_nulls():
    r=client.post("/api/analyze",files={"dataset":("nulls.csv",b"a,b\n1,x\n,\n3,z\n","text/csv")})
    assert r.status_code==200 and r.json()["preview"][1]=={"a":None,"b":None}

def test_missing_report_has_headers_when_no_gaps():
    r=client.post("/api/analyze",files={"dataset":("data.csv",b"machine_state\non\noff\n","text/csv"),"metadata":("meta.csv",b"feature_name,description\nmachine_state,Operating state\n","text/csv")})
    assert r.status_code==200 and r.json()["missing_metadata"]==[]
    report=client.get(f"/api/reports/{r.json()['report_id']}/missing")
    assert list(pd.read_excel(io.BytesIO(report.content)).columns)==["feature","missing_field","reason"]

def test_duplicate_csv_headers_are_rejected():
    r=client.post("/api/analyze",files={"dataset":("duplicate.csv",b"a,a\n1,2\n","text/csv")})
    assert r.status_code==400 and "duplicate" in r.json()["detail"].lower()

def test_blank_csv_header_is_rejected():
    r=client.post("/api/analyze",files={"dataset":("blank.csv",b"a,\n1,2\n","text/csv")})
    assert r.status_code==400

def test_literal_na_values_preserved():
    r=client.post("/api/analyze",files={"dataset":("labels.csv",b"label\nNA\nNULL\n\n","text/csv")})
    assert r.status_code==200
    assert r.json()["summary"]["rows"]==3 and r.json()["summary"]["total_missing_cells"]==1
    assert r.json()["preview"][0]["label"]=="NA" and r.json()["preview"][1]["label"]=="NULL"
    assert r.json()["preview"][2]["label"] is None

def test_punctuation_only_header_rejected():
    r=client.post("/api/analyze",files={"dataset":("symbols.csv",b"%%%\n1\n","text/csv")})
    assert r.status_code==400 and "letter or number" in r.json()["detail"]

def test_xlsx_duplicate_headers_rejected():
    data=io.BytesIO(); writer=pd.ExcelWriter(data,engine="openpyxl")
    pd.DataFrame([[1,2]],columns=["reading","reading"]).to_excel(writer,index=False); writer.close()
    r=client.post("/api/analyze",files={"dataset":("duplicate.xlsx",data.getvalue(),"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code==400 and "duplicate" in r.json()["detail"].lower()


def test_empty_metadata_csv_with_wrong_header_is_rejected():
    response = client.post("/api/analyze", files={
        "dataset": ("data.csv", b"reading\\n1\\n2\\n", "text/csv"),
        "metadata": ("metadata.csv", b"wrong_header\\n", "text/csv")
    })
    assert response.status_code == 400
