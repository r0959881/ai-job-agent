"""Server maintenance commands. Run them in the app's virtual environment (cPanel Terminal or SSH).

    python manage.py secret-key     print a new random SECRET_KEY to paste into the environment variables
    python manage.py check          check the settings, connect to the database and create its tables
    python manage.py users          list the accounts (id, email, created, last sign-in)
    python manage.py import-profile EMAIL resume_data.yaml [agent_settings.yaml]
                                    copy a resume (and search settings) into an account; the user signs in
                                    with that email afterwards (creates the account if it does not exist yet)
"""
import secrets
import sys


def secret_key():
    print(secrets.token_urlsafe(48))
    return 0


def check():
    from api import server_config, store

    problems = []
    url = server_config.database_url()
    print(f"Database:      {url.split('@')[-1] if '@' in url else url}")
    try:
        store.init_schema()
        with store.engine().connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        print("               connected, tables ready")
    except Exception as error:  # report every problem at once instead of stopping at the first
        problems.append(f"The database is not reachable: {error}")
    public = server_config.public_url()
    print(f"PUBLIC_URL:    {public or '(not set)'}")
    if not public:
        problems.append("PUBLIC_URL is not set (e.g. https://jobs.example.com). Sign-in redirects need it.")
    elif not public.startswith("https://"):
        problems.append("PUBLIC_URL should start with https:// (Google and LinkedIn require HTTPS).")
    print(f"SECRET_KEY:    {'set' if server_config.env('SECRET_KEY') else '(not set)'}")
    if not server_config.env("SECRET_KEY"):
        problems.append("SECRET_KEY is not set. Generate one with: python manage.py secret-key")
    providers = [name for name in ("google", "linkedin") if server_config.oauth_client(name)]
    print(f"Sign-in with:  {', '.join(providers) or '(none)'}")
    if not providers:
        problems.append("Neither GOOGLE_CLIENT_ID/SECRET nor LINKEDIN_CLIENT_ID/SECRET is set, so nobody can sign in.")
    if public:
        for name in providers:
            print(f"               {name} redirect URI: {public}/api/auth/{name}/callback")
    if server_config.dev_login_enabled():
        problems.append("AI_JOB_AGENT_DEV_LOGIN is on: anyone could sign in as any email. Remove it on a server.")
    from config import WEB_DIST

    if not (WEB_DIST / "index.html").exists():
        problems.append("web/dist is missing. Build the web app (cd web && npm run build) and upload web/dist.")
    if problems:
        print("\nProblems:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nAll good.")
    return 0


def users():
    import sqlalchemy as sa

    from api import store

    with store.engine().connect() as conn:
        rows = conn.execute(sa.select(store.users).order_by(store.users.c.id)).all()
    for row in rows:
        print(f"{row.id:>5}  {row.email or '-':<40} created {row.created_at[:10]}  last sign-in {row.last_login_at[:16]}")
    print(f"{len(rows)} account(s)")
    return 0


def import_profile(email="", resume_path="", settings_path=""):
    """Validate the YAML like the profile editor does, keep a version of what was there, then save."""
    from pathlib import Path

    import yaml

    import agent_settings
    import user_scope
    from api import store
    from api.models.settings import SearchSettings
    from api.services import resume_store

    if "@" not in email or not resume_path:
        print("Usage: python manage.py import-profile EMAIL resume_data.yaml [agent_settings.yaml]")
        return 2
    text = Path(resume_path).read_text(encoding="utf-8")
    try:
        resume_store.parse_raw(text)
    except resume_store.ResumeInvalid as exc:
        print(f"{resume_path} has problems:")
        for error in exc.errors:
            print(f"  line {error.get('line')}: {error.get('message')}")
        return 1
    user, created = store.sign_in("import", email.strip().lower(), email, "")
    with user_scope.use(user["id"]):
        _etag, backup_id = resume_store.save_raw(text)
        if settings_path:
            raw = yaml.safe_load(Path(settings_path).read_text(encoding="utf-8")) or {}
            merged = agent_settings._merge(agent_settings.DEFAULTS, raw)
            agent_settings.save(SearchSettings.model_validate(merged).model_dump(mode="json"))
    print(f"{'Created' if created else 'Updated'} account {user['id']} ({user['email']}): profile imported"
          f"{' and search settings' if settings_path else ''}{f', previous version kept as {backup_id}' if backup_id else ''}.")
    print("Sign in with Google or LinkedIn using that email address to see it.")
    return 0


COMMANDS = {"secret-key": secret_key, "check": check, "users": users, "import-profile": import_profile}

if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in COMMANDS:
        print(__doc__)
        sys.exit(2)
    sys.exit(COMMANDS[command](*sys.argv[2:]))
