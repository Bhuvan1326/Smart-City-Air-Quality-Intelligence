from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def create(
        cls, items: list[T], total: int, page: int, page_size: int
    ) -> "PaginatedResponse[T]":
        pages = max(1, -(-total // page_size))
        return cls(
            items=items, total=total, page=page, page_size=page_size, pages=pages
        )


class APIResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    message: str | None = None
    errors: list[str] | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: Any | None = None
    code: str | None = None
