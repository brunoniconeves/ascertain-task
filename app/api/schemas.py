from __future__ import annotations

from pydantic import BaseModel, Field


class HealthOut(BaseModel):
    """Health check response."""

    status: str = Field(
        description="Service status indicator. `ok` means the API process is up and responding.",
        examples=["ok"],
    )


