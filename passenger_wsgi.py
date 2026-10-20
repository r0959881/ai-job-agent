"""Entry point for cPanel's "Setup Python App" (Phusion Passenger).

Passenger speaks WSGI; the app is ASGI (FastAPI), so a2wsgi bridges the two.
In the Python App settings use: startup file `passenger_wsgi.py`, entry point `application`.
Errors while starting end up in stderr.log in the application root.
"""
import os
import sys

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_ROOT)
os.chdir(APP_ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(APP_ROOT, ".env"))

if not os.environ.get("SECRET_KEY"):
    raise RuntimeError(
        "SECRET_KEY is not set. Add it under Setup Python App → Environment variables "
        "(generate one with: python manage.py secret-key), then restart the app."
    )

from a2wsgi import ASGIMiddleware  # noqa: E402

from api.app import create_app  # noqa: E402

application = ASGIMiddleware(create_app())
