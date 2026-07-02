"""Who is making this request?

Databricks Apps forwards the signed-in user's identity on every request via
X-Forwarded-* headers. Header availability can vary by platform version, so we
check the known candidates in order and report which one matched (useful when
verifying a fresh deployment). Outside Databricks (local dev, tests) there are
no headers — identity falls back to "local".
"""
from fastapi import Request

EMAIL_HEADERS = ("x-forwarded-email", "x-forwarded-preferred-username", "x-forwarded-user")


def request_user(request: Request) -> dict[str, str]:
    for header in EMAIL_HEADERS:
        value = request.headers.get(header)
        if value:
            return {"user": value, "source": header}
    return {"user": "local", "source": "none"}


def user_email(request: Request) -> str:
    return request_user(request)["user"]
