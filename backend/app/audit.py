import json
import logging
import re
import uuid
from contextlib import contextmanager

from fastapi import Request
from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.clientip import client_address
from app.models import AuditLog, Base

log = logging.getLogger("tcancy.audit")

EXTRA_FIELDS = frozenset({
    "password", "full_name", "email", "phone", "nik", "address", "birth_date", "profile", "documents",
})

_ACTION = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")  # auth.login, account.delete
_NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")  # keys, roles, target types, field names
_WORD = re.compile(r"^[a-z][a-z0-9_.]{0,63}$")  # a text value inside details
_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")  
_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029]")
_MAX_ACTION = 64
_MAX_IP = 64
_MAX_USER_AGENT = 256
_MAX_DETAILS_BYTES = 2048
_MAX_LIST = 50
_MAX_INT = 2**53


def _known_fields() -> frozenset[str]:
    columns = {column.name for table in Base.metadata.tables.values() for column in table.columns}
    return frozenset(columns) | EXTRA_FIELDS


def details(fields=(), /, **numbers: int) -> dict:
    """The only sanctioned way to build the `details` of an audit entry.

    `fields` are names of fields (columns, or EXTRA_FIELDS) that something concerned;
    keyword arguments are counts, as plain integers. Anything else raises ValueError, and the
    message never repeats the rejected value.
    """
    if isinstance(fields, (str, bytes)):
        raise ValueError("fields must be a list of field names, not a string")
    known = _known_fields()
    out: dict = {}
    names = list(fields)
    if any(not isinstance(name, str) or name not in known for name in names):
        raise ValueError("fields may only contain known field names")
    names = set(names)
    if names:
        out["fields"] = sorted(names)
    for key, number in numbers.items():
        if not _NAME.match(key) or key == "fields":
            raise ValueError("a count needs a plain lower-case name other than 'fields'")
        if isinstance(number, bool) or not isinstance(number, int) or abs(number) > _MAX_INT:
            raise ValueError("count %r must be a plain integer" % key)
        out[key] = number
    return out


def client(request: Request) -> dict:
    """The ip and user_agent of a request, to pass on as record(..., **audit.client(request))."""
    return {"ip": client_address(request), "user_agent": request.headers.get("user-agent")}


@contextmanager
def quietly(db: Session, action: str):
    try:
        yield
    except Exception as exc:
        db.rollback()
        log.error("audit entry %s could not be written (%s)", action, type(exc).__name__)


def _clean(value, limit: int) -> str | None:
    """Text safe to store: no control characters (NUL makes PostgreSQL refuse the row), cut to size."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("expected text")
    value = value.encode("utf-8", "ignore").decode("utf-8")  # drop lone surrogates
    value = _CONTROL.sub("", value).strip()[:limit].strip()
    return value or None


def _uuid(value, label: str):
    if value is None or isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            pass
    raise ValueError("%s must be a UUID" % label)


def _name(value, label: str):
    if value is None:
        return None
    if not isinstance(value, str) or not _NAME.match(value):
        raise ValueError("%s must be a short lower-case name" % label)
    return value


def _check_value(key: str, value):
    if isinstance(value, bool):
        raise ValueError("details[%r] must be a number or a field name" % key)
    if isinstance(value, int):
        if abs(value) > _MAX_INT:
            raise ValueError("details[%r] is out of range" % key)
    elif isinstance(value, str):
        if not (_WORD.match(value) or _CODE.match(value)):
            raise ValueError("details[%r] must be a number or a field name" % key)
    elif isinstance(value, (list, tuple)):
        if len(value) > _MAX_LIST or not all(isinstance(v, str) and (_WORD.match(v) or _CODE.match(v)) for v in value):
            raise ValueError("details[%r] must be a short list of field names" % key)
    else:
        raise ValueError("details[%r] must be a number or a field name" % key)


def _checked_details(value) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("details must be a dict")
    for key, item in value.items():
        if not isinstance(key, str) or not _NAME.match(key):
            raise ValueError("details keys must be short lower-case names")
        _check_value(key, item)
    if len(json.dumps(value, separators=(",", ":"))) > _MAX_DETAILS_BYTES:
        raise ValueError("details is too large")
    return dict(value) or None


def record(db: Session, *, actor_id, actor_role, action, target_type=None, target_id=None,
           ip=None, user_agent=None, details: dict | None = None) -> None:
    """Frozen interface: write one audit entry in the caller's transaction, without committing."""
    if not isinstance(action, str) or len(action) > _MAX_ACTION or not _ACTION.match(action):
        raise ValueError("action must look like 'auth.login'")
    db.execute(
        insert(AuditLog).values(
            actor_id=_uuid(actor_id, "actor_id"),
            actor_role=_name(actor_role, "actor_role"),
            action=action,
            target_type=_name(target_type, "target_type"),
            target_id=_uuid(target_id, "target_id"),
            ip=_clean(ip, _MAX_IP),
            user_agent=_clean(user_agent, _MAX_USER_AGENT),
            details=_checked_details(details),
        )
    )