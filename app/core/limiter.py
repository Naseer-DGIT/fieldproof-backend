"""Rate limiter singleton.

Lives in its own module so routers can import it without a circular
import with app.main.

Limits are environment-derived:

- dev and lab: 1000/minute. The test suite calls /auth/login dozens of
  times in under a minute; a production limit would exhaust and break
  unrelated tests.
- staging and prod: the real limits (10/minute for login, 60/minute
  for event sync).

The limits can be overridden via env vars for the rate limit test:

    LOGIN_LIMIT=10/minute uvicorn ...
"""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

_ENV = os.getenv("ENVIRONMENT", "dev")

if _ENV in ("staging", "prod"):
    LOGIN_LIMIT = os.getenv("LOGIN_LIMIT", "10/minute")
    EVENTS_LIMIT = os.getenv("EVENTS_LIMIT", "60/minute")
else:
    LOGIN_LIMIT = os.getenv("LOGIN_LIMIT", "1000/minute")
    EVENTS_LIMIT = os.getenv("EVENTS_LIMIT", "1000/minute")

limiter = Limiter(key_func=get_remote_address)
