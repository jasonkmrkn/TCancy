import hashlib
import uuid

from fastapi import Request

from app import config
from app.clientip import client_ip
from app.ratelimit import enforce


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def register(request: Request) -> None:
    """Both registration endpoints share this one budget per address."""
    enforce("register", client_ip(request), config.REGISTER_LIMIT, config.REGISTER_WINDOW_SECONDS)


def login(request: Request, username: str) -> None:
    """Per address first; the per-username budget is only touched once the address is allowed.

    The username is part of the key together with the address, so one client cannot use up
    the budget somebody else has for the same account from another address.
    """
    ip = client_ip(request)
    enforce("login_ip", ip, config.LOGIN_IP_LIMIT, config.LOGIN_IP_WINDOW_SECONDS)
    enforce(
        "login_user",
        f"{ip}|{_digest(username.strip().lower())}",
        config.LOGIN_USER_LIMIT,
        config.LOGIN_USER_WINDOW_SECONDS,
    )


def delete_account(request: Request, user_id: uuid.UUID | str) -> None:
    enforce(
        "delete_account",
        f"{client_ip(request)}|{user_id}",
        config.DELETE_ACCOUNT_LIMIT,
        config.DELETE_ACCOUNT_WINDOW_SECONDS,
    )