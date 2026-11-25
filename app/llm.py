"""Optional Gemini-backed feature description generation.

Only compact column-level evidence is sent to Gemini. Dataset rows are never sent.
User-provided descriptions are preserved and never included in model requests.
"""
import json
import httpx  # retained for the optional OpenAI-compatible adapter and its tests
from . import config


def _evidence_for(missing: list[dict]) -> list[dict]:
    return [{
        "feature": item["feature"],
        "data_type": item["data_type"],
        "observed_min": item.get("min"),
        "observed_max": item.get("max"),
        "observed_mean": item.get("mean"),
        "unit": item.get("unit") or None,
        "sample_categories": item.get("top_values", [])[:5] if isinstance(item.get("top_values"), list) else [],
    } for item in missing]


def _prompt(evidence: list[dict]) -> str:
    return (
        "Create concise data-dictionary descriptions for the supplied dataset columns. "
        "Return ONLY valid JSON in this exact shape: "
        '{"descriptions":[{"feature":"exact input feature name","description":"one short sentence"}]}. '
        "Include each feature exactly once and preserve feature names exactly. Use only the supplied evidence. "
        "You may explain an obvious meaning explicitly present in a feature name, for example Temperature (C). "
        "Do not invent sensor purpose, equipment, process, measurement meaning, units, causal explanations, "
        "or business meaning. For ambiguous names such as ch_01, X17 or sensor_17, explicitly state that "
        "the specific measurement/purpose is not specified. Observed min/max are dataset observations, "
        "not approved operating limits. Keep each description under 25 words.\n\n"
        f"Column evidence:\n{json.dumps(evidence, ensure_ascii=False, default=str)}"
    )


def _validate_and_apply(dictionary: list[dict], missing: list[dict], raw: str, model_name: str):
    payload = json.loads(raw)
    entries = payload.get("descriptions") if isinstance(payload, dict) else None
    if not isinstance(entries, list) or len(entries) != len(missing):
        raise ValueError("Unexpected number of generated descriptions")
    by_feature = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid description entry")
        feature, description = entry.get("feature"), entry.get("description")
        if not isinstance(feature, str) or not isinstance(description, str) or not description.strip() or len(description) > 300:
            raise ValueError("Generated description is empty or too long")
        if feature in by_feature:
            raise ValueError("Duplicate generated feature")
        by_feature[feature] = description.strip()
    expected = {item["feature"] for item in missing}
    if set(by_feature) != expected:
        raise ValueError("Generated description feature coverage is invalid")
    updated = []
    for item in dictionary:
        clone = dict(item)
        if clone.get("description_source") != "user_supplied":
            clone["description"] = by_feature[clone["feature"]]
            clone["description_source"] = "ai_generated"
        updated.append(clone)
    return updated, f"Descriptions generated using {model_name}; user descriptions preserved"


def _generate_with_gemini(dictionary: list[dict], missing: list[dict]):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    model_name = config.GEMINI_MODEL or "gemini-2.5-flash"
    response = client.models.generate_content(
        model=model_name,
        contents=_prompt(_evidence_for(missing)),
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
        ),
    )
    if not getattr(response, "text", None):
        raise ValueError("Gemini returned an empty response")
    return _validate_and_apply(dictionary, missing, response.text, model_name)


def _generate_with_openai_compatible(dictionary: list[dict], missing: list[dict]):
    response = httpx.post(
        f"{config.LLM_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
        json={"model": config.LLM_MODEL, "temperature": 0,
              "response_format": {"type": "json_object"},
              "messages": [{"role": "system", "content": "Follow the user's strict evidence-only description instructions."},
                           {"role": "user", "content": _prompt(_evidence_for(missing))}]},
        timeout=35.0,
    )
    response.raise_for_status()
    raw = response.json()["choices"][0]["message"]["content"]
    return _validate_and_apply(dictionary, missing, raw, config.LLM_MODEL)


def enrich_descriptions(dictionary: list[dict]) -> tuple[list[dict], str]:
    missing = [item for item in dictionary if item.get("description_source") != "user_supplied"]
    if not missing:
        return dictionary, "All descriptions were supplied by the user; preserved unchanged"

    try:
        if config.LLM_MODE == "gemini" and config.GEMINI_API_KEY:
            return _generate_with_gemini(dictionary, missing)
        if (config.LLM_MODE == "openai_compatible" and config.LLM_BASE_URL
                and config.LLM_API_KEY and config.LLM_MODEL):
            return _generate_with_openai_compatible(dictionary, missing)
        return dictionary, "AI is not configured — safe local descriptions shown"
    except Exception as exc:
        # Keep application available if provider is offline, rate-limited or misconfigured.
        return dictionary, f"AI description generation unavailable — safe system-generated descriptions retained ({type(exc).__name__})"
