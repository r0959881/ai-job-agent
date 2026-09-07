import base64
import os.path
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from discovery import save_jobs_to_db

# Scopes needed to read Gmail messages
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_gmail_service():
    """Authenticates and returns the Gmail API service instance."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                # The cached refresh token can be revoked or expire; re-authorize it.
                creds = None
        else:
            creds = None

        if not creds:
            if not os.path.exists('credentials.json'):
                print("❌ Error: credentials.json missing! Ensure it is saved in your project folder.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
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

def parse_email_alerts():
    service = get_gmail_service()
    if not service:
        return

    print("📬 Connected to Gmail API. Searching for Belgian job alerts...")

    # Gmail braces express OR reliably and newer_than keeps each run bounded.
    query = (
        'newer_than:2d {from:linkedin.com from:indeed.com '
        'from:stepstone.be from:jobat.be from:vdab.be from:actiris.brussels} '
        '{subject:job subject:vacature subject:alert}'
    )
    
    try:
        results = service.users().messages().list(userId='me', q=query, maxResults=15).execute()
        messages = results.get('messages', [])

        if not messages:
            print("ℹ️ No new job alert emails matching criteria found in inbox.")
            return

        email_jobs = []
        skipped_without_body = 0
        for msg in messages:
                msg_data = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
                headers = msg_data['payload']['headers']
                sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')
                
                # Identify platform source
                source = "Email Alert"
                sender_lower = sender.lower()
                if "linkedin" in sender_lower:
                    source = "LinkedIn Alerts"
                elif "indeed" in sender_lower:
                    source = "Indeed Alerts"
                elif "stepstone" in sender_lower:
                    source = "StepStone Belgium"
                elif "jobat" in sender_lower:
                    source = "Jobat Belgium"
                elif "vdab" in sender_lower:
                    source = "VDAB Belgium"
                elif "actiris" in sender_lower:
                    source = "Actiris Brussels"

                html_body = extract_body_html(msg_data['payload'])
                plain_body = extract_body_text(msg_data['payload'])
                if not html_body and not plain_body:
                    skipped_without_body += 1
                    continue

                soup = BeautifulSoup(html_body, 'html.parser') if html_body else None

                # Parse job links, then send them through the shared database filter.
                links = soup.find_all('a', href=True) if soup else []
                if not links and plain_body:
                    print(f"  ℹ️ Plain-text alert found from {source}; no links extracted")
                for link in links:
                    text = link.get_text(strip=True)
                    href = link['href']
                    context = link.parent.get_text(" ", strip=True) if link.parent else text
                    candidate_text = f"{text} {context} {href}"
                    
                    location_context = candidate_text
                    if source in {"StepStone Belgium", "Jobat Belgium", "VDAB Belgium", "Actiris Brussels"}:
                        location_context = "Belgium"

                    email_jobs.append({
                        "title": text,
                        "company_name": f"Partner ({source})",
                        "description": candidate_text,
                        "location": location_context,
                        "url": href,
                        "source": source,
                    })

        print(f"📨 Gmail messages: {len(messages)} | candidate links: {len(email_jobs)} | bodyless: {skipped_without_body}")
        for source in sorted({job["source"] for job in email_jobs}):
            source_jobs = [job for job in email_jobs if job["source"] == source]
            save_jobs_to_db(source_jobs, source)

    except Exception as e:
        print(f"❌ Error parsing Gmail alerts: {e}")

if __name__ == "__main__":
    parse_email_alerts()