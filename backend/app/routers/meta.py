from fastapi import APIRouter
from pydantic import BaseModel

from app.validators import CATEGORIES, EVENT_TYPES

router = APIRouter(prefix="/meta", tags=["meta"])


class CategoriesOut(BaseModel):
    categories: list[str]
    event_types: list[str]


@router.get("/categories", response_model=CategoriesOut, summary="The 13 categories (and event types)")
async def categories() -> CategoriesOut:
    return CategoriesOut(categories=CATEGORIES, event_types=EVENT_TYPES)
