"""Health of the user's integrations and connection tests (Groq, Adzuna)."""
import requests
from fastapi import APIRouter, HTTPException

import agent_settings
from api.services import integrations, secrets

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


@router.get("/status")
def status():
    return integrations.status()


@router.post("/{name}/test")
def test_integration(name: str):
    if name == "groq":
        from tailor import GroqConfigError, describe_error, get_client

        try:
            models = get_client().models.list()
            count = len(getattr(models, "data", []) or [])
            return {"ok": True, "message": f"Groq answered ({count} models available)."}
        except GroqConfigError as exc:
            return {"ok": False, "message": str(exc).removeprefix("❌ ")}
        except Exception as exc:
            return {"ok": False, "message": f"Groq test failed: {describe_error(exc)}."}
    if name == "adzuna":
        app_id, app_key = secrets.get("ADZUNA_APP_ID"), secrets.get("ADZUNA_APP_KEY")
        if not app_id or not app_key:
            return {"ok": False, "message": "Add both the Adzuna app ID and key first."}
        country = agent_settings.get("adzuna")["country"]
        try:
            response = requests.get(f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
                                    params={"app_id": app_id, "app_key": app_key, "results_per_page": 1,
                                            "what": "data"}, timeout=20)
            if response.status_code in {401, 403}:
                return {"ok": False, "message": "Adzuna rejected the app ID or key."}
            response.raise_for_status()
            total = response.json().get("count")
            return {"ok": True, "message": f"Adzuna answered{f' ({total} “data” jobs listed)' if total else ''}."}
        except (requests.RequestException, ValueError) as exc:
            return {"ok": False, "message": f"Adzuna could not be reached: {exc}"}
    raise HTTPException(404, f"Unknown integration “{name}”.")
