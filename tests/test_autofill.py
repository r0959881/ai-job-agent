"""Browser auto-fill against local pages: reaching the form, what is filled and what is left alone."""
import pytest

playwright = pytest.importorskip("playwright.sync_api")

PROFILE = {"full_name": "Ammar Haider", "email": "ammar@example.com", "phone": "+32 466 00 00 00",
           "location": "Mechelen / Antwerp, Belgium", "work_authorization": "Authorized to work in Belgium / EU"}

POSTING = """<!doctype html><html><body>
<div id="cookies" style="position:fixed;inset:0;background:#fff;z-index:9">
  <button onclick="document.getElementById('cookies').remove()">Accept all</button></div>
<h1>Junior Data Analyst</h1>
<form id="alerts"><label>Get job alerts <input type="email" name="alertEmail"></label></form>
<a href="form.html" target="_blank">Apply now</a>
</body></html>"""

FORM = """<!doctype html><html><body><h1>Application</h1>
<iframe src="frame.html" style="width:900px;height:900px"></iframe></body></html>"""

FRAME = """<!doctype html><html><body><form>
<label>First name <input name="first_name"></label>
<label>Last name <input name="last_name"></label>
<label>Email <input type="email" name="email"></label>
<label>Phone <input type="tel" name="phone" value="+49"></label>
<label>City <input name="city"></label>
<label>Country <select name="country"><option value="">Choose</option><option>Belgium</option>
  <option>Netherlands</option></select></label>
<label>Search jobs <input name="q"></label>
<label>Preferred name <input name="preferred" value="Ammy"></label>
<label>Work permit expiry date <input name="permit_expiry"></label>
<label>Are you authorised to work in the EU? <input name="authorised"></label>
<label>Why this company? <textarea name="why"></textarea></label>
<label>Resume/CV <input type="file" name="resume"></label>
<label>Cover letter <input type="file" name="cover_letter"></label>
</form></body></html>"""

LOGIN = """<!doctype html><html><body><form>
<label>Email <input type="email" name="email"></label><label>Password <input type="password" name="pw"></label>
<label>Full name <input name="name"></label></form></body></html>"""

LATE = """<!doctype html><html><body><div id="slot"></div>
<button onclick="document.getElementById('slot').innerHTML =
  '<form><label>Full name <input name=full></label><label>Email <input type=email name=mail></label></form>'">
  Start</button></body></html>"""


@pytest.fixture
def site(tmp_path):
    for name, html in {"posting.html": POSTING, "form.html": FORM, "frame.html": FRAME, "login.html": LOGIN,
                       "late.html": LATE}.items():
        (tmp_path / name).write_text(html, encoding="utf-8")
    (tmp_path / "cv.docx").write_bytes(b"cv")
    (tmp_path / "letter.docx").write_bytes(b"letter")
    return tmp_path


@pytest.fixture
def context():
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser.new_context()
        browser.close()


def values(page):
    frame = page.frames[-1]
    return frame.evaluate("""() => Object.fromEntries(Array.from(document.querySelectorAll('input, select, textarea'))
        .map(el => [el.name, el.type === 'file' ? Array.from(el.files).map(f => f.name).join(',') : el.value]))""")


def test_it_clicks_apply_follows_the_tab_and_fills_the_embedded_form(site, context):
    import apply

    page = context.new_page()
    page.goto((site / "posting.html").as_uri())
    filler = apply.AutoFiller(apply.applicant_profile(PROFILE), str(site / "cv.docx"), str(site / "letter.docx"))
    steps = []
    form_page = apply.reach_and_fill(context, page, filler, steps)

    assert steps == ["Accepted the cookie banner", "Clicked “Apply now”", "Followed it to a new tab"]
    assert page.locator("input[name=alertEmail]").input_value() == ""  # the job-alert box is left alone
    filled = values(form_page)
    assert filled["first_name"] == "Ammar" and filled["last_name"] == "Haider"
    assert filled["email"] == "ammar@example.com" and filled["phone"] == "+32 466 00 00 00"
    assert filled["city"] == "Mechelen" and filled["country"] == "Belgium"
    assert filled["resume"] == "cv.docx" and filled["cover_letter"] == "letter.docx"
    assert filled["authorised"] == "Authorized to work in Belgium / EU"
    # Search boxes, existing answers, date questions and open questions are not touched.
    assert filled["q"] == "" and filled["preferred"] == "Ammy" and filled["permit_expiry"] == ""
    assert filled["why"] == ""


def test_sign_in_forms_are_never_filled(site, context):
    import apply

    page = context.new_page()
    page.goto((site / "login.html").as_uri())
    filler = apply.AutoFiller(apply.applicant_profile(PROFILE))
    assert filler.fill_page(page) == 0
    assert values(page) == {"email": "", "pw": "", "name": ""}


def test_fields_that_appear_later_are_filled_while_watching(site, context):
    import apply

    page = context.new_page()
    page.goto((site / "late.html").as_uri())
    filler = apply.AutoFiller(apply.applicant_profile(PROFILE))
    assert filler.fill_page(page) == 0
    page.get_by_role("button", name="Start").click()  # what the user does in the window
    apply.watch(context, filler, stop_after=3)
    assert values(page) == {"full": "Ammar Haider", "mail": "ammar@example.com"}


def test_field_classification():
    from apply import classify_field

    def field(describe, kind="text", tag="input", autocomplete=""):
        return {"describe": describe, "type": kind, "tag": tag, "autocomplete": autocomplete, "formRole": ""}

    assert classify_field(field("Company name | company")) is None
    assert classify_field(field("username | session_key")) is None
    assert classify_field(field("", "file")) == "cv"
    assert classify_field(field("Upload your motivation letter", "file")) == "cover_letter"
    assert classify_field(field("Voornaam")) == "first_name"
    assert classify_field(field("Salary expectations (EUR) | salary", "number")) is None
    assert classify_field(field("x", autocomplete="family-name")) == "last_name"
