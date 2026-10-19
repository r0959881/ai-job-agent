"""Small read/write helpers for the API. Rows come back as dicts.

If the database or a newer table/column is missing (fresh clone, deleted
jobs.db), the schema is created on first use instead of failing.
"""
import sqlite3

from database import connect, init_db


def _run(sql, params, fetch):
    conn = connect()
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            cursor = conn.execute(sql, params)
            if fetch == "one":
                row = cursor.fetchone()
                return dict(row) if row else None
            if fetch == "all":
                return [dict(row) for row in cursor.fetchall()]
            return cursor.rowcount
    finally:
        conn.close()


def _with_schema(sql, params, fetch):
    try:
        return _run(sql, params, fetch)
    except sqlite3.OperationalError as error:
        if "no such table" not in str(error) and "no such column" not in str(error):
            raise
        init_db(quiet=True)
        return _run(sql, params, fetch)


def all_rows(sql, params=()):
    return _with_schema(sql, params, "all")


def one_row(sql, params=()):
    return _with_schema(sql, params, "one")


def execute(sql, params=()):
    """Run a write statement; returns the number of affected rows."""
    return _with_schema(sql, params, None)


def execute_many(statements):
    """Run several (sql, params) writes in one transaction."""
    init_db(quiet=True)
    conn = connect()
    try:
        with conn:
            for sql, params in statements:
                conn.execute(sql, params)
    finally:
        conn.close()
