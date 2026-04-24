"""API Key Pydantic schemas.

Extracted from api_keys.py for maintainability (Phase 6B).
"""

from typing import Optional

from pydantic import BaseModel, Field


class ApiKeyCreateRequest(BaseModel):
    label: Optional[str] = Field(None, max_length=255, description="Human-readable label")
    environment: str = Field("live", pattern="^(live|test)$", description="live or test")


class ApiKeyResponse(BaseModel):
    id: str
    key_prefix: str
    label: Optional[str] = None
    environment: str
    is_active: bool
    last_used_at: Optional[str] = None
    created_at: Optional[str] = None
    model_config = {"from_attributes": True}


class ApiKeyCreateResponse(BaseModel):
    """Returned only on creation — plaintext key shown ONCE."""

    id: str
    key: str
    key_prefix: str
    label: Optional[str] = None
    environment: str


class ApiKeyCursorResponse(BaseModel):
    """Phase 6B: cursor pagination response."""

    data: list[ApiKeyResponse]
    has_more: bool
