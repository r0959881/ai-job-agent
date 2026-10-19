"""Gmail OAuth web flow (Google mocked), search settings, secrets and data tools."""
import io
import json
import os
import zipfile
from urllib.parse import parse_qs, urlparse

import pytest

import config

CLIENT = {"installed": {"client_id": "id.apps.googleusercontent.com", "client_secret": "secret",
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token", "redirect_uris": ["http://localhost"]}}


@pytest.fixture
def credentials(project_root):
    (project_root / "credentials.json").write_text(json.dumps(CLIENT))


def location(response):
    assert response.status_code == 302, response.text
    return response.headers["location"]


def test_connect_redirects_to_google_with_state_pkce_and_offline_consent(client, credentials):
    url = urlparse(location(client.get("/api/integrations/gmail/connect", follow_redirects=False)))
    query = parse_qs(url.query)
    assert url.netloc == "accounts.google.com"
    assert query["access_type"] == ["offline"] and query["prompt"] == ["consent"]
    assert query["scope"] == ["https://www.googleapis.com/auth/gmail.readonly"]
    assert query["redirect_uri"] == ["http://127.0.0.1/api/integrations/gmail/callback"]
    assert query["code_challenge_method"] == ["S256"] and len(query["code_challenge"][0]) > 40
    assert len(query["state"][0]) >= 24


def test_connect_without_credentials_explains(client):
    target = location(client.get("/api/integrations/gmail/connect", follow_redirects=False))
    assert "gmail=error" in target and "credentials.json" in target


class FakeCreds:
    refresh_token = "refresh-1"
    token = "access-1"
    expiry = None
    scopes = ["https://www.googleapis.com/auth/gmail.readonly"]

    def to_json(self):
        return json.dumps({"token": self.token, "refresh_token": self.refresh_token, "client_id": "id",
                           "client_secret": "secret", "scopes": self.scopes})


class FakeFlow:
    instances = []

    def __init__(self, redirect_uri, state=None):
        self.redirect_uri, self.state = redirect_uri, state
        self.code_verifier = None
        self.fetched = None
        self.credentials = FakeCreds()
        FakeFlow.instances.append(self)

    def authorization_url(self, **kwargs):
        return f"https://accounts.google.com/o/oauth2/auth?state={kwargs['state']}", kwargs["state"]

    def fetch_token(self, code):
        self.fetched = (code, self.code_verifier)


def test_callback_rejects_a_state_mismatch_and_writes_nothing(client, credentials, monkeypatch, project_root):
    from api.integrations import gmail

    monkeypatch.setattr(gmail, "_flow", lambda redirect_uri, state=None: FakeFlow(redirect_uri, state))
    location(client.get("/api/integrations/gmail/connect", follow_redirects=False))
    target = location(client.get("/api/integrations/gmail/callback?state=forged&code=abc", follow_redirects=False))
    assert "gmail=error" in target and "expired" in target
    assert not (project_root / "token.json").exists()


def test_callback_exchanges_the_code_with_pkce_and_saves_the_token(client, credentials, monkeypatch, project_root):
    from api.integrations import gmail
    from gmail_parser import read_gmail_state

    FakeFlow.instances.clear()
    monkeypatch.setattr(gmail, "_flow", lambda redirect_uri, state=None: FakeFlow(redirect_uri, state))
    monkeypatch.setattr(gmail, "profile_email", lambda creds: "me@example.com")
    target = location(client.get("/api/integrations/gmail/connect", follow_redirects=False))
    state = parse_qs(urlparse(target).query)["state"][0]
    verifier = FakeFlow.instances[0].code_verifier

    target = location(client.get(f"/api/integrations/gmail/callback?state={state}&code=the-code", follow_redirects=False))
    assert target == "/settings/integrations?gmail=connected"
    assert FakeFlow.instances[-1].fetched == ("the-code", verifier)
    token = json.loads((project_root / "token.json").read_text())
    assert token["refresh_token"] == "refresh-1"
    state_file = read_gmail_state()
    assert state_file["status"] == "connected" and state_file["email"] == "me@example.com"
    # The same state cannot be replayed.
    replay = location(client.get(f"/api/integrations/gmail/callback?state={state}&code=x", follow_redirects=False))
    assert "gmail=error" in replay


def test_return_path_is_kept_local(client, credentials, monkeypatch):
    from api.integrations import gmail

    monkeypatch.setattr(gmail, "_flow", lambda redirect_uri, state=None: FakeFlow(redirect_uri, state))
    monkeypatch.setattr(gmail, "profile_email", lambda creds: "me@example.com")
    for wanted, expected in (("/onboarding?step=connect", "/onboarding?step=connect&gmail=connected"),
                             ("https://evil.example/x", "/settings/integrations?gmail=connected"),
                             ("//evil.example", "/settings/integrations?gmail=connected")):
        target = location(client.get(f"/api/integrations/gmail/connect?return_to={wanted}", follow_redirects=False))
        state = parse_qs(urlparse(target).query)["state"][0]
        done = location(client.get(f"/api/integrations/gmail/callback?state={state}&code=c", follow_redirects=False))
        assert done == expected


def test_denied_consent_is_friendly(client):
    target = location(client.get("/api/integrations/gmail/callback?error=access_denied", follow_redirects=False))
    assert "gmail=denied" in target and "cancelled" in target


def test_refresh_error_marks_reauth_required(client, credentials, monkeypatch, project_root):
    from google.auth.exceptions import RefreshError

    from api.integrations import gmail

    class Expired(FakeCreds):
        expired = True

        def refresh(self, _request):
            raise RefreshError("invalid_grant: Token has been expired or revoked.")

    (project_root / "token.json").write_text("{}")
    monkeypatch.setattr(gmail, "load_credentials", lambda: Expired())
    body = client.get("/api/integrations/gmail/status").json()
    assert body["state"] == "reauth_required" and "Testing mode" in body["reason"]
    assert client.get("/api/integrations/status").json()["gmail"]["status"] == "warning"


def test_server_path_never_opens_a_browser(project_root, monkeypatch):
    import gmail_parser

    def no_browser(*_a, **_k):
        raise AssertionError("browser opened")

    monkeypatch.setattr(gmail_parser.InstalledAppFlow, "from_client_secrets_file", no_browser)
    (project_root / "credentials.json").write_text(json.dumps(CLIENT))
    with pytest.raises(gmail_parser.GmailAuthRequired) as error:
        gmail_parser.get_gmail_service(interactive=False)
    assert error.value.status == "not_connected"


def test_status_and_test_when_not_connected(client, credentials):
    status = client.get("/api/integrations/gmail/status").json()
    assert status["state"] == "not_connected" and status["credentials_present"] and status["client_type"] == "installed"
    response = client.post("/api/integrations/gmail/test")
    assert response.status_code == 409 and "not connected" in response.json()["detail"]["message"]


def test_gmail_test_counts_alerts_without_saving(client, credentials, monkeypatch):
    from helpers import FakeGmailService

    import gmail_parser

    service = FakeGmailService()
    monkeypatch.setattr(gmail_parser, "get_gmail_service", lambda interactive=True: service)
    result = client.post("/api/integrations/gmail/test").json()
    assert result == {"ok": True, "email": "me@example.com", "count": 1, "query": service.queries[0]}
    assert client.get("/api/jobs").json()["total"] == 0


def test_disconnect_revokes_then_deletes_the_token(client, credentials, monkeypatch, project_root):
    from api.integrations import gmail

    (project_root / "token.json").write_text("{}")
    monkeypatch.setattr(gmail, "load_credentials", lambda: FakeCreds())
    calls = []

    class Response:
        status_code = 200

    monkeypatch.setattr(gmail.requests, "post", lambda url, **kw: calls.append((url, kw["params"])) or Response())
    assert client.post("/api/integrations/gmail/disconnect").json()["revoked"] is True
    assert calls == [(gmail.REVOKE_URL, {"token": "refresh-1"})]
    assert not (project_root / "token.json").exists()


# ---------------------------------------------------------------- settings, secrets, data


def test_search_settings_round_trip_and_validation(client):
    body = client.get("/api/settings/search").json()
    settings = body["settings"]
    assert settings["time_window_hours"] == 48
    settings["target_roles"]["Data Steward"] = ["data steward", "Data Steward"]
    settings["allowed_locations"].append("Liège")
    settings["gmail"]["senders"].append("from:@jobs.example.com")
    saved = client.put("/api/settings/search", json={"settings": settings}).json()
    assert saved["settings"]["target_roles"]["Data Steward"] == ["data steward"]
    assert "liège" in saved["settings"]["allowed_locations"]
    assert saved["settings"]["gmail"]["senders"][-1] == "jobs.example.com"
    assert any("Data Steward" in w for w in saved["warnings"])

    bad = dict(settings, target_roles={}, allowed_locations=[])
    response = client.put("/api/settings/search", json={"settings": bad})
    assert response.status_code == 422
    assert client.put("/api/settings/search", json={"settings": {**settings, "time_window_hours": 0}}).status_code == 422


def test_secrets_are_masked_and_written_to_env(client, project_root):
    (project_root / ".env").write_text("# keep me\nTELEGRAM_BOT_TOKEN=abc\nGROQ_API_KEY=old\n")
    described = client.put("/api/settings/secrets", json={"values": {"GROQ_API_KEY": "gsk_abcdefghijkl1234",
                                                                     "ALERT_EMAIL_TO": "me@example.com"}}).json()
    groq = next(item for item in described if item["key"] == "GROQ_API_KEY")
    assert groq["set"] and groq["masked"] == "gsk_…1234"
    assert "gsk_abcdefghijkl1234" not in json.dumps(described)
    text = (project_root / ".env").read_text()
    assert text.startswith("# keep me\nTELEGRAM_BOT_TOKEN=abc\nGROQ_API_KEY=gsk_abcdefghijkl1234\n")
    assert os.environ["GROQ_API_KEY"] == "gsk_abcdefghijkl1234"
    assert client.get("/api/integrations/status").json()["groq"]["status"] == "ok"

    client.put("/api/settings/secrets", json={"values": {"GROQ_API_KEY": ""}})
    assert "GROQ_API_KEY" not in (project_root / ".env").read_text()
    assert client.put("/api/settings/secrets", json={"values": {"PATH": "x"}}).status_code == 400
    assert client.put("/api/settings/secrets", json={"values": {"GROQ_API_KEY": "a\nB=1"}}).status_code == 422


def test_integration_tests_explain_missing_keys(client):
    assert client.post("/api/integrations/groq/test").json()["ok"] is False
    assert "Adzuna" in client.post("/api/integrations/adzuna/test").json()["message"]
    assert client.post("/api/integrations/smtp/test").json()["ok"] is False
    assert client.post("/api/integrations/myspace/test").status_code == 404


def test_reset_needs_typed_confirmation_and_export_excludes_secrets(client, project_root):
    from database import init_db, transaction

    init_db()
    with transaction() as conn:
        conn.execute("INSERT INTO jobs (id, title, location) VALUES ('x', 'Job', 'Gent')")
    (project_root / ".env").write_text("GROQ_API_KEY=secret\n")
    (project_root / "token.json").write_text("{}")
    (project_root / "output" / "a.docx").write_bytes(b"x")
    assert client.post("/api/data/reset-jobs", json={"confirm": "reset"}).status_code == 400

    export = client.get("/api/data/export")
    names = zipfile.ZipFile(io.BytesIO(export.content)).namelist()
    assert {"resume_data.yaml", "jobs.db", "output/a.docx"} <= set(names)
    assert not any(n.endswith((".env", "token.json", "credentials.json")) for n in names)

    assert client.post("/api/data/reset-jobs", json={"confirm": "RESET"}).json() == {"deleted": 1}
    assert client.get("/api/jobs").json()["total"] == 0
    assert config.RESUME_PATH.exists()
