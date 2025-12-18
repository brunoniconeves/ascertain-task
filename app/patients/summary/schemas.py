from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SummaryAudience = Literal["clinician", "family", "patient", "third_party"]
SummaryVerbosity = Literal["short", "medium", "long"]


class PatientHeading(BaseModel):
    name: str
    age: int = Field(ge=0)
    mrn: str | None = None


class SummaryContent(BaseModel):
    audience: SummaryAudience
    verbosity: SummaryVerbosity
    text: str = Field(min_length=1)


class PatientSummaryOut(BaseModel):
    patient_heading: PatientHeading
    summary: SummaryContent


class _LLMSummaryJSON(BaseModel):
    """
    Internal schema for validating the LLM response payload.

    We keep this minimal to reduce the chance of leaking PHI or accepting extra fields.
    """

    text: str = Field(min_length=1)


