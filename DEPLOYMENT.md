# Deploying AI Job Agent on Namecheap (cPanel)

This guide puts the web app on a Namecheap shared hosting plan (Stellar, Stellar Plus or
Stellar Business) at an address such as `https://jobs.yourdomain.com`. Allow about an hour
the first time; most of it is waiting for SSL and for `pip install`.

## How the hosted app works

- **Sign-in** is with Google or LinkedIn. Both only share name, email and photo. LinkedIn does
  not give apps your work history, so each user fills their profile by uploading a CV or their
  LinkedIn data export (Profile → Import).
- **On the server (MySQL):** users, their profile (resume) with its last 20 versions, their
  search settings, and their own Groq/Adzuna keys, encrypted. A few kilobytes per user.
- **On each user's computer:** every job found, application tracking, and all CVs, cover letters
  and reports. In Chrome and Edge these go into a folder the user picks; other browsers keep them
  in browser storage. Nothing about jobs or documents is stored on the server.
- **Runs are driven by the browser tab:** one search or one CV per request, so no request runs
  longer than about 40 seconds. Users keep the tab open while a run is going.
- Not in the hosted version: reading Gmail job alerts (Google's review for that permission is
  long and costly) and browser auto-fill (a server cannot open a browser on the user's PC).

What you need: the hosting account, a domain on it, about 15 minutes in Google Cloud Console and
LinkedIn Developers, and on your own PC Python 3.11+ and Node.js 18+ (to build the package).

---

## 1. Check your hosting

1. Log in to cPanel (Namecheap dashboard → Hosting List → **Go to cPanel**).
2. Under **Software**, open **Setup Python App** and click **Create Application**. Open the
   **Python version** list: you need **3.11 or newer**. Pick the highest one offered. (If there
   is nothing newer than 3.10, ask Namecheap support to enable it; the app does not run on older
   versions.) Close the form without saving for now.
3. Under **Advanced**, look for **Terminal**. If it is there you can run commands in the browser.
   Otherwise turn on SSH: Namecheap dashboard → your hosting → **SSH access**, then connect with
   `ssh -p 21098 cpanelusername@yourdomain.com`. The Terminal or SSH is needed in step 6.

## 2. Create the subdomain and turn on HTTPS

1. cPanel → **Domains** → **Create A New Domain** (on older cPanel: **Subdomains**). Enter
   `jobs.yourdomain.com`, untick "Share document root", keep the suggested folder
   (e.g. `/home/cpanelusername/jobs.yourdomain.com`), click **Submit**.
2. cPanel → **SSL/TLS Status** → tick `jobs.yourdomain.com` → **Run AutoSSL**. Wait until it
   shows a valid certificate (a few minutes, sometimes up to an hour). Google and LinkedIn
   only accept `https://` sign-in addresses, so this must be done before testing sign-in.

## 3. Create the MySQL database

1. cPanel → **Databases** → **MySQL Database Wizard**.
2. Database name: `jobs` (cPanel makes it `cpanelusername_jobs`) → **Next Step**.
3. User: `jobs`, with a long generated password (use **Password Generator**, copy it somewhere
   safe) → **Create User**.
4. Tick **ALL PRIVILEGES** → **Next Step**.
5. Write down the connection string you will use in step 5:

   ```
   mysql+pymysql://cpanelusername_jobs:PASSWORD@localhost/cpanelusername_jobs?charset=utf8mb4
   ```

   If the password contains `@ : / ? # & %` or spaces, replace each with its URL code
   (`@` → `%40`, `:` → `%3A`, `/` → `%2F`, `?` → `%3F`, `#` → `%23`, `&` → `%26`, `%` → `%25`),
   or generate a password with only letters and digits.

## 4. Build the package and upload it

On your own PC, in the project folder:

```powershell
cd web; npm ci; cd ..
.\.venv\Scripts\python.exe deploy\make_package.py
```

This builds the web app and writes `deploy\build\ai-job-agent-<date>.zip` (under 1 MB). It
contains only the app code. Your `resume_data.yaml`, `.env`, `jobs.db`, Google tokens and PDFs
are never included.

In cPanel → **File Manager**:

1. In your home folder (`/home/cpanelusername`), create a folder **`ai-job-agent`**. Keep it
   outside `public_html` so the code cannot be downloaded.
2. Open it, click **Upload**, choose the zip. When it finishes, go back, right-click the zip →
   **Extract** → extract into `/home/cpanelusername/ai-job-agent`. Delete the zip afterwards.

## 5. Create the Python app

cPanel → **Setup Python App** → **Create Application**:

| Field | Value |
|---|---|
| Python version | 3.11 or newer (the highest offered) |
| Application root | `ai-job-agent` |
| Application URL | `jobs.yourdomain.com` (leave the path after it empty) |
| Application startup file | `passenger_wsgi.py` |
| Application Entry point | `application` |
| Passenger log file | `/home/cpanelusername/ai-job-agent/stderr.log` |

Click **Create**. At the top of the page cPanel now shows a command like
`source /home/cpanelusername/virtualenv/ai-job-agent/3.11/bin/activate && cd /home/cpanelusername/ai-job-agent`.
Copy it; you need it in step 6.

Still on this page, under **Environment variables**, click **Add Variable** for each of these
and then **Save**:

| Name | Value |
|---|---|
| `PUBLIC_URL` | `https://jobs.yourdomain.com` (no slash at the end) |
| `SECRET_KEY` | a long random string. Make one in step 6 with `python manage.py secret-key`, or use any 60+ random letters and digits |
| `DATABASE_URL` | the connection string from step 3 |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | from step 7 (add them later) |
| `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` | from step 8 (add them later) |
| `ALLOWED_EMAILS` | optional: only these people may sign up, e.g. `me@gmail.com, @mycompany.com`. Leave it out to allow everyone |

Keep `SECRET_KEY` the same forever: changing it signs everyone out and makes the saved API keys
unreadable (users would have to enter them again).

## 6. Install the packages and check the setup

Open **Terminal** (or SSH in) and paste the command from step 5, then:

```bash
pip install --upgrade pip
pip install --no-cache-dir -r requirements.txt
python manage.py secret-key      # only if you still need a SECRET_KEY for step 5
python manage.py check
```

`pip install` takes a few minutes (the job scrapers bring in pandas and numpy). If it stops
with `Killed`, the host ran out of memory for a moment; run the same command again.

No Terminal or SSH? On the Setup Python App page, enter `requirements.txt` under
**Configuration files**, click **Add**, then **Run Pip Install**. You can then skip
`manage.py check`; step 9 shows the same problems.

`manage.py check` reads the environment variables you saved in cPanel only when they are also
exported in the Terminal session. If it reports a missing `SECRET_KEY` or `DATABASE_URL` that
you did set in cPanel, either export them for the check
(`export DATABASE_URL='...' PUBLIC_URL='https://jobs.yourdomain.com' SECRET_KEY='...'`) or copy
`.env.example` to `.env` in the app folder and fill it in. A `.env` file there works too, and
values from cPanel take precedence.

It should end with **All good.** Fix anything it lists. It also prints the exact sign-in redirect
URIs you need in steps 7 and 8. The database tables are created automatically.

Finally go back to **Setup Python App** and click **Restart**.

## 7. Sign in with Google

1. Go to <https://console.cloud.google.com/>, create a project (e.g. "AI Job Agent").
2. **APIs & Services → OAuth consent screen** (called **Google Auth Platform** in newer
   consoles) → **Get started**: app name, your support email, audience **External**, your contact
   email → **Create**.
3. **Branding**: add `yourdomain.com` under *Authorized domains*. Add a home page link and a
   privacy policy link if you have them.
4. **Data access → Add or remove scopes**: tick `openid`, `.../auth/userinfo.email` and
   `.../auth/userinfo.profile` → **Update** → **Save**. These are basic scopes, so Google does
   not need to review the app.
5. **Audience → Publish app** (status *In production*). While it is in *Testing*, only the test
   users you list can sign in.
6. **Clients → Create client** → type **Web application**, name "AI Job Agent".
   - Authorized JavaScript origins: `https://jobs.yourdomain.com`
   - Authorized redirect URIs: `https://jobs.yourdomain.com/api/auth/google/callback`
7. **Create**, then copy the **Client ID** and **Client secret** into `GOOGLE_CLIENT_ID` and
   `GOOGLE_CLIENT_SECRET` (step 5). Restart the app.

## 8. Sign in with LinkedIn

1. Go to <https://www.linkedin.com/developers/apps> → **Create app**. LinkedIn requires a
   LinkedIn **Page** to attach the app to; if you have none, create a free one from the link on
   that form. Add a logo, accept the terms → **Create app**.
2. **Settings** tab: next to the Page, click **Verify** and follow the link (a Page admin must
   approve it, which can be you).
3. **Products** tab → **Sign In with LinkedIn using OpenID Connect** → **Request access**
   (approved immediately).
4. **Auth** tab → *Authorized redirect URLs for your app* → add
   `https://jobs.yourdomain.com/api/auth/linkedin/callback` → **Update**.
5. Copy the **Client ID** and **Primary Client Secret** (same tab) into `LINKEDIN_CLIENT_ID` and
   `LINKEDIN_CLIENT_SECRET` (step 5). Restart the app.

You can set up just one provider; the sign-in page only shows the ones that are configured.

## 9. Force HTTPS and test

1. File Manager → the subdomain's folder (`/home/cpanelusername/jobs.yourdomain.com`) → turn on
   **Settings → Show Hidden Files** → edit `.htaccess`. cPanel wrote a block marked
   `CLOUDLINUX PASSENGER CONFIGURATION` there; leave it alone and add these lines **above** it:

   ```apache
   RewriteEngine On
   RewriteCond %{HTTPS} !=on
   RewriteRule ^ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]
   ```

2. Open `https://jobs.yourdomain.com/api/health`. You should see `"status":"ok"` and
   `"database":true`.
3. Open `https://jobs.yourdomain.com`, sign in with Google or LinkedIn, then:
   - in onboarding add your Groq key (free at <https://console.groq.com/keys>) and import your CV
     or LinkedIn export,
   - choose a documents folder (use Chrome or Edge),
   - start a small run (one region, one role, *Max CVs to tailor* = 1).

### Bringing your existing profile over

Your current `resume_data.yaml` (and `agent_settings.yaml`) can go straight into your account
instead of re-importing. Upload them to the `ai-job-agent` folder, then in the Terminal (step 6):

```bash
python manage.py import-profile you@gmail.com resume_data.yaml agent_settings.yaml
rm resume_data.yaml agent_settings.yaml
```

Use the email of the Google or LinkedIn account you sign in with. Alternatively, paste the YAML
into Profile → *Advanced: Edit YAML* in the app.

## Updating to a new version

1. On your PC: `.\.venv\Scripts\python.exe deploy\make_package.py`.
2. File Manager: upload the new zip to `ai-job-agent` and extract it there, letting it
   overwrite. Environment variables are kept by cPanel. The package includes
   `tmp/restart.txt`, which makes Passenger reload the app.
3. If `requirements.txt` changed, run `pip install --no-cache-dir -r requirements.txt` again
   (step 6). Then click **Restart** on the Setup Python App page.

## Backups

All server data is in the MySQL database: cPanel → **Backup** → *Download a MySQL Database
Backup*. Users' jobs and documents are on their own computers; the Storage settings explain
how they can keep a copy (the folder plus `ai-job-agent-data.json`).

`python manage.py users` (in the Terminal, step 6) lists the accounts.

## Troubleshooting

| Problem | What to do |
|---|---|
| The site shows a Passenger error or "Incomplete response" | Read `ai-job-agent/stderr.log`. A missing package means `pip install` did not finish (step 6). `SECRET_KEY is not set` means step 5. |
| `{"detail":"Unknown host."}` | `PUBLIC_URL` must be exactly the address you open, with `https://`. For extra addresses add `ALLOWED_HOSTS=www.jobs.yourdomain.com`. |
| `"database": false` on `/api/health` | Check `DATABASE_URL`: user and database names include your cPanel prefix, the user has ALL PRIVILEGES on the database, and special characters in the password are URL-encoded. |
| `Specified key was too long` while creating tables | The MySQL/MariaDB version is very old. Ask Namecheap support which server your account is on; MariaDB 10.3+ or MySQL 5.7+ is needed. |
| Google: `redirect_uri_mismatch` | The redirect URI in the Google client must be exactly `https://jobs.yourdomain.com/api/auth/google/callback`, and `PUBLIC_URL` must match. |
| LinkedIn: "The redirect_uri does not match" or `unauthorized_scope_error` | Check the Auth tab's redirect URL, and that the OpenID Connect product shows as *Added* on the Products tab. |
| "This app is invite-only" | The email is not in `ALLOWED_EMAILS`. |
| Signed out after every restart | `SECRET_KEY` is missing in the environment variables, so a temporary one was used. Set it (step 5). |
| Searches on LinkedIn, Indeed or Glassdoor keep failing | Shared-hosting IP addresses are often blocked by these sites. The run skips a source after two failures. Lower *Results per search* in Settings → Search, add a proxy there, or rely on the other sources (VDAB, Jobat, StepStone, Adzuna...). |
| A search ends with fewer descriptions than usual | Each search may spend at most `SEARCH_TIME_BUDGET` seconds (default 35) on job detail pages. Raise it only if your host allows long requests. |
| A user's CVs are not in their folder | In Firefox and Safari files stay in browser storage (Documents page → Download). In Chrome and Edge the browser asks for folder permission again after a restart: Settings → Storage → *Allow access again*. |

## Things to know

- **Scraping and the host's rules.** LinkedIn, Indeed and Glassdoor do not allow automated
  searching in their terms, and heavy use from your hosting account can get its IP address
  blocked or draw complaints. Keep runs small, or turn those sources off for everyone in each
  user's settings and rely on the public job APIs.
- **Shared hosting limits.** Stellar plans limit CPU, memory and simultaneous processes per
  account. A handful of people running searches at once is fine. For dozens of active users,
  move to a VPS (the same code runs there with `uvicorn` or under Passenger).
- **Local use still works.** On your own PC, `.\start.ps1` runs the same app on
  `http://127.0.0.1:8765` with a local SQLite database and a developer sign-in, without Google
  or LinkedIn keys. `python run_agent.py` is still the single-user command line (with Gmail),
  using `requirements-local.txt`.
