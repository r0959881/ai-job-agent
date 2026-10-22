# AI Job Agent

Finds early-career jobs in the countries you pick (LinkedIn, Indeed, StepStone, Jobat,
VDAB, Michael Page, Randstad, Manpower, Hays, Robert Half, Actiris, Le Forem, web search,
national job exchanges, remote boards, company career pages and
Adzuna), filters them by role, seniority, location and language, and writes a tailored
CV for each one with Groq.

It is a web app for several people. Each person signs in with Google or LinkedIn. Their
profile, search preferences and API keys are saved in the server database. The jobs
found and every CV, cover letter and report stay on their own computer, in a folder
they choose.

- **Hosted:** deploy it on cPanel shared hosting (Namecheap and similar) with
  [DEPLOYMENT.md](DEPLOYMENT.md).
- **On your own PC:** `.\start.ps1` runs the same app on `http://127.0.0.1:8765`.
- **Command line:** `python run_agent.py` is the original single-user pipeline (it also
  reads Gmail job alerts).

## Run it locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\start.ps1
```

The web app also needs Node.js 18+ the first time, to build the frontend. `start.ps1`
builds it if needed, starts the server and opens your browser; stop it with Ctrl+C.
Options: `-Port 8800`, `-NoBrowser`, `-Rebuild`.

Locally there is a **developer sign-in** (any email, no password), because the server
only listens on 127.0.0.1. The data goes into `app.db` (SQLite) next to the code. To try
Google or LinkedIn sign-in locally, set the variables from `.env.example` and
`AI_JOB_AGENT_DEV_LOGIN=0`.

To start with your existing profile instead of onboarding:

```powershell
.\.venv\Scripts\python.exe manage.py import-profile you@example.com resume_data.yaml agent_settings.yaml
```

then use the developer sign-in with that email.

## Using the app

**First sign-in.** A new account starts with the name and email from Google or LinkedIn.
Onboarding then fills the profile:

1. **Choose a source.** Upload a PDF/DOCX resume (needs your Groq key, asked for right
   there), import your LinkedIn data export (.zip, no key needed), or start from your
   current profile. Sources can be combined: import a PDF, then LinkedIn to fill gaps.
   (Signing in with LinkedIn does not share your work history; LinkedIn does not offer
   that to apps, so the export is the way to bring it in.)
2. **Review.** Nothing is saved until you click **Apply to profile**. Conflicts show your
   value next to the imported one, and new skills are sorted into categories. A version
   is kept before every save.
3. **Connect & configure.** Add your API keys (each has a *Test* button), choose the
   documents folder and pick your target roles. Then *Run your first search*.

**Day to day**

| Page | What it is for |
|---|---|
| Dashboard | KPIs, funnel, last run, jobs ready to apply, integration health |
| Profile | Your master resume: every section editable, drag to reorder, history with restore, live CV preview, *Advanced: Edit YAML* |
| Jobs | Search and filter every job (filters live in the URL); open one for its **Apply** checklist |
| Documents | Every CV, cover letter and report in your folder, with preview, download, regenerate and delete |
| Runs | Start a run (regions and language → roles → sources, time window, CV cap, dry run), watch it live, cancel, read old logs |
| Settings | Search rules, API keys, LinkedIn import, the documents folder, your account (export, delete) |

The Apply workspace takes you from a found job to *applied*: open the posting, check the
keyword match, preview or edit the tailored CV, generate a cover letter, copy standard
answers, then track the status, dates and notes.

Keyboard: `Ctrl+K` command palette, `Ctrl+S` save profile, `?` all shortcuts,
`g` then `d/p/j/o/r/s` to jump between pages.

### Where things live

| What | Where |
|---|---|
| Account, profile (with its last 20 versions), search settings | Server database (MySQL on cPanel, `app.db` locally) |
| Groq and Adzuna keys | Server database, encrypted with a key derived from `SECRET_KEY`; never shown in full again |
| Jobs, application tracking, run history | The browser's storage (IndexedDB), one database per user, plus `ai-job-agent-data.json` in the documents folder |
| CVs, cover letters, Excel reports | The documents folder: `CVs/`, `Cover letters/`, `Reports/` (Chrome and Edge). Other browsers keep them in browser storage; download them from Documents |

Opening the app in another browser or on another PC? Choose the same folder there (for
example a synced OneDrive folder) and the job list is restored from
`ai-job-agent-data.json`.

### Runs

**Run agent** opens a three-step dialog: pick the **regions** (about 35 countries plus
*Remote*) and the **job languages**, the **roles** (your role profiles), then the
**sources**. Only jobs located in the picked regions, matching the picked roles and in the
picked languages are kept and tailored. The last choice is remembered; defaults live in
*Settings → Search*.

The browser tab drives the run: it asks the server for one search at a time, keeps the
jobs, then has the server write one CV at a time and saves each into the folder. No
request takes longer than about 40 seconds, which keeps the app within shared hosting's
request limits. **Keep the tab open while a run is going**; closing it stops the run
(the jobs and CVs found so far are kept).

**Job language.** English is picked by default. A job is kept when every language it
requires is one you picked ("fluent Dutch and English" needs both; "Dutch or French"
needs either; "French is a plus" does not count). When a posting names no language, the
language it is written in must be one you picked. Very short listings are kept.

### Job sources

| Source | Key needed | Covers |
|---|---|---|
| LinkedIn, Indeed, Glassdoor (via [JobSpy](https://github.com/speedyapply/JobSpy)) | No | LinkedIn everywhere; Indeed and Glassdoor per country. Glassdoor is off by default because it often blocks |
| StepStone | No | Belgium, Germany (search snippets; StepStone blocks its detail pages) |
| VDAB | No | Belgium (Flanders), with full descriptions and required languages |
| Jobat | No | Belgium (also Vacature, which now redirects to Jobat) |
| Michael Page | No | Belgium/Luxembourg, Germany, France, UK, Ireland, Switzerland, Spain, Italy, Poland, Portugal |
| Randstad / Tempo-Team, Manpower, Hays, Robert Half | No | Belgium (Tempo-Team now redirects to Randstad) |
| Actiris | No | Belgium (Brussels' public employment service; title, contract and place only) |
| Le Forem | No | Belgium (Wallonia's public employment service, via its open-data feed) |
| Web search | Brave Search key, or the Groq key | Postings on company career sites (Greenhouse, Lever, Ashby, Teamtailor, Workday…), any region. Falls back to Groq web search, at most 2 searches per run, when Brave's quota runs out |
| Bundesagentur für Arbeit | No | Germany |
| Arbetsförmedlingen (JobTech) | No | Sweden |
| Arbeitnow | No | Germany, Austria, Switzerland, remote |
| Remotive, Himalayas, Jobicy, Remote OK | No | *Remote* region |
| Company career pages | No | Companies you follow in *Settings → Search* as `greenhouse:collibra`, `lever:…`, `ashby:…`, `recruitee:…`, `smartrecruiters:…` |
| Adzuna | Yes (free, per user) | 19 countries |

If a source fails twice in a row it is skipped for the rest of the run, and the step
shows a warning. LinkedIn and Indeed block heavy automated use, more so from hosting
providers' IP addresses: run less often, lower *Results per search*, or add a proxy in
*Settings → Search*.

### Security

- Sign-in uses OpenID Connect with Google or LinkedIn (state check, PKCE for Google).
  Sessions are signed, HttpOnly, SameSite=Lax cookies, Secure on HTTPS.
- Every write request needs the session's CSRF token, which other sites cannot read.
- Requests are only answered for the configured host names (`PUBLIC_URL`, `ALLOWED_HOSTS`).
- Each request runs in its user's scope: one user can never read another's profile,
  settings or keys. `ALLOWED_EMAILS` can limit who may sign up.
- Generated files are built in memory and returned to the browser; the server keeps no
  copies.

## Development

```powershell
.\start.ps1 -Dev                      # API only on :8765
cd web; npm run dev                   # Vite with hot reload on http://127.0.0.1:5173
```

Set `AI_JOB_AGENT_FAKE_SOURCES=1` to run whole runs offline, with fake job sources and
Groq, for UI work.

Checks:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest              # backend + e2e (e2e needs web/dist)
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
cd web; npm run typecheck; npm run lint; npm test
```

The end-to-end test (`tests/e2e`) signs in, edits the profile, runs the mocked agent in
the browser, marks a job applied, previews its CV, checks a second user sees none of it,
and runs an axe accessibility scan of every main page in light and dark mode.

### Command line (single user)

`python run_agent.py` runs the original pipeline against `resume_data.yaml`,
`agent_settings.yaml`, `.env` and `jobs.db` on your PC, and writes to `output/`. It needs
the extras in `requirements-local.txt` (Gmail and Playwright). For Gmail alerts, put a
Google OAuth *Desktop app* client in `credentials.json`; the first run opens the Google
sign-in.

### Troubleshooting

- **"npm was not found"**: install Node.js once; after the first build `start.ps1`
  works without it.
- **The folder button does nothing**: choosing a folder needs Chrome or Edge, on HTTPS or
  localhost.
- **A scanned PDF imports almost nothing**: export it as a text PDF or DOCX, or use the
  LinkedIn import.
- Hosting problems: see the troubleshooting table in [DEPLOYMENT.md](DEPLOYMENT.md).
