"""The server database: users, their resume (with history), search settings and API keys.

Jobs, CVs and other documents are not stored here; they stay in each user's
browser and chosen folder. That keeps this database small: a few rows per user.

The same code runs on MySQL/MariaDB (cPanel) and SQLite (local runs, tests).
API keys are encrypted with a key derived from SECRET_KEY.
"""
import base64
import hashlib
import json
import threading
from datetime import UTC, datetime

import sqlalchemy as sa
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.dialects import mysql

from api import server_config

KEEP_VERSIONS = 20
LongText = sa.Text().with_variant(mysql.MEDIUMTEXT(), "mysql")

metadata = sa.MetaData()

users = sa.Table(
    "users", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("email", sa.String(320), unique=True, nullable=True),
    sa.Column("name", sa.String(200), nullable=False, default=""),
    sa.Column("picture", sa.String(1000), nullable=False, default=""),
    sa.Column("created_at", sa.String(40), nullable=False),
    sa.Column("last_login_at", sa.String(40), nullable=False),
    mysql_charset="utf8mb4",
)

identities = sa.Table(
    "identities", metadata,
    sa.Column("provider", sa.String(20), primary_key=True),
    sa.Column("subject", sa.String(255), primary_key=True),
    sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    mysql_charset="utf8mb4",
)

resumes = sa.Table(
    "resumes", metadata,
    sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("yaml_text", LongText, nullable=False),
    sa.Column("updated_at", sa.String(40), nullable=False),
    mysql_charset="utf8mb4",
)

resume_versions = sa.Table(
    "resume_versions", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    sa.Column("backup_id", sa.String(80), nullable=False),
    sa.Column("label", sa.String(40), nullable=False, default=""),
    sa.Column("created_at", sa.String(40), nullable=False),
    sa.Column("yaml_text", LongText, nullable=False),
    mysql_charset="utf8mb4",
)

user_settings = sa.Table(
    "user_settings", metadata,
    sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("data", LongText, nullable=False),
    sa.Column("updated_at", sa.String(40), nullable=False),
    mysql_charset="utf8mb4",
)

user_secrets = sa.Table(
    "user_secrets", metadata,
    sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("name", sa.String(64), primary_key=True),
    sa.Column("value", sa.Text, nullable=False),
    mysql_charset="utf8mb4",
)

_engine_lock = threading.Lock()
_engine: sa.Engine | None = None
_engine_url = ""


def now():
    return datetime.now(UTC).isoformat()


def engine():
    """One engine per database URL. MySQL connections are recycled before shared hosts drop idle ones."""
    global _engine, _engine_url
    url = server_config.database_url()
    with _engine_lock:
        if _engine is None or url != _engine_url:
            options: dict = {"pool_pre_ping": True}
            if url.startswith("mysql"):
                options.update(pool_recycle=280, pool_size=3, max_overflow=2)
            _engine = sa.create_engine(url, **options)
            _engine_url = url
            metadata.create_all(_engine)
        return _engine


def reset_engine():
    """Forget the engine (tests switch databases between cases)."""
    global _engine, _engine_url
    with _engine_lock:
        if _engine is not None:
            _engine.dispose()
        _engine, _engine_url = None, ""


def init_schema():
    metadata.create_all(engine())


# --------------------------------------------------------------------------------- users

def _user(row):
    return dict(row._mapping) if row else None


def get_user(user_id):
    with engine().connect() as conn:
        return _user(conn.execute(sa.select(users).where(users.c.id == user_id)).first())


def sign_in(provider, subject, email, name="", picture=""):
    """Find or create the user for an identity. Returns (user, created).

    A second provider with the same verified email signs into the same account,
    so a user can use Google one day and LinkedIn the next.
    """
    email = (email or "").strip().lower() or None
    stamp = now()
    with engine().begin() as conn:
        row = conn.execute(
            sa.select(users).join(identities, identities.c.user_id == users.c.id)
            .where(identities.c.provider == provider, identities.c.subject == subject)
        ).first()
        created = False
        if row is None and email:
            row = conn.execute(sa.select(users).where(users.c.email == email)).first()
        if row is None:
            result = conn.execute(users.insert().values(email=email, name=name or "", picture=picture or "",
                                                        created_at=stamp, last_login_at=stamp))
            user_id = result.inserted_primary_key[0]
            created = True
        else:
            user_id = row._mapping["id"]
            changes = {"last_login_at": stamp}
            if name:
                changes["name"] = name
            if picture:
                changes["picture"] = picture
            conn.execute(users.update().where(users.c.id == user_id).values(**changes))
        known = conn.execute(sa.select(identities.c.user_id).where(
            identities.c.provider == provider, identities.c.subject == subject)).first()
        if known is None:
            conn.execute(identities.insert().values(provider=provider, subject=subject, user_id=user_id))
        user = _user(conn.execute(sa.select(users).where(users.c.id == user_id)).first())
    return user, created


def providers_for(user_id):
    with engine().connect() as conn:
        return [row.provider for row in conn.execute(
            sa.select(identities.c.provider).where(identities.c.user_id == user_id))]


def delete_user(user_id):
    """Remove the account and everything stored for it."""
    with engine().begin() as conn:
        for table in (identities, resumes, resume_versions, user_settings, user_secrets):
            conn.execute(table.delete().where(table.c.user_id == user_id))
        conn.execute(users.delete().where(users.c.id == user_id))


# -------------------------------------------------------------------------------- resume

def get_resume_text(user_id):
    with engine().connect() as conn:
        row = conn.execute(sa.select(resumes.c.yaml_text).where(resumes.c.user_id == user_id)).first()
    return row.yaml_text if row else ""


def set_resume_text(user_id, text):
    with engine().begin() as conn:
        updated = conn.execute(resumes.update().where(resumes.c.user_id == user_id)
                               .values(yaml_text=text, updated_at=now())).rowcount
        if not updated:
            conn.execute(resumes.insert().values(user_id=user_id, yaml_text=text, updated_at=now()))


def add_version(user_id, backup_id, label, text, keep=KEEP_VERSIONS):
    with engine().begin() as conn:
        conn.execute(resume_versions.insert().values(user_id=user_id, backup_id=backup_id, label=label or "",
                                                     created_at=now(), yaml_text=text))
        old = [row.id for row in conn.execute(
            sa.select(resume_versions.c.id).where(resume_versions.c.user_id == user_id)
            .order_by(resume_versions.c.id.desc()).offset(keep))]
        if old:
            conn.execute(resume_versions.delete().where(resume_versions.c.id.in_(old)))


def list_versions(user_id):
    query = (sa.select(resume_versions.c.backup_id, resume_versions.c.label, resume_versions.c.created_at,
                       sa.func.length(resume_versions.c.yaml_text).label("size"))
             .where(resume_versions.c.user_id == user_id).order_by(resume_versions.c.id.desc()))
    with engine().connect() as conn:
        return [dict(row._mapping) for row in conn.execute(query)]


def get_version(user_id, backup_id):
    with engine().connect() as conn:
        row = conn.execute(sa.select(resume_versions.c.yaml_text).where(
            resume_versions.c.user_id == user_id, resume_versions.c.backup_id == backup_id)).first()
    if row is None:
        raise FileNotFoundError(backup_id)
    return row.yaml_text


# ------------------------------------------------------------------------------ settings

def get_settings(user_id):
    with engine().connect() as conn:
        row = conn.execute(sa.select(user_settings.c.data).where(user_settings.c.user_id == user_id)).first()
    if not row:
        return {}
    try:
        return json.loads(row.data) or {}
    except ValueError:
        return {}


def set_settings(user_id, data):
    text = json.dumps(data, ensure_ascii=False)
    with engine().begin() as conn:
        updated = conn.execute(user_settings.update().where(user_settings.c.user_id == user_id)
                               .values(data=text, updated_at=now())).rowcount
        if not updated:
            conn.execute(user_settings.insert().values(user_id=user_id, data=text, updated_at=now()))


# ------------------------------------------------------------------------------- secrets

def _fernet():
    seed = server_config.env("ENCRYPTION_KEY") or server_config.secret_key()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(seed.encode("utf-8")).digest()))


def get_secret(user_id, name):
    with engine().connect() as conn:
        row = conn.execute(sa.select(user_secrets.c.value).where(
            user_secrets.c.user_id == user_id, user_secrets.c.name == name)).first()
    if not row:
        return ""
    try:
        return _fernet().decrypt(row.value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""  # SECRET_KEY changed since the key was saved; the user enters it again


def set_secret(user_id, name, value):
    """Store an encrypted value, or delete it when value is empty."""
    with engine().begin() as conn:
        conn.execute(user_secrets.delete().where(user_secrets.c.user_id == user_id, user_secrets.c.name == name))
        if value:
            token = _fernet().encrypt(value.encode("utf-8")).decode("ascii")
            conn.execute(user_secrets.insert().values(user_id=user_id, name=name, value=token))
