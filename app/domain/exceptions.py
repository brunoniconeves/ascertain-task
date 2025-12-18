from __future__ import annotations


class BusinessValidationError(Exception):
    """Raised when a domain/business rule is violated."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


