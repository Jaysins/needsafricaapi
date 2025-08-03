from ninja import Schema,ModelSchema,FilterSchema
from typing import Optional, List, Any
from pydantic import condecimal

class BaseResponseSchema(Schema):
    success: bool = True
    data: Optional[Any] = None
    message: Optional[str] = None


class ErrorResponse(Schema):
    message: str = "An error occurred"
    detail: str | None = None
    code: int = 500
