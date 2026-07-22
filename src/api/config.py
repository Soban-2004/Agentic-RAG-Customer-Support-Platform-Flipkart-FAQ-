"""Shared config for the src/api/ routers -- read once at import time, same
pattern app.py used to use for its own module-level constants."""

import os

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        "Missing DATABASE_URL. Login + chat history need a Postgres database -- "
        "see README.md's Auth & chat history section."
    )
