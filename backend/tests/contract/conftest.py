"""Shared fixtures for the contract tests.

These tests describe what each frozen interface promises, so they must pass against the
stubs today and against the real implementations later. Do not assert on stub internals.
"""
import itertools
import os
import uuid

import pytest
from sqlalchemy.orm import Session

from app import config
from app.db import engine
from app.models import User
from helpers import password_hash


@pytest.fixture
def db():
    """A plain session, closed before tests/conftest.py truncates the tables."""
    with Session(engine) as session:
        yield session


@pytest.fixture
def make_user(db):
    counter = itertools.count(1)

    def _make(role="applicant", status="active"):
        username = "contract%d_%s" % (next(counter), uuid.uuid4().hex[:6])
        user = User(username=username, password_hash=password_hash(), role=role, status=status)
        db.add(user)
        db.commit()
        return user

    return _make


@pytest.fixture
def pdf_content():
    """A valid-looking PDF, larger than one 64 KiB storage chunk."""
    return b"%PDF-1.4\n" + b"contract test line\n" * 10000


@pytest.fixture
def files_on_disk():
    def _files():
        return set(os.listdir(config.UPLOAD_DIR)) if os.path.isdir(config.UPLOAD_DIR) else set()

    return _files