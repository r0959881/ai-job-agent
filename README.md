# AI Job Agent

Finds early-career data jobs in Belgium and the Netherlands (Adzuna, Arbeitnow and
Gmail job-alert emails), filters them, and writes a tailored CV for each one with
Groq. Everything runs on your own computer.

There are two front doors to the same pipeline:

- **Command line:** `python run_agent.py` (unchanged).
- **Web UI:** `.\start.ps1`, a local app for your profile, runs, jobs, documents and applications.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium   # only for "Auto-fill with browser"
Copy-Item .env.example .env                                  # or add the keys later in the UI
```

The web UI also needs Node.js 18+ the first time, to build the frontend.

## Using the UI

```powershell
.\start.ps1
```

This builds the web app if needed, starts the server on `http://127.0.0.1:8765` and
opens your browser. Stop it with Ctrl+C. Options: `-Port 8800`, `-NoBrowser`,
`-Rebuild`. You can also run `python serve.py`.

**First launch.** If `resume_data.yaml` is empty, the app opens onboarding:

1. **Choose a source.** Upload a PDF/DOCX resume (needs a Groq key), import your
   LinkedIn data export (.zip, no key needed), or keep the existing YAML. Sources can
   be combined: import a PDF, then LinkedIn to fill gaps.
2. **Review.** Nothing is saved until you click **Apply to profile**. Conflicts show
   your value next to the imported one (*Keep mine*, *Use LinkedIn*, *Keep both*),
   and new skills are sorted into categories. A backup is made before every save.
3. **Connect & configure.** Add API keys (each has a *Test* button), connect Gmail,
   and pick your target roles. Then *Run your first search*.

**Day to day**

| Page | What it is for |
|---|---|
| Dashboard | KPIs, funnel, last run, jobs ready to apply, integration health |
| Profile | Your master resume: every section editable, drag to reorder, history with restore, live CV preview, *Advanced: Edit YAML* |
| Jobs | Search and filter every job (filters live in the URL); open one for its **Apply** checklist |
| Documents | Every CV, cover letter and report in `output/`, with preview, download, *Open in Word*, regenerate, delete and orphan clean-up |
| Runs | Start a run (sources, time window, CV cap, dry run), watch it live, cancel, read old logs |
| Settings | Search rules (roles, keywords, locations, sources), API keys, Gmail, LinkedIn import, data export and reset |

The Apply workspace takes you from a found job to *applied*: open the posting, check
the keyword match, preview or edit the tailored CV, generate a cover letter, copy
standard answers, and optionally let a visible browser auto-fill the form (you
always submit yourself). Then track the status, dates and notes.

Keyboard: `Ctrl+K` command palette, `Ctrl+S` save profile, `?` all shortcuts,
`g` then `d/p/j/o/r/s` to jump between pages.

### Gmail

1. In Google Cloud Console, enable the Gmail API and create an OAuth client of type
   **Desktop app**. Download it as `credentials.json` into this folder.
2. In the UI open **Settings → Integrations → Connect Gmail** and sign in with Google.
   Access is read-only (`gmail.readonly`).

A Desktop client accepts the loopback redirect
(`http://127.0.0.1:<port>/api/integrations/gmail/callback`), so there is nothing to
register. If you use a *Web application* client, the Gmail card shows the exact URI
to add.

If your Google Cloud app is in *Testing* mode, Google expires access after 7 days.
The Gmail card and the dashboard then show *Reconnect required*, and runs skip Gmail
with a warning instead of failing. Reconnect, or publish the app for personal use.

### Where things live

| File | Contents | In git? |
|---|---|---|
| `resume_data.yaml` | Master resume (the UI keeps your comments and formatting) | yes |
| `agent_settings.yaml` | Search settings edited in Settings → Search | yes |
| `.env` | API keys (written by the UI, never shown in full) | no |
| `credentials.json`, `token.json`, `.gmail_state.json` | Google OAuth client, token and status | no |
| `jobs.db` | Jobs, runs and documents | no |
| `output/`, `output/runs/` | Generated files and per-run logs | no |
| `backups/resume/` | The last 20 versions of your resume | no |
| `.ui_token` | Random per-install token that protects write requests | no |

### Security

The server only listens on 127.0.0.1 and only answers requests whose `Host` is
localhost. Every write request needs the per-install token from `.ui_token`, which
other websites cannot read, so they cannot trigger actions in the app. Files are only
served from inside `output/`.

### Development

```powershell
.\start.ps1 -Dev                      # API only on :8765
cd web; npm run dev                   # Vite with hot reload on http://127.0.0.1:5173
```

Set `AI_JOB_AGENT_FAKE_SOURCES=1` to run the whole pipeline offline, with fake job
sources, Groq and Gmail, for UI work.

Checks:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest              # backend + e2e (e2e needs web/dist)
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
cd web; npm run typecheck; npm run lint; npm test
```

The end-to-end test (`tests/e2e`) edits the profile, runs the mocked agent, opens a
job and marks it applied. It also runs an axe accessibility scan of every main page
in light and dark mode.

### Troubleshooting

- **"npm was not found"**: install Node.js once; after the first build `start.ps1`
  works without it.
- **Auto-fill says Playwright's browser is not installed**: run
  `python -m playwright install chromium`.
- **A CV will not delete**: it is open in Word. Close it and try again.
- **A scanned PDF imports almost nothing**: export it as a text PDF or DOCX, or use
  the LinkedIn import.
