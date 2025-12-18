from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

SoapConfidence = Literal["high", "partial"]


@dataclass(frozen=True)
class SoapParseResult:
    """
    Derived, non-authoritative structured representation of a SOAP-formatted note.

    Important: the original note content remains the source of truth; this result is
    best-effort and must not be used to mutate the raw note.
    """

    schema: str
    parsed_from: str
    parser_version: str
    confidence: SoapConfidence
    sections: dict[str, str | None]


_SOAP_MARKER_RE = re.compile(r"(?m)^\s*([SOAPsoap])\s*:\s*")


def parse_soap(text: str) -> SoapParseResult | None:
    """
    Deterministically parse SOAP sections from raw text using explicit markers:
    S:, O:, A:, P: (case-insensitive, at start of line with optional whitespace).

    - No inference, guessing, or NLP.
    - Missing sections are allowed.
    - Returns None when no SOAP markers are detected at all.
    """

    if not text:
        return None

    matches = list(_SOAP_MARKER_RE.finditer(text))
    if not matches:
        return None

    key_map = {
        "S": "subjective",
        "O": "objective",
        "A": "assessment",
        "P": "plan",
    }

    # Initialize with stable keys to keep schema predictable.
    sections: dict[str, str | None] = {v: None for v in key_map.values()}

    for idx, m in enumerate(matches):
        marker = m.group(1).upper()
        section_key = key_map.get(marker)
        if section_key is None:
            # Shouldn't happen given regex, but keep deterministic.
            continue

        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        chunk = text[start:end]

        # Preserve original content exactly as captured (no trimming/normalization).
        if sections[section_key] is None:
            sections[section_key] = chunk
        else:
            # Deterministic handling for repeated markers: concatenate content in order.
            sections[section_key] = f"{sections[section_key]}\n{chunk}"

    present = [k for k, v in sections.items() if v not in (None, "")]
    if not present:
        return None

    confidence: SoapConfidence = "high" if len(present) == 4 else "partial"

    return SoapParseResult(
        schema="soap_v1",
        parsed_from="text",
        parser_version="v1",
        confidence=confidence,
        sections=sections,
    )
