import io
import csv
from typing import Any
import numpy as np
import pandas as pd

ALIASES = {
    "feature_name": ["feature_name", "feature", "column_name", "column", "field", "parameter", "name"],
    "description": ["description", "meaning", "definition", "details"],
    "unit": ["unit", "units", "measurement_unit"],
    "measurement_range": ["measurement_range", "range", "expected_range"],
    "unit_applicable": ["unit_applicable", "unit_required", "has_unit"],
}

def normalize_key(value: Any) -> str:
    return "".join(character for character in str(value).strip().casefold() if character.isalnum())

def _validate_headers(headers: list) -> None:
    cleaned = [str(value).strip() if value is not None else "" for value in headers]
    if not cleaned or any(not value for value in cleaned):
        raise ValueError("Every dataset column must have a non-empty column name.")
    normalized = [normalize_key(value) for value in cleaned]
    if any(not key for key in normalized):
        raise ValueError("Column names must contain at least one letter or number.")
    if len(normalized) != len(set(normalized)):
        raise ValueError("Dataset contains duplicate or ambiguous column names. Rename them before analysis.")

def _normalize_blank_cells(frame: pd.DataFrame) -> pd.DataFrame:
    # Treat empty and whitespace-only cells as missing, while preserving literal labels
    # such as NA, NULL, N/A and unknown.
    return frame.replace(r"^\s*$", np.nan, regex=True)


def read_table(filename: str, content: bytes) -> pd.DataFrame:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix == "csv":
        header = next(csv.reader(io.StringIO(content.decode("utf-8-sig"))), [])
        _validate_headers(header)
        frame = pd.read_csv(io.BytesIO(content), encoding="utf-8-sig", keep_default_na=False,
                            na_values=["", "null"], skip_blank_lines=False)
        return _normalize_blank_cells(frame)
    if suffix in ("xlsx", "xlsm"):
        from openpyxl import load_workbook
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        try:
            worksheet = workbook.active
            header = list(next(worksheet.iter_rows(min_row=1, max_row=1, values_only=True), ()))
            while header and (header[-1] is None or str(header[-1]).strip() == ""):
                header.pop()
            _validate_headers(header)
        finally:
            workbook.close()
        frame = pd.read_excel(io.BytesIO(content), engine="openpyxl", keep_default_na=False, na_values=["", "null"])
        return _normalize_blank_cells(frame)
    raise ValueError("Unsupported file type. Upload a CSV or XLSX file.")

def _metadata_column(df: pd.DataFrame, key: str):
    normalized = {normalize_key(c): c for c in df.columns}
    for alias in ALIASES[key]:
        if normalize_key(alias) in normalized:
            return normalized[normalize_key(alias)]
    return None

def _clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()

def _parse_bool(value, field_name: str):
    text = _clean(value).casefold()
    if not text:
        return None
    if text in {"true", "yes", "y", "1", "required"}:
        return True
    if text in {"false", "no", "n", "0", "not_applicable", "not applicable"}:
        return False
    raise ValueError(f"Metadata field '{field_name}' must be yes/no or true/false.")

def _is_datetime_series(series: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    values = series.dropna()
    if values.empty or not (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
        return False
    # Require date-like separators before parsing to avoid treating ordinary numbers as dates.
    candidates = values.astype(str).str.strip()
    date_like = candidates.str.contains(r"[-/T:]")
    if date_like.mean() < 0.8:
        return False
    parsed = pd.to_datetime(candidates, errors="coerce", format="mixed", utc=True)
    return parsed.notna().mean() >= 0.8

def parse_metadata(df: pd.DataFrame | None) -> dict[str, dict]:
    if df is None:
        return {}
    name_col = _metadata_column(df, "feature_name")
    if name_col is None:
        raise ValueError("Metadata file needs a feature_name column (or feature/column_name/field).")
    desc_col = _metadata_column(df, "description")
    unit_col = _metadata_column(df, "unit")
    range_col = _metadata_column(df, "measurement_range")
    applicable_col = _metadata_column(df, "unit_applicable")
    result = {}
    for _, row in df.iterrows():
        name = str(row[name_col]).strip()
        if not name or name.lower() == "nan":
            continue
        key = normalize_key(name)
        if key in result:
            raise ValueError(f"Metadata contains duplicate or ambiguous feature name: {name}")
        result[key] = {
            "feature_name": name,
            "description": _clean(row[desc_col]) if desc_col else "",
            "unit": _clean(row[unit_col]) if unit_col else "",
            "measurement_range": _clean(row[range_col]) if range_col else "",
            "unit_applicable": _parse_bool(row[applicable_col], "unit_applicable") if applicable_col else None,
        }
    return result

def _num(value):
    if pd.isna(value) or not np.isfinite(value):
        return None
    return round(float(value), 6)

def _generated_description(feature: str, data_type: str, unit: str = "") -> str:
    """Create a concise, conservative description from an explicit feature name."""
    name = str(feature).strip()
    key = normalize_key(name)
    known = {
        "formatteddate": "Date and time when the weather observation was recorded.",
        "summary": "Text summary describing the observed weather conditions.",
        "preciptype": "Type of precipitation recorded, such as rain or snow.",
        "temperaturec": "Air temperature recorded in degrees Celsius.",
        "apparenttemperaturec": "Apparent or feels-like air temperature in degrees Celsius.",
        "humidity": "Relative humidity, expressed as a proportion from 0 to 1 in this dataset.",
        "windspeedkmh": "Wind speed recorded in kilometres per hour.",
        "windbearingdegrees": "Wind direction expressed as a bearing in degrees.",
        "visibilitykm": "Visibility distance recorded in kilometres.",
        "loudcover": "Numeric values recorded for the Loud Cover feature; its meaning is not defined by the dataset name.",
        "pressuremillibars": "Atmospheric pressure recorded in millibars.",
        "dailysummary": "Text summary describing the weather over the day.",
    }
    if key in known:
        return known[key]

    # Clear measurement names can be described without assigning an unknown sensor meaning.
    readable = name
    if data_type == "datetime":
        return f"Date/time values recorded in {readable}; the event represented is not specified."
    if data_type == "categorical/text":
        return f"Text or category values recorded for {readable}; the specific business meaning is not specified."
    if data_type == "numeric":
        return f"The {readable} column contains numeric values; the measured quantity is not confirmed."
    return f"Values recorded for {readable}; the feature meaning cannot be determined from the available data."

def profile_dataset(df: pd.DataFrame, metadata: dict[str, dict]) -> tuple[list[dict], list[dict], dict]:
    dictionary, missing = [], []
    rows, cols = df.shape
    duplicate_rows = int(df.duplicated().sum()) if rows else 0
    for col in df.columns:
        series = df[col]
        non_null = series.dropna()
        is_datetime = _is_datetime_series(series)
        numeric = pd.to_numeric(series, errors="coerce") if not is_datetime else pd.Series(dtype="float64")
        is_numeric = bool(not is_datetime and len(non_null) and not pd.api.types.is_bool_dtype(series)
                          and numeric.notna().sum() / max(1, len(non_null)) >= 0.9)
        is_unknown = len(non_null) == 0
        meta = metadata.get(normalize_key(col), {})
        description, unit = meta.get("description", ""), meta.get("unit", "")
        unit_applicable = meta.get("unit_applicable")
        if is_numeric:
            vals = numeric.dropna()
            q1 = vals.quantile(0.25) if len(vals) else None
            q3 = vals.quantile(0.75) if len(vals) else None
            iqr = (q3 - q1) if len(vals) else 0
            stats = {
                "min": _num(vals.min()) if len(vals) else None,
                "max": _num(vals.max()) if len(vals) else None,
                "mean": _num(vals.mean()) if len(vals) else None,
                "median": _num(vals.median()) if len(vals) else None,
                "std": _num(vals.std()) if len(vals) > 1 else None,
                "outlier_count_iqr": int(((vals < q1 - 1.5 * iqr) | (vals > q3 + 1.5 * iqr)).sum()) if len(vals) else 0,
            }
            data_type, kind = "numeric", "numeric values"
        else:
            stats = {"min": None, "max": None, "mean": None, "median": None, "std": None, "outlier_count_iqr": None}
            if is_datetime and len(non_null):
                parsed_dates = pd.to_datetime(non_null, errors="coerce", format="mixed", utc=True)
                valid_dates = parsed_dates.dropna()
                stats["min"] = valid_dates.min().isoformat() if len(valid_dates) else None
                stats["max"] = valid_dates.max().isoformat() if len(valid_dates) else None
            data_type = "unknown (all values missing)" if is_unknown else (
                "datetime" if is_datetime else "categorical/text")
            kind = "values of unknown type (all values are missing)" if is_unknown else (
                "date/time values" if is_datetime else "categorical or text values")
        null_count = int(series.isna().sum())
        generated_description = _generated_description(str(col), data_type, unit)
        row = {
            "feature": str(col), "data_type": data_type,
            "description": description if description else generated_description,
            "unit": unit, "measurement_range": meta.get("measurement_range", ""),
            "unit_applicable": unit_applicable if is_numeric else False,
            "count": int(rows), "null_count": null_count,
            "null_percent": round(null_count / rows * 100, 2) if rows else 0.0,
            "unique_count": int(series.nunique(dropna=True)),
            "non_numeric_count": int(len(non_null) - numeric.notna().sum()) if is_numeric else 0,
            **stats,
            "description_source": "user_supplied" if description else "system_generated",
            "unit_source": "user_supplied" if unit else "unknown",
            "completeness": (
                "Unknown" if is_unknown or (is_numeric and not unit and unit_applicable is None)
                else "Incomplete" if is_numeric and unit_applicable is True and not unit
                else "Complete"
            ),
        }
        dictionary.append(row)
        if is_numeric and not unit:
            if unit_applicable is True:
                missing.append({"feature": str(col), "missing_field": "unit", "reason": "A unit is marked as applicable but was not supplied."})
            elif unit_applicable is None:
                missing.append({"feature": str(col), "missing_field": "unit_applicability", "reason": "Confirm whether this numeric feature represents a measured quantity requiring a unit; identifiers may not have units."})
        if is_unknown:
            missing.append({"feature": str(col), "missing_field": "data_type", "reason": "All values are missing, so the data type and applicable unit cannot be determined."})
    summary = {
        "rows": int(rows), "columns": int(cols), "duplicate_rows": duplicate_rows,
        "total_missing_cells": int(df.isna().sum().sum()),
        "complete_features": sum(1 for x in dictionary if x["completeness"] == "Complete"),
        "documented_features": sum(1 for x in dictionary if x["description_source"] == "user_supplied"),
        "features_with_descriptions": sum(1 for x in dictionary if bool(x.get("description"))),
        "user_described_features": sum(1 for x in dictionary if x["description_source"] == "user_supplied"),
    }
    return dictionary, missing, summary
