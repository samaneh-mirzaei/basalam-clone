from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.schemas.categories.models import Category


def lock_taxonomy(session: Session) -> None:
    # Serialize category writes so competing parent changes cannot create cycles.
    session.execute(text("SELECT pg_advisory_xact_lock(721804221)"))


def active_parent(session: Session, parent_id: int | None) -> Category | None:
    if parent_id is None:
        return None
    parent = session.get(Category, parent_id)
    if parent is None or not parent.is_active:
        raise APIError(404, "CATEGORY_PARENT_NOT_FOUND", "Active parent category not found.")
    return parent


def commit_category(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise APIError(409, "CATEGORY_SLUG_EXISTS", "Category slug already exists.") from exc


def create_category(session: Session, values: dict) -> Category:
    lock_taxonomy(session)
    active_parent(session, values.get("parent_id"))
    category = Category(**values)
    session.add(category)
    commit_category(session)
    session.refresh(category)
    return category


def edit_category(session: Session, category_id: int, changes: dict) -> Category:
    lock_taxonomy(session)
    category = session.scalar(select(Category).where(Category.id == category_id).with_for_update())
    if category is None:
        raise APIError(404, "CATEGORY_NOT_FOUND", "Category not found.")
    next_parent_id = changes.get("parent_id", category.parent_id)
    if next_parent_id is not None:
        active_parent(session, next_parent_id)
        ancestor_id = next_parent_id
        while ancestor_id is not None:
            if ancestor_id == category.id:
                raise APIError(409, "CATEGORY_CYCLE", "A category cannot become its own ancestor.")
            ancestor_id = session.get(Category, ancestor_id).parent_id
    if changes.get("is_active") is False and category.is_active:
        active_child = session.scalar(select(Category.id).where(Category.parent_id == category.id, Category.is_active.is_(True)))
        if active_child is not None:
            raise APIError(409, "CATEGORY_HAS_ACTIVE_CHILDREN", "Deactivate child categories first.")
    for field, value in changes.items():
        setattr(category, field, value)
    commit_category(session)
    session.refresh(category)
    return category
