"""Console logging that can also feed a run's progress events.

`log()` prints exactly like `print()` did before. When code runs inside
`event_scope(on_event, cancel_event)`, every message and step change is also
passed to `on_event(step, status, message, data)` and cancellation can be
checked with `check_cancelled()`. Scopes are context-local, so the CLI and
the web server never share state.
"""
import contextlib
import contextvars

_handler = contextvars.ContextVar("agent_event_handler", default=None)
_cancel = contextvars.ContextVar("agent_cancel_event", default=None)
_step = contextvars.ContextVar("agent_current_step", default=None)


class RunCancelled(Exception):
    """Raised between steps or jobs when the user cancels a run."""


@contextlib.contextmanager
def event_scope(on_event=None, cancel_event=None):
    tokens = (_handler.set(on_event), _cancel.set(cancel_event), _step.set(None))
    try:
        yield
    finally:
        _handler.reset(tokens[0])
        _cancel.reset(tokens[1])
        _step.reset(tokens[2])


def _emit(step, status, message="", data=None):
    handler = _handler.get()
    if handler is None:
        return
    try:
        handler(step, status, message, data or {})
    except Exception:  # A broken listener must never break the pipeline.
        pass


def log(message="", level="info", data=None, **print_kwargs):
    """Print a console line and emit it as a log event for the current step."""
    try:
        print(message, **print_kwargs)
    except UnicodeEncodeError:
        # A console that cannot show emoji (cp1252 redirect) must never stop the pipeline.
        print(str(message).encode("ascii", "replace").decode("ascii"), **print_kwargs)
    _emit(_step.get(), "log", str(message).strip(), {"level": level, **(data or {})})


def step(name, status, message="", data=None):
    """Mark a pipeline step's status (started/succeeded/warning/failed/skipped/progress)."""
    if status == "started":
        _step.set(name)
    _emit(name, status, message, data)


def event(name, status, message="", data=None):
    """Emit an event without changing the current step."""
    _emit(name, status, message, data)


def is_cancelled():
    cancel = _cancel.get()
    return bool(cancel and cancel.is_set())


def check_cancelled():
    if is_cancelled():
        raise RunCancelled()
