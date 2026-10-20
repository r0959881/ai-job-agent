import base64
import json
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import agent_settings
from agent_log import RunCancelled, check_cancelled, log
from config import CREDENTIALS_PATH, GMAIL_STATE_PATH, TOKEN_PATH, atomic_write_text
from discovery import save_jobs_to_db

# Scopes needed to read Gmail messages
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Sender keyword -> source label used in the jobs table.
SENDER_SOURCES = [
    ("linkedin", "LinkedIn Alerts"),
    ("indeed", "Indeed Alerts"),
    ("stepstone", "StepStone Belgium"),
    ("jobat", "Jobat Belgium"),
    ("vdab", "VDAB Belgium"),
    ("actiris", "Actiris Brussels"),
]
LOCATION_TRUSTED_SOURCES = {"StepStone Belgium", "Jobat Belgium", "VDAB Belgium", "Actiris Brussels"}


class GmailAuthRequired(Exception):
    """Gmail needs (re)consent and the caller may not open a browser."""

    def __init__(self, reason, status="not_connected"):
        super().__init__(reason)
        self.reason = reason
        self.status = status


def _now():
    return datetime.now(timezone.utc).isoformat()


def read_gmail_state():
    try:
        return json.loads(GMAIL_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def update_gmail_state(**changes):
    state = {**read_gmail_state(), **changes}
    atomic_write_text(GMAIL_STATE_PATH, json.dumps(state, indent=2))
    return state


def save_token(creds):
    atomic_write_text(TOKEN_PATH, creds.to_json())


def get_gmail_service(interactive=True):
    """Authenticates and returns the Gmail API service instance.

    With interactive=False (the web server) a browser is never opened: a missing
    or revoked token raises GmailAuthRequired instead.
    """
    creds = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except ValueError:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                update_gmail_state(last_refresh=_now(), status="connected", reason="")
            except RefreshError as error:
                # The cached refresh token can be revoked or expire; re-authorize it.
                update_gmail_state(status="reauth_required", reason=str(error))
                if not interactive:
                    raise GmailAuthRequired(
                        "Google rejected the saved Gmail token. Reconnect Gmail in Settings.",
                        status="reauth_required",
                    ) from error
                creds = None
        else:
            creds = None

        if not creds:
            if not interactive:
                raise GmailAuthRequired("Gmail is not connected yet. Connect it in Settings.")
            if not CREDENTIALS_PATH.exists():
                log("❌ Error: credentials.json missing! Ensure it is saved in your project folder.", level="error")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
            update_gmail_state(status="connected", reason="", connected_at=_now())

        save_token(creds)

    return build('gmail', 'v1', credentials=creds)

def extract_body_html(payload):
    """Recursively extracts raw HTML body content from multi-part payloads."""
    if 'parts' in payload:
        for part in payload['parts']:
            if part.get('mimeType') == 'text/html' and 'data' in part.get('body', {}):
                return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
            elif 'parts' in part:
                res = extract_body_html(part)
                if res:
                    return res
    elif payload.get('mimeType') == 'text/html' and 'data' in payload.get('body', {}):
        return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
    return ""


def extract_body_text(payload):
    """Recursively extract a plain-text body when an alert has no HTML part."""
    if payload.get("mimeType") == "text/plain" and "data" in payload.get("body", {}):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
    for part in payload.get("parts", []):
        text = extract_body_text(part)
        if text:
            return text
    return ""


def source_for_sender(sender):
    sender_lower = sender.lower()
    for keyword, label in SENDER_SOURCES:
        if keyword in sender_lower:
            return label
    return "Email Alert"


def count_alert_messages(service=None, interactive=False):
    """Count matching alert emails without saving anything (used by the UI's test button)."""
    service = service or get_gmail_service(interactive=interactive)
    settings = agent_settings.load()
    results = service.users().messages().list(
        userId='me', q=agent_settings.gmail_query(settings), maxResults=settings["gmail"]["max_results"],
    ).execute()
    return len(results.get('messages', []))


def parse_email_alerts(interactive=True, settings=None):
    service = get_gmail_service(interactive=interactive)
    if not service:
        return None

    log("📬 Connected to Gmail API. Searching for Belgian job alerts...")

    # Search trusted job-alert senders; the relevance filter handles titles and seniority.
    # `settings` carries the run's regions and roles; Gmail options always come from the file.
    settings = settings or agent_settings.load()
    query = agent_settings.gmail_query(settings)
    totals = {"messages": 0, "discovered": 0, "new": 0, "duplicates": 0, "filtered": 0}

    try:
        results = service.users().messages().list(
            userId='me', q=query, maxResults=settings["gmail"]["max_results"],
        ).execute()
        messages = results.get('messages', [])
        totals["messages"] = len(messages)
        update_gmail_state(last_fetch=_now(), last_message_count=len(messages), status="connected", reason="")

        if not messages:
            log("ℹ️ No new job alert emails matching criteria found in inbox.")
            return totals

        email_jobs = []
        skipped_without_body = 0
        for msg in messages:
                check_cancelled()
                msg_data = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
                headers = msg_data['payload']['headers']
                sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')

                # Identify platform source
                source = source_for_sender(sender)

                html_body = extract_body_html(msg_data['payload'])
                plain_body = extract_body_text(msg_data['payload'])
                if not html_body and not plain_body:
                    skipped_without_body += 1
                    continue

                soup = BeautifulSoup(html_body, 'html.parser') if html_body else None

                # Parse job links, then send them through the shared database filter.
                links = soup.find_all('a', href=True) if soup else []
                if not links and plain_body:
                    log(f"  ℹ️ Plain-text alert found from {source}; no links extracted")
                for link in links:
                    text = link.get_text(strip=True)
                    href = link['href']
                    context = link.parent.get_text(" ", strip=True) if link.parent else text
                    candidate_text = f"{text} {context} {href}"

                    location_context = candidate_text
                    if source in LOCATION_TRUSTED_SOURCES:
                        location_context = "Belgium"

                    email_jobs.append({
                        "title": text,
                        "company_name": f"Partner ({source})",
                        "description": candidate_text,
                        "location": location_context,
                        "url": href,
                        "source": source,
                    })

        log(f"📨 Gmail messages: {len(messages)} | candidate links: {len(email_jobs)} | bodyless: {skipped_without_body}")
        for source in sorted({job["source"] for job in email_jobs}):
            source_jobs = [job for job in email_jobs if job["source"] == source]
            counts = save_jobs_to_db(source_jobs, source, settings)
            for key in ("discovered", "new", "duplicates", "filtered"):
                totals[key] += counts[key]
        return totals

    except RefreshError as error:
        update_gmail_state(status="reauth_required", reason=str(error))
        if not interactive:
            raise GmailAuthRequired(
                "Google rejected the saved Gmail token. Reconnect Gmail in Settings.",
                status="reauth_required",
            ) from error
        log(f"❌ Error parsing Gmail alerts: {error}", level="error")
        return None
    except RunCancelled:
        raise
    except Exception as e:
        log(f"❌ Error parsing Gmail alerts: {e}", level="error")
        return None

if __name__ == "__main__":
    parse_email_alerts()
