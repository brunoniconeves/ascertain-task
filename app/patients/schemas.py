from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PatientSortField = Literal["name", "date_of_birth", "created_at"]
SortOrder = Literal["asc", "desc"]


class PatientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    date_of_birth: date
    # Optional MRN for interoperability with upstream systems.
    # If omitted, it may be auto-generated (configurable).
    mrn: str | None = Field(default=None, min_length=1, max_length=50)


class PatientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    date_of_birth: date | None = None
    # Accept MRN in the payload so we can return a controlled 400 instead of silently ignoring it.
    # MRN is immutable and cannot be updated via the API (even if currently NULL).
    mrn: str | None = Field(default=None, min_length=1, max_length=50)


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mrn: str
    name: str
    date_of_birth: date
    created_at: datetime
    updated_at: datetime


class PatientListItemOut(BaseModel):
    """
    List item schema intentionally excludes MRN.

    Exposure rule: MRN is returned on patient *detail* endpoints and summary only.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    date_of_birth: date
    created_at: datetime
    updated_at: datetime


class PatientListOut(BaseModel):
    items: list[PatientListItemOut]
    limit: int
    next_cursor: str | None = None
