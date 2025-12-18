from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PatientSortField = Literal["name", "date_of_birth", "created_at"]
SortOrder = Literal["asc", "desc"]


class PatientCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=255,
        description="Patient's display name (not necessarily legal name).",
        examples=["Jane Doe"],
    )
    date_of_birth: date = Field(
        description="Date of birth in ISO format (YYYY-MM-DD).",
        examples=["1980-01-31"],
    )
    # Optional MRN for interoperability with upstream systems.
    # If omitted, it may be auto-generated (configurable).
    mrn: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description=(
            "Medical Record Number. If omitted and auto-generation is enabled, the server will "
            "generate one."
        ),
        examples=["MRN-00001234"],
    )


class PatientUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Updated patient name. Omit to keep existing.",
        examples=["Jane Doe"],
    )
    date_of_birth: date | None = Field(
        default=None,
        description="Updated date of birth (YYYY-MM-DD). Omit to keep existing.",
        examples=["1980-01-31"],
    )
    # Accept MRN in the payload so we can return a controlled 400 instead of silently ignoring it.
    # MRN is immutable and cannot be updated via the API (even if currently NULL).
    mrn: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="MRN is immutable. Providing it here will result in a validation error.",
        examples=["MRN-00001234"],
    )


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Patient identifier (UUID).")
    mrn: str = Field(description="Medical Record Number (MRN).")
    name: str = Field(description="Patient name.")
    date_of_birth: date = Field(description="Date of birth (YYYY-MM-DD).")
    created_at: datetime = Field(description="Record creation timestamp (UTC).")
    updated_at: datetime = Field(description="Record last update timestamp (UTC).")


class PatientListItemOut(BaseModel):
    """
    List item schema intentionally excludes MRN.

    Exposure rule: MRN is returned on patient *detail* endpoints and summary only.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Patient identifier (UUID).")
    name: str = Field(description="Patient name.")
    date_of_birth: date = Field(description="Date of birth (YYYY-MM-DD).")
    created_at: datetime = Field(description="Record creation timestamp (UTC).")
    updated_at: datetime = Field(description="Record last update timestamp (UTC).")


class PatientListOut(BaseModel):
    items: list[PatientListItemOut] = Field(description="Page of patient list items.")
    limit: int = Field(description="Page size requested.", examples=[50])
    next_cursor: str | None = Field(
        default=None,
        description="Opaque cursor for the next page. Omitted/null when there are no more results.",
    )
