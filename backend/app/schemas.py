import re
import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

PREFERRED_TYPES = ("internship", "fulltime", "parttime", "contract")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?\d{8,15}$")


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str

    @field_validator("username")
    @classmethod
    def clean_username(cls, v: str) -> str:
        v = v.strip().lower()
        if not 3 <= len(v) <= 64:
            raise ValueError("username must be 3-64 characters")
        if any(ord(c) < 32 or ord(c) == 127 for c in v):
            raise ValueError("username must not contain control characters")
        return v


class AlumniRegisterIn(LoginIn):
    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        if not 8 <= len(v) <= 256:
            raise ValueError("password must be 8-256 characters")
        return v


class ApplicantProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str
    email: str
    phone: str
    nik: str
    address: str
    birth_date: date
    angkatan: int
    skill_ids: list[uuid.UUID]
    preferred_type: str | None = None
    preferred_location: str | None = None

    @field_validator("full_name", "address", "preferred_location", mode="before")
    @classmethod
    def strip_text(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("full_name")
    @classmethod
    def check_full_name(cls, v: str) -> str:
        if not 1 <= len(v) <= 200:
            raise ValueError("full_name must be 1-200 characters")
        return v

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) > 254 or not EMAIL_RE.match(v):
            raise ValueError("email must be a valid address of at most 254 characters")
        return v

    @field_validator("phone")
    @classmethod
    def check_phone(cls, v: str) -> str:
        v = v.strip()
        if not PHONE_RE.match(v):
            raise ValueError("phone must be 8-15 digits, optionally starting with +")
        return v

    @field_validator("nik")
    @classmethod
    def check_nik(cls, v: str) -> str:
        v = v.strip()
        if not (len(v) == 16 and v.isascii() and v.isdigit()):
            raise ValueError("nik must be exactly 16 digits")
        return v

    @field_validator("address")
    @classmethod
    def check_address(cls, v: str) -> str:
        if not 1 <= len(v) <= 500:
            raise ValueError("address must be 1-500 characters")
        return v

    @field_validator("birth_date")
    @classmethod
    def check_birth_date(cls, v: date) -> date:
        today = date.today()
        age = today.year - v.year - ((today.month, today.day) < (v.month, v.day))
        if not 15 <= age <= 100:
            raise ValueError("age must be between 15 and 100 years")
        return v

    @field_validator("angkatan")
    @classmethod
    def check_angkatan(cls, v: int) -> int:
        if not 1990 <= v <= date.today().year:
            raise ValueError("angkatan must be between 1990 and the current year")
        return v

    @field_validator("skill_ids")
    @classmethod
    def check_skill_ids(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if not 1 <= len(v) <= 30:
            raise ValueError("skill_ids must contain 1-30 items")
        if len(set(v)) != len(v):
            raise ValueError("skill_ids must be unique")
        return v

    @field_validator("preferred_type", mode="before")
    @classmethod
    def check_preferred_type(cls, v):
        if v is None or v == "":
            return None
        if v not in PREFERRED_TYPES:
            raise ValueError("preferred_type must be one of " + ", ".join(PREFERRED_TYPES))
        return v

    @field_validator("preferred_location")
    @classmethod
    def check_preferred_location(cls, v: str | None) -> str | None:
        if not v:
            return None
        if len(v) > 100:
            raise ValueError("preferred_location must be at most 100 characters")
        return v


class RegisterIn(AlumniRegisterIn):
    profile: ApplicantProfileIn


class AlumniProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = None
    company: str | None = None
    angkatan: int | None = None

    @model_validator(mode="after")
    def check_fields(self):
        for name in ("full_name", "company"):
            v = getattr(self, name)
            if v is not None:
                v = v.strip() or None
                if v is not None and len(v) > 200:
                    raise ValueError(name + " must be at most 200 characters")
                setattr(self, name, v)
        if self.angkatan is not None and not 1990 <= self.angkatan <= date.today().year:
            raise ValueError("angkatan must be between 1990 and the current year")
        return self


class AlumniRegisterProfileIn(AlumniProfileIn):
    """Profile sent at alumni registration: all three fields are required."""

    full_name: str
    company: str
    angkatan: int

    @model_validator(mode="after")
    def check_required(self):
        # AlumniProfileIn turns blank text into None, so reject both None and blank.
        for name in ("full_name", "company"):
            if not (getattr(self, name) or "").strip():
                raise ValueError(name + " must not be blank")
        return self


class AlumniRegisterWithProfileIn(AlumniRegisterIn):
    profile: AlumniRegisterProfileIn


JOB_TYPES = ("internship", "fulltime", "parttime", "contract")
WORK_MODES = ("onsite", "hybrid", "remote")


class JobIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    company: str
    type: str
    work_mode: str
    location: str | None = None
    description: str
    requirements: str | None = None
    deadline: date | None = None
    skill_ids: list[uuid.UUID] = []

    @field_validator("title", "company", "location", "description", "requirements", mode="before")
    @classmethod
    def strip_text(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("title", "company")
    @classmethod
    def check_short(cls, v: str) -> str:
        if not 1 <= len(v) <= 200:
            raise ValueError("must be 1-200 characters")
        return v

    @field_validator("type")
    @classmethod
    def check_type(cls, v: str) -> str:
        if v not in JOB_TYPES:
            raise ValueError("type must be one of: " + ", ".join(JOB_TYPES))
        return v

    @field_validator("work_mode")
    @classmethod
    def check_work_mode(cls, v: str) -> str:
        if v not in WORK_MODES:
            raise ValueError("work_mode must be one of: " + ", ".join(WORK_MODES))
        return v

    @field_validator("location")
    @classmethod
    def check_location(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if len(v) > 200:
            raise ValueError("location must be at most 200 characters")
        return v

    @field_validator("description")
    @classmethod
    def check_description(cls, v: str) -> str:
        if not 1 <= len(v) <= 10000:
            raise ValueError("description must be 1-10000 characters")
        return v

    @field_validator("requirements")
    @classmethod
    def check_requirements(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if len(v) > 10000:
            raise ValueError("requirements must be at most 10000 characters")
        return v

    @field_validator("skill_ids")
    @classmethod
    def check_skill_ids(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(v) > 20:
            raise ValueError("at most 20 skills")
        if len(set(v)) != len(v):
            raise ValueError("skills must be unique")
        return v


class ApplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cv_document_id: uuid.UUID
    intro_video_document_id: uuid.UUID | None = None
    cover_note: str | None = Field(default=None, max_length=2000)
    consents: list[str] = Field(default_factory=list)


class StatusChangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["shortlisted", "accepted", "rejected"]
    note: str | None = Field(default=None, max_length=500)


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("reason must not be empty")
        return v


class UserStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "suspended"]


class TestimonialIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_id: uuid.UUID
    content: str = Field(min_length=20, max_length=1000)
    show_name: StrictBool

    @field_validator("content")
    @classmethod
    def strip_content(cls, v):
        v = v.strip()
        if not 20 <= len(v) <= 1000:
            raise ValueError("content must be 20-1000 characters")
        return v


class TestimonialStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["approved", "hidden"]
