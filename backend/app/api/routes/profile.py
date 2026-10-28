"""The signed-in user's own profile. Consent-gated: GET shows what is stored, PUT stores it only with consent=true, DELETE erases it."""

from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import current_user
from app.core.config import get_settings
from app.services.orders import User
from app.services.profile import Profile, ProfileStore, ProfileWrite

router = APIRouter(tags=["profile"])


@lru_cache
def _store(path: str) -> ProfileStore:
    return ProfileStore(path)


def get_profile_store() -> ProfileStore:
    return _store(get_settings().profile_db)


Store = Annotated[ProfileStore, Depends(get_profile_store)]
Me = Annotated[User, Depends(current_user)]


@router.get("/me/profile")
def read_profile(user: Me, store: Store) -> dict:
    saved = store.get(user.id)
    return {"stored": saved is not None, "consent_at": saved["consent_at"] if saved else None, "profile": saved["profile"] if saved else None,
            "account": {"name": user.name, "email": user.email, "company": user.customer_name}}


@router.put("/me/profile")
def write_profile(body: ProfileWrite, user: Me, store: Store) -> dict:
    if not body.consent:
        store.erase(user.id)
    else:
        store.put(user.id, Profile.model_validate(body.model_dump(exclude={"consent"})))
    return read_profile(user, store)


@router.delete("/me/profile", status_code=200)
def erase_profile(user: Me, store: Store) -> dict:
    store.erase(user.id)
    return read_profile(user, store)
