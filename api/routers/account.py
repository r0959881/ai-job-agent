"""The signed-in user's account: who they are, exporting what the server stores, deleting it all."""
import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

import agent_settings
from api import store
from api.auth import public_user, uses_project_files
from api.services import resume_store, secrets

router = APIRouter(prefix="/api/account", tags=["account"])


def _user(request: Request):
    user_id = request.session.get("user_id")
    user = store.get_user(user_id) if user_id else None
    if user is None:
        raise HTTPException(401, "Please sign in.")
    return user


@router.get("")
def me(request: Request):
    return {"user": public_user(_user(request))}


@router.get("/export")
def export(request: Request):
    """Everything the server keeps about the user, as JSON. API keys are listed but never included."""
    user = _user(request)
    payload = {
        "exported_at": datetime.now(UTC).isoformat(),
        "user": public_user(user) | {"created_at": user["created_at"], "last_login_at": user["last_login_at"]},
        "resume_yaml": resume_store.read_text(),
        "resume_versions": resume_store.list_backups(),
        "search_settings": agent_settings.load(),
        "api_keys_saved": [item["key"] for item in secrets.describe() if item["set"]],
    }
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return Response(json.dumps(payload, indent=2, ensure_ascii=False), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="ai_job_agent_account_{stamp}.json"'})


class DeleteBody(BaseModel):
    confirm: str


@router.post("/delete")
def delete(body: DeleteBody, request: Request):
    """Delete the account, resume, settings and keys from the server. Files on the user's device stay."""
    if body.confirm != "DELETE":
        raise HTTPException(400, "Type DELETE to confirm.")
    if uses_project_files(request.session):
        raise HTTPException(400, "The local account uses this PC's project files and cannot be deleted.")
    store.delete_user(_user(request)["id"])
    request.session.clear()
    return {"deleted": True}
