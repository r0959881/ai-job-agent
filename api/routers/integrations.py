"""Integration health, connection tests and the Gmail OAuth web flow."""
from fastapi import APIRouter

from api.services import integrations

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


@router.get("/status")
def status():
    return integrations.status()
