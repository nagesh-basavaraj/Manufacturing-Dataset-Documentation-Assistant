import pandas as pd
from app.processing import profile_dataset, parse_metadata, normalize_key

def test_profile_does_not_infer_sensor_meaning_or_unit():
    df = pd.DataFrame({"sensor_01": [10, 20, None], "status": ["on", "off", "on"]})
    dictionary, missing, summary = profile_dataset(df, {})
    sensor = dictionary[0]
    assert "sensor_01" in sensor["description"] and "numeric values" in sensor["description"]
    assert sensor["unit"] == ""
    assert sensor["unit_source"] == "unknown"
    assert any(x["feature"] == "sensor_01" and x["missing_field"] == "unit_applicability" for x in missing)
    assert summary["rows"] == 3

def test_metadata_matching_uses_normalized_key():
    meta = parse_metadata(pd.DataFrame([{"feature_name":"Spindle Speed", "description":"Rotational speed", "unit":"rpm"}]))
    df = pd.DataFrame({"spindle_speed":[100, 110]})
    dictionary, missing, _ = profile_dataset(df, meta)
    assert dictionary[0]["description"] == "Rotational speed"
    assert dictionary[0]["unit"] == "rpm"
    assert dictionary[0]["description_source"] == "user_supplied"
    assert not missing

def test_normalize_key():
    assert normalize_key("Spindle-Speed (RPM)") == "spindlespeedrpm"


def test_literal_na_and_null_words_are_not_missing():
    from app.processing import read_table
    frame=read_table("labels.csv",b"label\nNA\nNULL\n\n")
    assert frame.loc[0,"label"]=="NA" and frame.loc[1,"label"]=="NULL" and pd.isna(frame.loc[2,"label"])

def test_duplicate_metadata_keys_are_rejected():
    import pytest
    frame=pd.DataFrame([{"feature_name":"Spindle Speed","description":"A","unit":"rpm"},{"feature_name":"spindle_speed","description":"B","unit":"rpm"}])
    with pytest.raises(ValueError,match="duplicate or ambiguous"): parse_metadata(frame)

def test_all_null_column_is_unknown():
    dictionary,missing,_=profile_dataset(pd.DataFrame({"empty_sensor":[None,None]}),{})
    assert dictionary[0]["data_type"]=="unknown (all values missing)" and dictionary[0]["completeness"]=="Unknown"
    assert any(x["missing_field"]=="data_type" for x in missing)

def test_iqr_outlier_count():
    dictionary,_,_=profile_dataset(pd.DataFrame({"reading":[1,1,1,1,100]}),{})
    assert dictionary[0]["outlier_count_iqr"]==1

def test_numeric_profile_reports_non_numeric_entries():
    dictionary,_,_=profile_dataset(pd.DataFrame({"reading":["1","2","3","4","bad","6","7","8","9","10"]}),{})
    assert dictionary[0]["data_type"]=="numeric" and dictionary[0]["non_numeric_count"]==1 and dictionary[0]["max"]==10.0

def test_llm_does_not_send_undocumented_features(monkeypatch):
    from app import llm,config
    monkeypatch.setattr(config,"LLM_MODE","openai_compatible"); monkeypatch.setattr(config,"LLM_BASE_URL","https://example.invalid/v1")
    monkeypatch.setattr(config,"LLM_API_KEY","test"); monkeypatch.setattr(config,"LLM_MODEL","test")
    item={"feature":"sensor_17","data_type":"numeric","description":"sensor_17 contains numeric values; its specific purpose has not been confirmed.","description_source":"system_generated"}
    updated,status=llm.enrich_descriptions([item])
    assert updated[0]["description"]==item["description"] and "safe system-generated descriptions retained" in status

def test_llm_generates_only_missing_descriptions_and_preserves_user_text(monkeypatch):
    import json
    from types import SimpleNamespace
    from app import llm,config
    monkeypatch.setattr(config,"LLM_MODE","openai_compatible"); monkeypatch.setattr(config,"LLM_BASE_URL","https://example.invalid/v1")
    monkeypatch.setattr(config,"LLM_API_KEY","test"); monkeypatch.setattr(config,"LLM_MODEL","test")
    def fake_post(*args,**kwargs):
        content=json.dumps({"descriptions":[{"feature":"spindle_speed","description":"Machine-recorded rotational speed."}]})
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{"choices":[{"message":{"content":content}}]})
    monkeypatch.setattr(llm.httpx,"post",fake_post)
    items=[{"feature":"spindle_speed","data_type":"numeric","description":"Rotational speed","description_source":"user_supplied"},{"feature":"sensor_17","data_type":"numeric","description":"sensor_17 contains numeric values; its specific purpose has not been confirmed.","description_source":"system_generated","min":1,"max":2,"mean":1.5}]
    content=json.dumps({"descriptions":[{"feature":"sensor_17","description":"Numeric readings in sensor_17; the measured quantity is not specified."}]})
    monkeypatch.setattr(llm.httpx,"post",lambda *a,**k:SimpleNamespace(raise_for_status=lambda:None,json=lambda:{"choices":[{"message":{"content":content}}]}))
    updated,_=llm.enrich_descriptions(items)
    assert updated[0]["description"]=="Rotational speed" and updated[0]["description_source"]=="user_supplied"
    assert updated[1]["description_source"]=="ai_generated" and "not specified" in updated[1]["description"]

def test_llm_invalid_response_falls_back(monkeypatch):
    from types import SimpleNamespace
    from app import llm,config
    monkeypatch.setattr(config,"LLM_MODE","openai_compatible"); monkeypatch.setattr(config,"LLM_BASE_URL","https://example.invalid/v1")
    monkeypatch.setattr(config,"LLM_API_KEY","test"); monkeypatch.setattr(config,"LLM_MODEL","test")
    monkeypatch.setattr(llm.httpx,"post",lambda *a,**k:SimpleNamespace(raise_for_status=lambda:None,json=lambda:{"choices":[{"message":{"content":"{\"descriptions\": []}"}}]}))
    items=[{"feature":"f1","data_type":"numeric","description":"f1 contains numeric values; its specific purpose has not been confirmed.","description_source":"system_generated"}]
    updated,status=llm.enrich_descriptions(items)
    assert updated==items and "system-generated descriptions retained" in status


def test_iso_date_strings_are_datetime_not_text():
    frame = pd.DataFrame({"recorded_at": ["2026-01-01T09:00:00", "2026-01-02T09:00:00"]})
    dictionary, _, _ = profile_dataset(frame, {})
    assert dictionary[0]["data_type"] == "datetime"
    assert dictionary[0]["min"].startswith("2026-01-01")

def test_excel_datetime_values_are_not_profiled_as_numeric():
    import io
    from app.processing import read_table
    data = io.BytesIO()
    pd.DataFrame({"recorded_at": pd.to_datetime(["2026-01-01", "2026-01-02"])}).to_excel(data, index=False)
    frame = read_table("dates.xlsx", data.getvalue())
    dictionary, _, _ = profile_dataset(frame, {})
    assert dictionary[0]["data_type"] == "datetime"
    assert dictionary[0]["mean"] is None

def test_numeric_feature_unit_applicability_is_not_assumed():
    frame = pd.DataFrame({"batch_id": [1001, 1002, 1003]})
    dictionary, missing, _ = profile_dataset(frame, {})
    assert dictionary[0]["completeness"] == "Unknown"
    assert any(item["missing_field"] == "unit_applicability" for item in missing)
    assert not any(item["missing_field"] == "unit" for item in missing)

def test_explicit_unit_applicability_controls_missing_unit():
    frame = pd.DataFrame({"spindle_speed": [100, 110]})
    meta = parse_metadata(pd.DataFrame([{"feature_name": "spindle_speed", "description": "Rotational speed", "unit_applicable": "yes"}]))
    _, missing, _ = profile_dataset(frame, meta)
    assert any(item["missing_field"] == "unit" for item in missing)
    meta = parse_metadata(pd.DataFrame([{"feature_name": "batch_id", "description": "Batch identifier", "unit_applicable": "no"}]))
    dictionary, missing, _ = profile_dataset(pd.DataFrame({"batch_id": [1001, 1002]}), meta)
    assert dictionary[0]["completeness"] == "Complete"
    assert not any(item["missing_field"] in {"unit", "unit_applicability"} for item in missing)

def test_empty_metadata_file_still_requires_feature_column():
    import pytest
    with pytest.raises(ValueError, match="feature_name"):
        parse_metadata(pd.DataFrame(columns=["wrong_header"]))


def test_missing_description_does_not_make_feature_incomplete():
    dictionary, missing, summary = profile_dataset(pd.DataFrame({"temperature_c": [10, 12, 14]}), {})
    assert dictionary[0]["completeness"] == "Unknown"  # unit applicability still needs confirmation
    assert not any(item["missing_field"] in {"description", "optional_description"} for item in missing)
    assert not any(item["missing_field"] == "description" for item in missing)


def test_description_is_not_part_of_completeness_when_unit_is_confirmed_not_applicable():
    meta = parse_metadata(pd.DataFrame([{"feature_name": "batch_id", "unit_applicable": "no"}]))
    dictionary, missing, _ = profile_dataset(pd.DataFrame({"batch_id": [1, 2]}), meta)
    assert dictionary[0]["completeness"] == "Complete"
    assert dictionary[0]["description_source"] == "system_generated"
    assert not any(item["missing_field"] in {"description", "optional_description"} for item in missing)

def test_mixed_timezone_datetime_values_use_consistent_utc_bounds():
    frame = pd.DataFrame({"Formatted Date": [
        "2006-04-01 00:00:00.000 +0200",
        "2016-09-09 23:00:00.000 +0200",
    ]})
    dictionary, _, _ = profile_dataset(frame, {})
    item = dictionary[0]
    assert item["data_type"] == "datetime"
    assert item["min"].startswith("2006-03-31T22:00:00")
    assert item["max"].startswith("2016-09-09T21:00:00")

def test_weather_dataset_feature_names_get_concise_local_descriptions():
    frame = pd.DataFrame({
        "Formatted Date": ["2006-04-01T00:00:00+02:00"],
        "Temperature (C)": [12.5],
        "Humidity": [0.7],
        "sensor_17": [42],
    })
    dictionary, missing, _ = profile_dataset(frame, {})
    by_name = {item["feature"]: item for item in dictionary}
    assert by_name["Formatted Date"]["description"] == "Date and time when the weather observation was recorded."
    assert by_name["Temperature (C)"]["description"] == "Air temperature recorded in degrees Celsius."
    assert "not confirmed" in by_name["sensor_17"]["description"]
    assert all(item["description"] for item in dictionary)
    assert not any(item["missing_field"] in {"description", "optional_description"} for item in missing)


def test_user_description_is_displayed_exactly_and_not_replaced():
    exact = "My own feature explanation — keep this wording."
    meta = parse_metadata(pd.DataFrame([{"feature_name": "temperature_c", "description": exact}]))
    dictionary, missing, _ = profile_dataset(pd.DataFrame({"temperature_c": [10, 11]}), meta)
    assert dictionary[0]["description"] == exact
    assert dictionary[0]["description_source"] == "user_supplied"
    assert not any(item["missing_field"] in {"description", "optional_description"} for item in missing)


def test_gemini_generates_missing_descriptions_and_preserves_user_text(monkeypatch):
    import json, sys, types
    from types import SimpleNamespace
    from app import llm, config

    calls = {}
    class FakeClient:
        def __init__(self, api_key):
            calls["api_key"] = api_key
            self.models = self
        def generate_content(self, **kwargs):
            calls["request"] = kwargs
            return SimpleNamespace(text=json.dumps({"descriptions": [
                {"feature": "sensor_17", "description": "Numeric readings in sensor_17; the specific measurement is not specified."}
            ]}))
    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = FakeClient
    fake_genai.types = SimpleNamespace(GenerateContentConfig=lambda **kwargs: kwargs)
    fake_google = types.ModuleType("google")
    fake_google.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setattr(config, "LLM_MODE", "gemini")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setattr(config, "GEMINI_MODEL", "gemini-2.5-flash")

    items = [
        {"feature": "temperature", "data_type": "numeric", "description": "User wording", "description_source": "user_supplied"},
        {"feature": "sensor_17", "data_type": "numeric", "description": "Fallback", "description_source": "system_generated", "min": 1, "max": 2},
    ]
    updated, status = llm.enrich_descriptions(items)
    assert updated[0]["description"] == "User wording"
    assert updated[0]["description_source"] == "user_supplied"
    assert updated[1]["description_source"] == "ai_generated"
    assert "not specified" in updated[1]["description"]
    assert calls["api_key"] == "test-gemini-key"
    assert calls["request"]["model"] == "gemini-2.5-flash"
    assert "temperature" not in calls["request"]["contents"]  # user-described feature is not sent
    assert "sensor_17" in calls["request"]["contents"]
    assert "gemini-2.5-flash" in status


def test_gemini_failure_keeps_local_descriptions(monkeypatch):
    import sys, types
    from types import SimpleNamespace
    from app import llm, config
    class FakeClient:
        def __init__(self, api_key): self.models = self
        def generate_content(self, **kwargs): raise RuntimeError("provider unavailable")
    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = FakeClient
    fake_genai.types = SimpleNamespace(GenerateContentConfig=lambda **kwargs: kwargs)
    fake_google = types.ModuleType("google"); fake_google.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setattr(config, "LLM_MODE", "gemini")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    item = {"feature": "sensor_1", "data_type": "numeric", "description": "Fallback", "description_source": "system_generated"}
    updated, status = llm.enrich_descriptions([item])
    assert updated == [item]
    assert "RuntimeError" in status

def test_whitespace_only_cells_are_counted_as_missing():
    from app.processing import read_table, profile_dataset
    frame = read_table("whitespace.csv", b"sensor,category\n ,running\n12,   \n")
    assert int(frame.isna().sum().sum()) == 2
    _, _, summary = profile_dataset(frame, {})
    assert summary["total_missing_cells"] == 2

def test_literal_na_labels_are_not_treated_as_missing():
    from app.processing import read_table
    frame = read_table("labels.csv", b"label\nNA\nNULL\nN/A\nunknown\n")
    assert int(frame.isna().sum().sum()) == 0

def test_lowercase_null_token_is_treated_as_missing_but_uppercase_label_is_preserved():
    from app.processing import read_table
    frame = read_table("null_tokens.csv", b"state\nnull\nNULL\nrunning\n")
    assert frame["state"].isna().sum() == 1
    assert frame["state"].iloc[1] == "NULL"
