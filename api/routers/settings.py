"""Search settings (agent_settings.yaml) and write-only secrets (.env)."""
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

import agent_settings
from api.models.settings import SearchSettings, settings_warnings
from api.services import secrets

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _role_profiles():
    try:
        from api.services.resume_store import load

        resume, _etag, _warnings = load()
        return resume.role_profiles
    except Exception:
        return None


def _response():
    settings = agent_settings.load()
    return {"settings": settings, "warnings": settings_warnings(settings, _role_profiles())}


@router.get("/search")
def get_search_settings():
    return _response()


@router.put("/search")
def put_search_settings(body: dict[str, Any]):
    payload = body.get("settings", body)
    try:
        validated = SearchSettings.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(422, [{"loc": list(e["loc"]), "msg": e["msg"].removeprefix("Value error, ")}
                                  for e in exc.errors()]) from exc
    agent_settings.save(validated.model_dump(mode="json"))
    return _response()


@router.get("/search/defaults")
def get_default_settings():
    return {"settings": agent_settings.DEFAULTS}


class SecretsPut(BaseModel):
    values: dict[str, str | None]


@router.get("/secrets")
def get_secrets():
    return secrets.describe()


@router.put("/secrets")
def put_secrets(body: SecretsPut):
    try:
        secrets.update(body.values)
    except KeyError as exc:
        raise HTTPException(400, f"{exc.args[0]} is not a setting this app manages.") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return secrets.describe()
