"""Gemini ranks code-defined actions; only verified IDs reach the results page."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from models import AnalysisRequest
from recommendations import Candidate, Evidence, Suggestion


MODEL = "gemini-3.1-flash-lite"
TIMEOUT_MS = 30_000


class AIError(Exception):
    """The model was unavailable or returned an unsafe selection."""


def validate_reply(
    raw: str, evidence: tuple[Evidence, ...], candidates: tuple[Candidate, ...],
) -> tuple[Suggestion, ...]:
    """Reject malformed, unknown, duplicate, or unsupported selections."""
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise AIError("The AI response was not valid JSON.") from exc
    if not isinstance(payload, dict) or set(payload) != {"recommendations"}:
        raise AIError("The AI response had an unexpected structure.")
    rows = payload["recommendations"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 3:
        raise AIError("The AI response did not contain one to three suggestions.")
    candidate_by_id = {candidate.id: candidate for candidate in candidates}
    evidence_by_id = {item.id: item for item in evidence}
    seen: set[str] = set()
    selected: list[Suggestion] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"action_id", "evidence_ids"}:
            raise AIError("The AI response contained an unexpected suggestion field.")
        action_id, ids = row["action_id"], row["evidence_ids"]
        if not isinstance(action_id, str) or action_id not in candidate_by_id or action_id in seen:
            raise AIError("The AI selected an unknown or duplicate action.")
        candidate = candidate_by_id[action_id]
        if (not isinstance(ids, list) or not ids or
                any(not isinstance(item, str) for item in ids) or
                len(ids) != len(set(ids)) or
                set(ids) != set(candidate.evidence_ids) or
                not set(ids).issubset(evidence_by_id)):
            raise AIError("The AI cited missing or unrelated evidence.")
        selected.append(Suggestion(candidate, tuple(evidence_by_id[item] for item in ids)))
        seen.add(action_id)
    return tuple(selected)


def rank_with_gemini(
    request: AnalysisRequest,
    evidence: tuple[Evidence, ...],
    candidates: tuple[Candidate, ...],
    *,
    api_key: str | None = None,
) -> tuple[Suggestion, ...]:
    """One bounded API call; the model can select IDs but cannot author advice."""
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise AIError("Gemini API key is not configured.")
    if not candidates:
        return ()
    schema = {
        "type": "object",
        "properties": {"recommendations": {
            "type": "array", "minItems": 1, "maxItems": 3,
            "items": {"type": "object", "properties": {
                "action_id": {"type": "string", "enum": [item.id for item in candidates]},
                "evidence_ids": {"type": "array", "minItems": 1,
                                 "items": {"type": "string", "enum": [item.id for item in evidence]}},
            }, "required": ["action_id", "evidence_ids"], "additionalProperties": False},
        }}, "required": ["recommendations"], "additionalProperties": False,
    }
    facts = {
        "crop_entered_by_user": request.crop,
        "growth_stage_entered_by_user": request.growth_stage,
        "evidence": [{"id": item.id, "text": item.text} for item in evidence],
        "candidate_actions": [{"id": item.id, "title": item.title,
                               "action": item.action, "allowed_evidence_ids": item.evidence_ids}
                              for item in candidates],
    }
    instruction = (
        "Rank up to three candidate actions for this selected agricultural analysis area. "
        "Choose only supplied action IDs and cite only the evidence IDs allowed for each action. "
        "Treat crop and stage as user input, not a satellite finding. "
        "Do not infer soil moisture, disease, yield, exact irrigation volumes, or fertilizer doses. "
        "Return only the structured selection.\n" + json.dumps(facts, ensure_ascii=False)
    )
    try:
        with genai.Client(api_key=key, http_options=types.HttpOptions(timeout=TIMEOUT_MS)) as client:
            response = client.models.generate_content(
                model=MODEL,
                contents=instruction,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", response_json_schema=schema,
                    temperature=0.2, max_output_tokens=500,
                ),
            )
        return validate_reply(response.text, evidence, candidates)
    except AIError:
        raise
    except Exception as exc:
        raise AIError("Gemini was unavailable or did not return a usable ranking.") from exc
