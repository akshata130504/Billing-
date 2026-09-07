"""Pagination helpers shared by every list endpoint."""
from dataclasses import dataclass
from math import ceil
from typing import Any, Callable, Generic, List, Optional, Sequence, TypeVar

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")

MAX_PAGE_SIZE = 100


@dataclass
class PageParams:
    page: int
    page_size: int
    sort: Optional[str]

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    sort: Optional[str] = Query(None, description="field or -field for descending"),
) -> PageParams:
    return PageParams(page=page, page_size=page_size, sort=sort)


def apply_sort(stmt: Select, model: Any, sort: Optional[str], allowed: Sequence[str], default: str) -> Select:
    """Order by `sort` if it is one of `allowed`, else by `default`. Leading '-' = descending."""
    key = sort or default
    desc = key.startswith("-")
    field = key.lstrip("-")
    if field not in allowed:
        field = default.lstrip("-")
        desc = default.startswith("-")
    column = getattr(model, field)
    return stmt.order_by(column.desc() if desc else column.asc())


@dataclass
class Page(Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return max(1, ceil(self.total / self.page_size)) if self.total else 0

    def to_response(self, serializer: Callable[[T], Any]) -> dict:
        return {
            "items": [serializer(i) for i in self.items],
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "total_pages": self.total_pages,
        }


def paginate(db: Session, stmt: Select, params: PageParams) -> Page:
    """Run a count + page query for an ORM select of a single entity."""
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = db.scalar(count_stmt) or 0
    items = list(db.scalars(stmt.offset(params.offset).limit(params.page_size)).unique().all())
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)
