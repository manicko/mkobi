"""Shared request-body schemas for API operations.

Complements ``responses.py``: where that module holds reusable OpenAPI error
documentation, this module holds reusable Pydantic request models for
operations whose payload is not tied to a domain model.
"""

from pydantic import BaseModel, ConfigDict

__all__ = [
    "TempPasswordRetrievalRequest",
]


class TempPasswordRetrievalRequest(BaseModel):
    """Request body for the temp-password retrieval operation.

    The handle is carried in the body so it never reaches the request line and,
    therefore, never appears in the application access log.
    """

    retrieval_token: str

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "retrieval_token": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            }
        },
    )
