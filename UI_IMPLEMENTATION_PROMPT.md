# Prompt: Build a local web UI for the AI Job Agent

You are working in an existing Python project, the AI Job Agent. Today it runs only from the command line (`python run_agent.py`). Your job is to add a polished, local, **single-user** web interface on top of it. Nobody has written any UI code yet.

Work in phases (listed below). **At the end of each phase, stop, summarise what you built, show how to verify it, and wait for my go-ahead before you start the next one.** Before you write any code, read every Python file and `resume_data.yaml`, then confirm the plan back to me. Flag anything in this prompt that conflicts with the code.

---

## 1. What exists today (verify this yourself)

| File | Role |
|---|---|
| `main.py` / `run_agent.py` | Pipeline entry point: `init_db` → `run_discovery` → `parse_email_alerts` → status refresh → 48-hour filter → `tailor_cv_for_job` per job → Excel report in `output/` |
| `database.py` | SQLite `jobs.db`, table `jobs`. Columns are added through the `JOB_COLUMNS` dict, and rows outside BE/NL locations are deleted on init |
| `discovery.py` | Adzuna and Arbeitnow fetchers. `TARGET_ROLES`, `SEARCH_QUERIES`, location lists and seniority filters are **hard-coded constants** |
| `gmail_parser.py` | Gmail API (needs `credentials.json` and `token.json`). Parses LinkedIn, Indeed, StepStone, Jobat, VDAB and Actiris alerts from the last 2 days |
| `tailor.py` | Groq LLM (`openai/gpt-oss-120b`) writes the summary and bullets. **Raises `SystemExit` at import time if `GROQ_API_KEY` is missing**, which would kill a web server |
| `generate_doc.py` | Builds the tailored CV `.docx` in `output/`. The filename prefix `Ammar_Haider_CV_` is hard-coded |
| `generate_cover_letter.py` | Role-family cover letters. `ROLE_LETTERS` text is hard-coded |
| `apply.py` | Playwright auto-fill (name, email, phone, CV upload) in a visible browser |
| `notifier.py` | Optional Gmail SMTP alert |
| `report.py` | Excel export plus `find_existing_cv` |
| `resume_data.yaml` | Master resume. Sections: `personal_info`, `role_profiles`, `standard_answers`, `core_skills` (categories → list), `experience[]`, `projects[]`, `certifications[]`, `education` (one object), `languages[]` |
| `.env` | `GROQ_API_KEY`, `ADZUNA_APP_ID/KEY`, optional `ALERT_EMAIL_*` and `TELEGRAM_*` |

Constraints:
- `discovery.py` and `gmail_parser.py` contain **uncommitted changes**. Preserve them. Ask me to commit before you refactor those files.
- The project path contains a `)` and sits inside OneDrive (`...\Projects\ai-job)agent`). Quote every path in scripts. Use `pathlib` paths anchored to the project root, never the current working directory.
- The platform is Windows 11. Start scripts must work in PowerShell.
- `python run_agent.py` **must keep working** after all of these changes. The UI is a second front door, not a replacement.
- Never commit or expose `.env`, `credentials.json`, `token.json`, `jobs.db` or `output/`.

---

## 2. Product goals

One person (me) runs this on my own laptop. There are no accounts, no multi-tenancy and no cloud hosting. The UI must let me:

1. **Onboard with my resume.** Upload a PDF or DOCX resume, have the LLM extract it into the `resume_data.yaml` structure, review and correct the extracted data, then save it. Alternatively, start from the existing YAML.
2. **Manage my master data at any time.** Add, edit, delete and reorder every resume section, role profile, standard answer, target role, search query and location filter.
3. **Run the agent.** Start a run with one click, see live per-step progress and logs, cancel the run, and look at the history of past runs.
4. **See everything it produced.** Browse every tailored CV and cover letter, preview it in the browser, download it, regenerate it or delete it, each linked to its job.
5. **Know how to apply to each job.** Every job gets an "Apply" workspace with the posting link, the right CV and cover letter, copy-ready standard answers, an optional Playwright auto-fill, and application status tracking.

---

## 3. Architecture

**Stack (use it unless you find a hard blocker, and tell me if you do):**
- **Backend:** FastAPI + Uvicorn, Pydantic v2 models, in a new `api/` package that *imports* the existing modules. Do not duplicate their logic.
- **Frontend:** a new `web/` folder using React + TypeScript + Vite, Tailwind CSS, shadcn/ui (Radix primitives), TanStack Query for server state, TanStack Table for data grids, React Hook Form + Zod for forms, dnd-kit for reordering, lucide-react icons, and sonner for toasts. Use React Router with these routes: `/`, `/profile`, `/jobs`, `/jobs/:id`, `/documents`, `/runs`, `/runs/:id`, `/settings`, `/onboarding`.
- **Live updates:** Server-Sent Events for run progress and logs. Use SSE rather than WebSockets because the traffic only flows one way.
- **Serving:** in development, use the Vite dev server with a proxy to FastAPI. In production, FastAPI serves the built `web/dist`. One command (`start.ps1` or `python serve.py`) builds the frontend if needed, starts the server on **127.0.0.1 only**, and opens the browser.
- **Security for a single user:** bind to localhost only. Skip login, but require a random per-install token (generated on first start and stored in a gitignored `.ui_token`) on mutating requests to block CSRF from other browser tabs. Use strict CORS (same origin only).

**Backend refactors (minimal, and backwards compatible):**
1. **Lazy Groq client.** Move the key check in `tailor.py` into a `get_client()` function that raises a normal exception. The CLI still prints the same friendly message.
2. **Central config.** Add a `config.py` holding `PROJECT_ROOT`, `DB_PATH`, `OUTPUT_DIR` and `RESUME_PATH`, and replace the scattered relative paths.
3. **Move the hard-coded search settings into editable data.** That covers `TARGET_ROLES`, `SEARCH_QUERIES`, the allowed and blocked locations, the seniority and exclusion keywords, and the time window (48h). Store them in a new gitignored-by-choice `agent_settings.yaml`, or in a `settings` table. Recommend one option to me. Seed it with today's constants so behaviour stays identical, and keep the constants as fallbacks.
4. **Derive the filename prefix and name** from `personal_info.full_name` instead of `Ammar_Haider`.
5. **Progress hooks.** Give `run_agent()` an optional `on_event(step, status, message, data)` callback. Route the existing `print` calls through a small logger that both prints to the console and emits events. CLI output must look the same as before.
6. **New tables** (add them idempotently, following the `JOB_COLUMNS` pattern):
   - `runs`: id, started_at, finished_at, status (`running`/`succeeded`/`failed`/`cancelled`), counts (discovered, new, filtered, tailored, failed), error, log_path.
   - `documents`: id, job_id (nullable), kind (`cv`/`cover_letter`/`report`), role_family, path, created_at, run_id.
   - New `jobs` columns: `role_family`, `application_status` (`not_applied`/`applied`/`interviewing`/`offer`/`rejected`/`skipped`), `applied_at`, `notes`, `cover_letter_path`.
   - Backfill `documents` by scanning the existing `output/` files, using `find_existing_cv` logic to match files to jobs.
7. **Resume store.** Validate with Pydantic models that mirror the YAML exactly. Every write is atomic (write to a temp file, then replace). Before each save, keep a timestamped backup in `backups/resume/` (keep the last 20) so I can restore any version. Preserve key order, and use `ruamel.yaml` if you can keep comments.
8. **Run manager.** Allow one run at a time and run it in a background thread or subprocess. Support cooperative cancellation between steps and between jobs. Write per-run log files to `output/runs/`. If Gmail OAuth needs interactive consent, surface that as a clear UI state ("Connect Gmail") rather than hanging. Missing API keys should skip that step with a warning event, not crash the run.

**API surface (REST, JSON):**
- `GET/PUT /api/resume`, `GET /api/resume/backups`, `POST /api/resume/backups/{id}/restore`, `POST /api/resume/import` (multipart PDF/DOCX → extracted draft, **not saved** until confirmed), `GET/PUT /api/resume/raw` (YAML text with validation errors and line numbers)
- `GET/PUT /api/settings/search`, `GET/PUT /api/settings/secrets` (values masked on read and write-only, with a "test connection" action per integration), `GET /api/integrations/status` (Groq, Adzuna, Gmail token, SMTP)
- `POST /api/runs`, `GET /api/runs`, `GET /api/runs/{id}`, `GET /api/runs/{id}/events` (SSE), `POST /api/runs/{id}/cancel`
- `GET /api/jobs` (filtering, sorting and paging on the server), `GET/PATCH /api/jobs/{id}`, `POST /api/jobs/{id}/tailor`, `POST /api/jobs/{id}/cover-letter`, `POST /api/jobs/{id}/autofill`, `DELETE /api/jobs/{id}`
- `GET /api/documents`, `GET /api/documents/{id}/download`, `GET /api/documents/{id}/preview` (DOCX → sanitised HTML using `mammoth`), `DELETE /api/documents/{id}` (deletes the file too, after confirmation), `GET /api/reports/latest`
- `GET /api/stats` for the dashboard
- Path safety: only serve files whose resolved path is inside `OUTPUT_DIR`.

---

## 4. Screens and UX

### Global shell
- A left sidebar (collapsible, and a drawer on narrow widths) with Dashboard, Profile, Jobs, Documents, Runs and Settings, plus a persistent **"Run agent" button** in the top bar. While a run is active, the button turns into a live progress pill that links to the run.
- A command palette (`Ctrl+K`) for navigation, "Run agent", "Add experience" and job search.
- Light and dark themes that follow the system setting, with a manual toggle.

### Onboarding (first launch or empty resume)
A three-step wizard:
1. Upload a resume (drag-and-drop for PDF/DOCX) *or* "Use existing resume_data.yaml".
2. Review the extracted data side by side: the original document preview on the left, editable structured fields on the right. Highlight low-confidence fields.
3. Enter API keys and test each one, then choose target roles. Finish with the option "Run your first search".

### Dashboard
- KPI cards: jobs found (last 48h), CVs generated, applications sent, interviews.
- A funnel: discovered → eligible → tailored → applied → interviewing.
- A last-run summary card with status, duration, a per-source count and a "View log" link.
- A "Ready to apply" list: the top jobs that have a tailored CV and status `not_applied`, each with a one-click open to the Apply workspace.
- Integration health chips (Groq, Adzuna and Gmail as green, amber or red), with a fix-it link for each.

### Profile (master resume editor)
- Tabs, or a sticky section nav: Personal info · Role profiles · Skills · Experience · Projects · Education · Certifications · Languages · Standard answers.
- List sections (experience, projects, certifications, languages, skills) use cards that **add, edit inline, duplicate, delete with undo toast, and drag to reorder**. Bullets are editable lists with reordering.
- Skills are tag inputs grouped by category, with add, rename and delete for categories.
- Role profiles show focus text, keyword tags, preferred skill categories as a multi-select from the existing categories, and preferred projects as a multi-select of project titles. Warn when a referenced project or category no longer exists.
- Saving: one explicit **Save** bar that appears when the form is dirty and shows a diff count. Guard unsaved changes on navigation. Validate inline as I type.
- Also provide an **"Advanced: Edit YAML"** toggle that opens a code editor (CodeMirror 6 with YAML mode and lint markers from server validation).
- A **History** drawer lists the backups, shows a diff against the current data, and offers restore.
- A live **CV preview** panel (optional, toggleable) renders a sample CV for a chosen role family from the current, possibly unsaved, data.

### Jobs
- A data grid with columns for title, company, location, role family, source, posted, status, application status, CV ✓/✗ and salary.
- Filters (saved in the URL): status, application status, role family, source, date range, and "has CV". Add a global search, plus quick filter chips like "Ready to apply" and "Applied this week".
- Multi-select bulk actions: mark as skipped, regenerate CVs, delete.
- Clicking a row opens the **job detail** (a side sheet, or the `/jobs/:id` route):
  - Header: title, company, location, salary, posted date, source badge and an "Open posting ↗" button.
  - Tabs: **Apply** (default) · Description · Documents · Notes & history.

### Apply workspace (the "how to apply" experience)
A checklist that tracks state per job:
1. **Review the posting.** The posting opens in a new tab, and the matched role family appears with a matched-keyword highlight against my resume.
2. **Your tailored CV.** Preview, download and regenerate, plus "Edit summary/bullets before generating" (show the LLM output in editable fields, then build the DOCX).
3. **Cover letter.** Generate, preview and download.
4. **Copy-ready answers.** Name, email, phone, work authorisation, sponsorship, notice period and salary, each with a copy button.
5. **Apply.** Offer "Auto-fill with browser" (runs `apply.py`, shows its result, and warns that a visible browser window will open and I must review and submit myself) or "I applied manually".
6. **Track.** Set the application status and date, add notes, and record the follow-up reminder date.

Show source-specific tips, for example: LinkedIn/Indeed alert links may need login; Easy Apply means upload the CV in their dialog.

### Documents
- Grid and list toggle, grouped by job or by type (CV, cover letter, Excel report). Searchable and filterable by role family and date.
- A preview modal renders the DOCX as HTML, with download, "Open in Word" (local `file://`), regenerate and delete actions.
- An "Orphans" filter shows files in `output/` with no linked job, with a bulk delete for them.

### Runs
- **Start run** dialog with options: the sources to include (Adzuna, Arbeitnow, Gmail), the time window, a cap on how many CVs to tailor, and dry-run (discover only).
- **Live run view:** a vertical stepper (Init DB → Adzuna → Arbeitnow → Gmail → Filter → Tailoring *n/m* → Report). Each step shows a spinner, a check or a warning, with counts and timing. Below it, a log console that autoscrolls with a pause button, level filters and a copy action. Include a Cancel button.
- **History** table: start time, duration, status and counts. Clicking a row opens the stored log and the documents that run produced.
- A browser notification (with permission) when a run finishes and the tab is in the background.

### Settings
- **Search:** editable target roles with keyword tags, search queries per role, allowed and blocked locations, seniority and exclusion keywords, the time window, and the Gmail alert senders.
- **Integrations:** masked secret fields with show, replace and test actions, Gmail connect/reconnect showing the token status, and SMTP alerts on/off with a test email button.
- **Data:** open the output folder, export everything (zip of YAML, DB and documents), and a "reset jobs database" action behind a typed confirmation.

---

## 5. Design standards (non-negotiable)

- **Design tokens.** Define CSS variables for colour, radius, spacing and shadow in the shadcn theme, using one neutral scale and one accent colour (a calm blue or indigo). Semantic colours: success, warning, danger, info. Never hard-code hex values in components.
- **Typography.** Use Inter (or Geist) with a clear scale: page title, section title, body and caption. Use tabular numbers for counts and dates. Line length on long text stays at 75 characters or fewer.
- **Layout.** Use an 8px spacing grid and keep content max-width around 1280px. Forms use one column for primary fields, with logical grouping and helpful descriptions.
- **Every view has four states:** loading (skeletons that match the layout, never a bare spinner), empty (an illustration-free message plus a primary call to action), error (a human-readable message plus retry) and success.
- **Feedback.** Use optimistic updates where it is safe. Every mutation produces a toast. Destructive actions need a confirmation dialog or an undo toast, and file deletion always needs a confirmation. Long tasks show progress.
- **Accessibility.** Meet WCAG 2.2 AA contrast, support full keyboard navigation, show visible focus rings, give icon buttons ARIA labels, trap focus in dialogs, and respect `prefers-reduced-motion`.
- **Responsiveness.** The UI must be usable from 1024px up and degrade gracefully down to 768px.
- **Motion.** Keep transitions at 150–200ms with no gratuitous animation.
- **Microcopy.** Write plain, specific copy ("Tailored 4 of 6 CVs. 2 failed because Groq timed out"), never generic copy ("Something went wrong").
- **Dates.** Show relative times ("3h ago") with the absolute time in a tooltip, in the Europe/Brussels timezone.

---

## 6. Delivery phases

Each phase ends with working, testable software and a stop for my review.

| # | Phase | Done when |
|---|---|---|
| 0 | **Audit & plan.** Read the code, confirm or adjust this plan, list risks, propose the settings storage and folder layout | I approve the plan |
| 1 | **Backend foundation.** `config.py`, lazy Groq client, settings extraction, DB migrations and backfill, logger and event hook, FastAPI skeleton with `/api/health`, pytest setup | `python run_agent.py` behaves exactly as before; API tests pass |
| 2 | **Frontend shell & design system.** Vite app, tokens, theme, sidebar layout, routing, API client, toasts, empty/loading/error components, `start.ps1` | `start.ps1` opens the app with working navigation in both themes |
| 3 | **Profile editor.** Resume API with validation, backups and atomic save; all section editors, reordering, YAML mode, history and restore | I can add, edit, delete and reorder every section, and the saved YAML round-trips through the CLI pipeline |
| 4 | **Run agent.** Run manager, SSE, start dialog, live stepper and logs, cancel, history | A full run from the UI matches the CLI output, and cancel works mid-tailoring |
| 5 | **Jobs & Apply workspace.** Grid, filters, detail sheet, apply checklist, status tracking, per-job tailor and cover letter, auto-fill | I can go from a found job to "applied" entirely in the UI |
| 6 | **Documents & Dashboard.** Library, DOCX preview, orphan cleanup, stats, funnel, ready-to-apply list | Every file in `output/` is visible and linked |
| 7 | **Onboarding & Settings.** Resume import (PDF/DOCX → LLM extraction → review), integrations tests, search settings editor, export and reset | A fresh clone with an empty YAML can be onboarded from a PDF resume |
| 8 | **Polish & QA.** Accessibility pass, keyboard shortcuts, performance (virtualise large tables), Playwright end-to-end smoke test, README "Using the UI" section | The checklist in section 7 passes |

## 7. Quality bar & testing

- **Backend:** pytest for the resume validation round-trip, settings, path-traversal protection, run lifecycle (mock Groq and the HTTP sources) and DB migrations against a copy of `jobs.db`.
- **Frontend:** Vitest + Testing Library for forms and reducers, and one Playwright end-to-end flow (edit profile → start a mocked run → open a job → mark it applied).
- **Code:** type-check both sides (`mypy --strict` on `api/` if practical, `tsc --noEmit`) and lint (ruff, eslint + prettier). Add no new global state. Keep the existing modules importable without side effects.
- **Dependencies:** add backend dependencies to `requirements.txt`, and pin frontend dependencies in `package.json`. Update `.gitignore` for `web/node_modules`, `web/dist`, `.ui_token`, `backups/` and `output/runs/`.
- **Commits:** make small commits per phase with clear messages. Never commit secrets or generated files.

## 8. Out of scope

Multi-user support, authentication providers, cloud deployment, mobile layouts below 768px, fully automatic submission of applications (a human always clicks submit), and scraping sites that forbid it.

**Start with Phase 0 only:** read the code and reply with your confirmed plan, risks and open questions. Write no code yet.
