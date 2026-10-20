"""Open a job posting in a visible browser, get to its application form and fill it in.

Nothing is ever submitted. The flow:

1. Open the posting and dismiss a cookie banner if one blocks the page.
2. If no application form is visible yet, click the posting's "Apply" button
   (following new tabs and redirects, up to a few hops: job board -> company site -> form).
3. Fill every recognised, empty field in every frame (Greenhouse and others embed the
   form in an iframe): names, email, phone, location, links, standard answers, and
   upload the tailored CV and cover letter.
4. Keep watching until the window is closed, so fields that appear later are filled
   too: after you click Apply yourself, sign in, or move to the next step of a form.

A persistent browser profile (.browser_profile/) keeps you signed in to LinkedIn,
Indeed and other sites between runs.
"""
import re
import time
from urllib.parse import urljoin

from agent_log import log
from config import PROJECT_ROOT, load_resume_file, resolve_project_path
from database import connect

PROFILE_DIR = PROJECT_ROOT / ".browser_profile"
MARK = "data-jobagent-filled"
MAX_APPLY_HOPS = 3
WATCH_INTERVAL_SECONDS = 1.5

FIELD_LABELS = {
    "first_name": "first name", "last_name": "last name", "full_name": "name", "email": "email",
    "phone": "phone", "city": "city", "location": "location", "country": "country", "linkedin": "LinkedIn",
    "github": "GitHub", "website": "website", "notice_period": "notice period",
    "salary_expectation": "salary expectation", "work_authorization": "work authorisation",
    "sponsorship_required": "sponsorship", "cv": "CV", "cover_letter": "cover letter",
}

# Fields that belong to search boxes, sign-in forms, newsletters and the like: never touched.
SKIP = re.compile(
    r"search|newsletter|subscri|coupon|captcha|password|passwd|user.?name|login|log.?in|sign.?in|session|"
    r"keyword|promo|voucher|referral.?code|chat|otp|verification.?code|zip.?code.?search|filter",
    re.I,
)
# Ordered: the first rule whose pattern matches the field's description wins.
RULES = [
    ("email", re.compile(r"e-?mail|courriel", re.I)),
    ("first_name", re.compile(r"first.?name|given.?name|\bfname\b|fore.?name|voornaam|pr[ée]nom|vorname", re.I)),
    ("last_name", re.compile(r"last.?name|family.?name|sur.?name|\blname\b|achternaam|nom de famille|nachname", re.I)),
    ("phone", re.compile(r"phone|mobile|\btel\b|telefoon|gsm|t[ée]l[ée]phone|telefon|handy", re.I)),
    ("linkedin", re.compile(r"linked.?in", re.I)),
    ("github", re.compile(r"github", re.I)),
    ("website", re.compile(r"website|portfolio|personal.?(site|url)|homepage", re.I)),
    ("notice_period", re.compile(r"notice|opzegtermijn|pr[ée]avis|k[üu]ndigungsfrist|start.?date|available.?from", re.I)),
    ("salary_expectation", re.compile(r"salary|compensation|pay.?expect|loon|salaire|gehalt|wage", re.I)),
    ("work_authorization", re.compile(r"authori[sz]|work.?permit|right.?to.?work|eligible.?to.?work|visa", re.I)),
    ("sponsorship_required", re.compile(r"sponsor", re.I)),
    ("country", re.compile(r"\bcountry\b|\bland\b|\bpays\b", re.I)),
    ("city", re.compile(r"\bcity\b|\btown\b|woonplaats|\bstad\b|\bville\b|wohnort", re.I)),
    ("location", re.compile(r"location|address|adres|adresse|where.?do.?you.?live|residence", re.I)),
    ("full_name", re.compile(r"full.?name|your.?name|\bname\b|\bnaam\b|\bnom\b", re.I)),
]
STANDARD_ANSWERS = {"notice_period", "salary_expectation", "work_authorization", "sponsorship_required"}
DATE_QUESTION = re.compile(r"expir|\bdate\b|datum|\bwhen\b|\bsince\b|valid until", re.I)
# Pages that are the application itself, where a lone email box is the form, not a newsletter.
APPLICATION_URL = re.compile(
    r"/(apply|application|applications|candidature|bewerbung|bewerben|postuler|solliciteren|sollicitatie)(/|\?|#|$)"
    r"|/c/new\b",
    re.I,
)
NOT_A_PERSON_NAME = re.compile(r"company|employer|user|file|job|middle|preferred|nick|school|reference|manager", re.I)
COVER_LETTER_FILE = re.compile(r"cover|motivation|motivatie|lettre|anschreiben|letter", re.I)
CV_FILE = re.compile(r"resume|résumé|\bcv\b|curriculum|lebenslauf|upload|attach|document|file", re.I)

APPLY_TEXT = [
    re.compile(p, re.I) for p in (
        r"^\s*apply (now|for this (job|position|role)|online|here)\b",
        r"^\s*apply on (the )?company('s)? (website|site)",
        r"^\s*(solliciteer|nu solliciteren|solliciteren)\b",
        r"^\s*(postuler|postulez|je postule)\b",
        r"^\s*(jetzt )?bewerben\b|^\s*jetzt bewerben",
        r"^\s*easy apply\b",
        r"^\s*apply\s*$",
        r"^\s*(i'?m interested|start (your )?application)\b",
    )
]
APPLY_NOT = re.compile(r"filter|applied|apply to (similar|more)|save", re.I)
COOKIE_ACCEPT = re.compile(
    r"^\s*(accept( all)?( cookies)?|allow( all)?( cookies)?|agree( to all)?|i agree|accept and continue|ok(ay)?|"
    r"got it|consent|i consent|"
    r"alles accepteren|accepteren|akkoord|alle cookies accepteren|toestemming geven|tout accepter|"
    r"accepter( et fermer)?|j'accepte|alle akzeptieren|akzeptieren|zustimmen|einwilligen)\s*$",
    re.I,
)

# One pass over a frame: describe every candidate control without many round trips.
DESCRIBE_JS = """
(mark) => Array.from(document.querySelectorAll('input, textarea, select')).map((el, index) => {
  const style = window.getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  const visible = style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  const texts = [];
  if (el.labels) for (const label of el.labels) texts.push(label.innerText);
  const labelledBy = el.getAttribute('aria-labelledby');
  if (labelledBy) for (const id of labelledBy.split(/\\s+/)) {
    const node = document.getElementById(id); if (node) texts.push(node.innerText);
  }
  const wrapper = el.closest('label, .field, .form-group, .application-question, [class*="field"], [class*="question"]');
  if (wrapper && !texts.length) texts.push((wrapper.innerText || '').slice(0, 120));
  const form = el.closest('form');
  return {
    index,
    tag: el.tagName.toLowerCase(),
    type: (el.getAttribute('type') || '').toLowerCase(),
    describe: [texts.join(' '), el.name, el.id, el.placeholder, el.getAttribute('aria-label'),
               /^(on|off)$/i.test(el.getAttribute('autocomplete') || '') ? '' : el.getAttribute('autocomplete')]
              .filter(Boolean).join(' | ').replace(/\\s+/g, ' ').slice(0, 300),
    autocomplete: (el.getAttribute('autocomplete') || '').toLowerCase(),
    role: (el.getAttribute('role') || '').toLowerCase(),
    // Phone widgets prefill a dialling code ("+49"); that still counts as empty.
    empty: el.tagName === 'SELECT' ? !el.value : el.type === 'file' ? !el.files.length :
           el.type === 'tel' ? /^\\s*\\+?\\d{0,4}\\s*$/.test(el.value) : !el.value,
    // Upload inputs are often hidden behind a styled button; their container shows whether the form is open.
    visible: visible || (el.type === 'file' && [el.parentElement, el.closest('form')].some(
      (box) => box && box.getBoundingClientRect().width > 0)),
    disabled: el.disabled || el.readOnly,
    marked: el.hasAttribute(mark),
    form: form ? Array.prototype.indexOf.call(document.forms, form) : -1,
    formRole: form ? ((form.getAttribute('role') || '') + ' ' + (form.getAttribute('action') || '') + ' ' +
                      (form.id || '') + ' ' + (form.className || '')).toLowerCase() : '',
  };
})
"""


def load_standard_answers():
    """Loads default responses for standard candidate questions."""
    data = load_resume_file()
    if data is None:
        return {}
    return {**data.get("personal_info", {}), **data.get("standard_answers", {})}


def applicant_profile(answers):
    """Values for each field kind, derived from personal_info and standard_answers."""
    full_name = str(answers.get("full_name") or "").strip()
    first, _, last = full_name.partition(" ")
    location = str(answers.get("location") or "").strip()
    parts = [part.strip() for part in re.split(r"[,/]", location) if part.strip()]
    profile = {
        "full_name": full_name, "first_name": first, "last_name": last, "email": answers.get("email", ""),
        "phone": answers.get("phone", ""), "location": location, "city": parts[0] if parts else "",
        "country": parts[-1] if len(parts) > 1 else "",
        "linkedin": answers.get("linkedin") or answers.get("linkedin_url", ""),
        "github": answers.get("github") or answers.get("github_url", ""),
        "website": answers.get("website") or answers.get("portfolio", ""),
    }
    for key in ("notice_period", "salary_expectation", "work_authorization", "sponsorship_required"):
        profile[key] = answers.get(key, "")
    return {key: str(value) for key, value in profile.items() if value}


def classify_field(field):
    """The profile key a described control should receive, or None to leave it alone."""
    text = field["describe"]
    kind = field["type"]
    if field["tag"] == "input" and kind in {"hidden", "password", "submit", "button", "checkbox", "radio", "image",
                                            "reset", "search", "range", "color"}:
        return None
    if SKIP.search(text) or SKIP.search(field["formRole"]):
        return None
    if kind == "file":
        if COVER_LETTER_FILE.search(text):
            return "cover_letter"
        return "cv" if CV_FILE.search(text) or not text else None
    if field["autocomplete"] in {"given-name"}:
        return "first_name"
    if field["autocomplete"] in {"family-name"}:
        return "last_name"
    if field["autocomplete"] == "email" or kind == "email":
        return "email"
    if field["autocomplete"].startswith("tel") or kind == "tel":
        return "phone"
    for key, pattern in RULES:
        if pattern.search(text):
            if key == "full_name" and NOT_A_PERSON_NAME.search(text):
                return None
            # Standard answers are sentences; a date or number question needs the user's own answer.
            if key in STANDARD_ANSWERS and (kind in {"date", "number", "month"} or DATE_QUESTION.search(text)):
                return None
            return key
    return None


class AutoFiller:
    """Fills recognised fields across every page and frame of one browser context."""

    def __init__(self, profile, cv_path=None, cover_letter_path=None):
        self.profile = profile
        self.files = {"cv": cv_path, "cover_letter": cover_letter_path}
        self.filled = []  # field kinds, in the order they were first filled

    def _note(self, key):
        if key not in self.filled:
            self.filled.append(key)
            log(f"  ✓ {FIELD_LABELS.get(key, key)} filled")

    def fill_frame(self, frame, application_page=False):
        try:
            fields = frame.evaluate(DESCRIBE_JS, MARK)
        except Exception:
            return 0
        controls = frame.locator("input, textarea, select")
        count = 0
        uploaded = set()
        # A visible password box means a sign-in or sign-up form: the user fills that themselves.
        if any(field["type"] == "password" and field["visible"] for field in fields):
            return 0
        for field in fields:
            field["key"] = classify_field(field) if field["visible"] else None
        # On a job posting, an email box that is the only thing recognised is a newsletter or alert signup.
        if not application_page and {field["key"] for field in fields if field["key"]} == {"email"}:
            return 0
        for field in fields:
            key = field["key"]
            if not key or field["marked"] or not field["empty"] or field["disabled"]:
                continue
            control = controls.nth(field["index"])
            try:
                if field["type"] == "file":
                    path = self.files.get(key)
                    if not path or key in uploaded or key in self.filled:
                        continue
                    control.set_input_files(path, timeout=5000)
                    uploaded.add(key)
                elif field["tag"] == "select":
                    value = self.profile.get(key)
                    if not value or not self._choose_option(control, value):
                        continue
                else:
                    value = self.profile.get(key)
                    if not value or field["role"] == "combobox" and key == "country":
                        continue
                    control.fill(value, timeout=5000)
                control.evaluate(f"el => el.setAttribute('{MARK}', '1')")
            except Exception:
                continue  # the page changed under us; the next pass tries again
            self._note(key)
            count += 1
        return count

    @staticmethod
    def _choose_option(control, value):
        options = control.locator("option")
        wanted = value.lower()
        for index in range(options.count()):
            label = (options.nth(index).inner_text() or "").strip()
            if label and (label.lower() == wanted or wanted.startswith(label.lower()) or label.lower() in wanted):
                control.select_option(label=label, timeout=5000)
                return True
        return False

    def fill_page(self, page):
        if needs_login(page):
            return 0
        application_page = bool(APPLICATION_URL.search(page.url))
        return sum(self.fill_frame(frame, application_page) for frame in page.frames)


def dismiss_cookies(page):
    for frame in page.frames:
        try:
            button = frame.get_by_role("button", name=COOKIE_ACCEPT).first
            if button.count() and button.is_visible():
                button.click(timeout=2000)
                page.wait_for_timeout(500)
                return True
        except Exception:
            continue
    return False


CLICKABLES = "a, button, [role=button], input[type=submit]"
# Visible clickables with their text, gathered in one call (per-element round trips are slow).
CLICKABLE_TEXT_JS = """
(selector) => Array.from(document.querySelectorAll(selector)).map((el, index) => {
  const rect = el.getBoundingClientRect();
  const style = window.getComputedStyle(el);
  const visible = rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
  const text = (el.innerText || el.value || el.getAttribute('aria-label') || '').replace(/​/g, '').trim();
  return {index, visible, text};
})
"""


def find_apply_button(page):
    """The most specific visible Apply link or button on the page, as (locator, text), or (None, None)."""
    try:
        items = page.evaluate(CLICKABLE_TEXT_JS, CLICKABLES)
    except Exception:
        return None, None
    best = None
    for item in items:
        text = " ".join(item["text"].split())
        if not item["visible"] or not text or len(text) > 60 or APPLY_NOT.search(text):
            continue
        for rank, pattern in enumerate(APPLY_TEXT):
            if pattern.search(text):
                if best is None or rank < best[0]:
                    best = (rank, item["index"], text)
                break
    if not best:
        return None, None
    return page.locator(CLICKABLES).nth(best[1]), best[2]


def needs_login(page):
    url = page.url.lower()
    return any(marker in url for marker in ("/login", "/signin", "/sign-in", "authwall", "/checkpoint", "/uas/"))


def click(page, button):
    """Click, forcing through an overlay if needed, or open the link directly. True if something happened."""
    for force in (False, True):
        try:
            button.click(timeout=4000, force=force)
            return True
        except Exception:
            continue
    try:
        href = button.get_attribute("href", timeout=2000)
    except Exception:
        href = None
    if not href or href.startswith(("#", "javascript:")):
        return False
    try:
        page.goto(urljoin(page.url, href), timeout=60000, wait_until="domcontentloaded")
        return True
    except Exception:
        return False


def reach_and_fill(context, page, filler, steps):
    """Fill the posting; if nothing is fillable, click Apply and follow it, a few hops deep."""
    current = page
    clicked = set()  # (url, label): never click the same button twice, e.g. one that opens a modal
    for _hop in range(MAX_APPLY_HOPS + 1):
        try:
            current.wait_for_load_state("domcontentloaded", timeout=30000)
        except Exception:
            pass
        button = label = None
        # Many career sites render the form or the Apply button seconds after loading.
        for _attempt in range(7):
            current.wait_for_timeout(1500)
            if dismiss_cookies(current):
                steps.append("Accepted the cookie banner")
            before = len(filler.filled)
            filler.fill_page(current)
            new = filler.filled[before:]
            if len(new) >= 2 or [key for key in new if key not in ("cv", "cover_letter")]:
                return current  # the application form is open
            if needs_login(current):
                steps.append("The site asks you to sign in. Sign in in this window; it is remembered next time.")
                return current
            button, label = find_apply_button(current)
            if button:
                break
        if not button or (current.url, label) in clicked:
            return current
        clicked.add((current.url, label))
        pages_before = list(context.pages)
        if not click(current, button):
            return current
        steps.append(f"Clicked “{label}”")
        current.wait_for_timeout(2500)
        new_pages = [p for p in context.pages if p not in pages_before]
        if new_pages:
            current = new_pages[-1]
            steps.append("Followed it to a new tab")
    return current


def open_context(playwright, headless):
    """A persistent profile keeps site sign-ins; fall back to a fresh one if it is in use."""
    # A visible window uses its own size; headless needs a fixed viewport.
    size = {"viewport": {"width": 1280, "height": 900}} if headless else {"no_viewport": True}
    try:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        context = playwright.chromium.launch_persistent_context(str(PROFILE_DIR), headless=headless, slow_mo=150,
                                                                **size)
        return context, None
    except Exception as error:
        log(f"⚠️ Browser profile unavailable ({error.__class__.__name__}); using a fresh window.", level="warning")
        browser = playwright.chromium.launch(headless=headless, slow_mo=150)
        return browser.new_context(**size), browser


def watch(context, filler, stop_after=None):
    """Keep filling new fields until every window is closed (or stop_after seconds pass)."""
    started = time.monotonic()
    while True:
        try:
            pages = [page for page in context.pages if not page.is_closed()]
        except Exception:
            return
        if not pages:
            return
        for page in pages:
            try:
                filler.fill_page(page)
            except Exception:
                continue
        if stop_after is not None and time.monotonic() - started >= stop_after:
            return
        try:
            pages[0].wait_for_timeout(WATCH_INTERVAL_SECONDS * 1000)
        except Exception:
            return


def auto_fill_job_application(job_url, docx_path, headless=False, keep_open_seconds=5, report=False,
                              on_filled=None, wait_for_close=False, cover_letter_path=None):
    """
    Opens the posting, reaches its application form, fills what it recognises and
    attaches the tailored CV (and cover letter). Never submits.

    With report=True a dict {"ok", "filled", "steps", "url", "error"} is returned instead of a bool.
    on_filled(result) is called after the first pass; wait_for_close keeps filling new fields
    until the user closes the window (the web UI uses both so you can submit yourself).
    """
    from playwright.sync_api import sync_playwright

    answers = load_standard_answers()
    paths = {}
    for key, path in (("cv", docx_path), ("cover_letter", cover_letter_path)):
        if path and resolve_project_path(path).exists():
            paths[key] = str(resolve_project_path(path))
    filler = AutoFiller(applicant_profile(answers), paths.get("cv"), paths.get("cover_letter"))
    steps = [] if paths.get("cv") else ["No tailored CV for this job yet, so no file was attached."]
    log(f"\n🤖 Launching Form Submitter for: {job_url}")

    with sync_playwright() as p:
        context, browser = open_context(p, headless)
        page = context.pages[0] if context.pages else context.new_page()
        result = {"ok": True, "filled": [], "steps": steps, "url": job_url}
        try:
            page.goto(job_url, timeout=60000, wait_until="domcontentloaded")
            log("🌐 Page loaded. Looking for the application form...")
            current = reach_and_fill(context, page, filler, steps)
            result["url"] = current.url
            if not filler.filled:
                steps.append("No form fields yet. Click Apply in the window; fields are filled as they appear.")
            log("✅ Form field auto-fill completed.")
        except Exception as error:
            log(f"⚠️ Form auto-fill warning/error: {error}", level="warning")
            result.update(ok=False, error=str(error))
        result["filled"] = [FIELD_LABELS.get(key, key) for key in filler.filled]
        if on_filled:
            on_filled(dict(result))
        try:
            if wait_for_close:
                watch(context, filler)
            elif keep_open_seconds:
                watch(context, filler, stop_after=keep_open_seconds)
        finally:
            result["filled"] = [FIELD_LABELS.get(key, key) for key in filler.filled]
            try:
                context.close()
                if browser:
                    browser.close()
            except Exception:
                pass
    if report:
        return result
    return result["ok"]


if __name__ == "__main__":
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT url, cv_path FROM jobs WHERE url != '' AND COALESCE(cv_path, '') != '' LIMIT 1")
    row = cursor.fetchone()
    conn.close()

    if row:
        auto_fill_job_application(row[0], row[1], headless=False, wait_for_close=True)
    else:
        print("⚠️ No job with a tailored CV found in jobs.db")
