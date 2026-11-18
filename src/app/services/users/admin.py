from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.schemas.users.models import User


def change_user_access(session: Session, actor: User, target_id: int, changes: dict) -> User:
    # Serialize admin demotions/deactivations so the last active admin remains.
    active_admin_ids = session.scalars(select(User.id).where(User.role == "admin", User.is_active.is_(True)).order_by(User.id).with_for_update()).all()
    target = session.scalar(select(User).where(User.id == target_id).with_for_update())
    if target is None:
        raise APIError(404, "USER_NOT_FOUND", "User not found.")
    if target.id == actor.id and (changes.get("role", "admin") != "admin" or changes.get("is_active", True) is False):
        raise APIError(403, "SELF_ACCESS_CHANGE_FORBIDDEN", "You cannot remove your own admin access.")
    if target.id in active_admin_ids and len(active_admin_ids) == 1 and (changes.get("role", target.role) != "admin" or changes.get("is_active", target.is_active) is False):
        raise APIError(409, "LAST_ADMIN_REQUIRED", "At least one active admin is required.")
    for field, value in changes.items():
        setattr(target, field, value)
    session.commit()
    session.refresh(target)
    return target
