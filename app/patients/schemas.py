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


class PatientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    date_of_birth: date | None = None


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    date_of_birth: date
    created_at: datetime
    updated_at: datetime


class PatientListOut(BaseModel):
    items: list[PatientOut]
    limit: int
    next_cursor: str | None = None
