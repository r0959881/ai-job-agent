"""Which user the current request acts for.

The web server signs users in and wraps every request in `use(user_id)`. Inside
that scope the shared helpers read the user's own data from the database:
agent_settings.load() returns their search settings, config.load_resume_file()
their resume and `secret()` their API keys. Outside a scope (the command line,
tests of the pipeline) the same helpers read agent_settings.yaml,
resume_data.yaml and .env as before.

A scope caches what it loaded, so the relevance gate can call
agent_settings.load() once per job without a database query each time.
"""
import contextlib
import contextvars
import os

_current: contextvars.ContextVar["Scope | None"] = contextvars.ContextVar("user_scope", default=None)


class Scope:
    def __init__(self, user_id):
        self.user_id = user_id
        self._cache = {}

    def cached(self, key, load):
        if key not in self._cache:
            self._cache[key] = load()
        return self._cache[key]

    def forget(self, key):
        self._cache.pop(key, None)


def current():
    return _current.get()


@contextlib.contextmanager
def use(user_id):
    token = _current.set(Scope(user_id))
    try:
        yield _current.get()
    finally:
        _current.reset(token)


def secret(name):
    """An API key for the current user (from the database), or from the environment outside a scope."""
    scope = current()
    if scope is None:
        return os.environ.get(name, "")
    from api import store

    return scope.cached(f"secret:{name}", lambda: store.get_secret(scope.user_id, name))
