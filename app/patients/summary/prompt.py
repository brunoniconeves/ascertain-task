from __future__ import annotations

import json
from typing import Any


def build_patient_summary_prompts(
    *,
    audience: str,
    verbosity: str,
    patient_context: dict[str, Any],
    notes: list[dict[str, Any]],
) -> tuple[str, str]:
    """
    Create (system_prompt, user_prompt) for summary generation.

    Safety / design decisions:
    - System prompt explicitly forbids invention/speculation and enforces neutral tone.
    - User prompt provides only data already exposed by the API (no extra PHI fields).
    - Output is forced to a JSON object with a single field: {"text": "..."}.
    """

    system_prompt = "\n".join(
        [
            "You are a careful clinical documentation assistant.",
            "You must follow these rules:",
            "- Do NOT invent facts, diagnoses, medications, lab values, or timelines.",
            "- Do NOT guess missing information; if unknown, omit it.",
            "- Do NOT speculate about causes or future outcomes.",
            "- Base the summary ONLY on the provided input data.",
            "- Use neutral clinical language. Avoid alarmist or judgmental phrasing.",
            "- If there are contradictions, present them as 'conflicting documentation' without resolving.",
            "- Do not include any content not present in the input.",
            "",
            "Output requirements:",
            "- Output MUST be valid JSON (and nothing else).",
            "- The JSON MUST be an object with exactly one key: 'text'.",
            "- 'text' MUST be a single human-readable narrative paragraph or short set of paragraphs.",
        ]
    )

    # Give the model explicit steering for audience/verbosity. Keep this in user prompt so
    # the system prompt remains stable and security-focused.
    audience_guidance = {
        "clinician": "Use clinical vocabulary and focus on actionable clinical details.",
        "family": "Use plain language; avoid jargon; explain abbreviations if present in notes.",
        "patient": "Use respectful, supportive plain language; avoid blame; avoid heavy jargon.",
        "third_party": "Use neutral, formal tone; focus on documented facts only; avoid sensitive details beyond what is present.",
    }
    verbosity_guidance = {
        "short": "Be brief; prioritize the most important conditions/meds/plans.",
        "medium": "Be concise but cover key diagnoses, medications, observations, and plans.",
        "long": "Include more detail and chronology, while staying coherent and avoiding repetition.",
    }

    user_payload = {
        "audience": audience,
        "verbosity": verbosity,
        "instructions": {
            "audience_style": audience_guidance.get(audience, ""),
            "detail_level": verbosity_guidance.get(verbosity, ""),
        },
        "patient_context": patient_context,
        "notes_chronological": notes,
        "reminders": [
            "Do not add facts that are not explicitly present above.",
            "If a note is file-backed and content_text is null, you cannot infer its content.",
            "Structured SOAP sections are derived and non-authoritative; treat them as helpful hints only.",
        ],
    }

    user_prompt = (
        "Create a patient summary from the following JSON input.\n"
        "Return ONLY JSON: {\"text\": \"...\"}\n\n"
        f"{json.dumps(user_payload, ensure_ascii=False)}"
    )

    return system_prompt, user_prompt


