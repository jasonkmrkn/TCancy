import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from app import policy

STATUSES = ("submitted", "shortlisted", "accepted", "rejected", "withdrawn")
ALL_SCOPES = ("profile", "cv", "video", "identity")


@pytest.mark.parametrize("status", STATUSES)
def test_no_consent_shows_nothing(status):
    assert policy.decide(status, [], "alumni") == policy.Visibility()


@pytest.mark.parametrize("status", STATUSES)
def test_cv_and_video_follow_their_own_scope(status):
    assert policy.decide(status, ["cv"], "alumni") == policy.Visibility(cv=True)
    assert policy.decide(status, ["video"], "alumni") == policy.Visibility(video=True)
    both = policy.decide(status, ["cv", "video"], "alumni")
    assert both == policy.Visibility(cv=True, video=True)


@pytest.mark.parametrize(
    "status,phone",
    [
        ("submitted", False),
        ("shortlisted", True),
        ("accepted", True),
        # never shown again once the application is rejected or withdrawn
        ("rejected", False),
        ("withdrawn", False),
    ],
)
def test_phone_only_from_shortlisted_with_profile_consent(status, phone):
    seen = policy.decide(status, ["profile"], "alumni")
    assert seen.profile is True and seen.phone is phone
    assert seen.cv is False and seen.video is False


def test_phone_needs_the_profile_consent():
    seen = policy.decide("accepted", ["cv", "video", "identity"], "alumni")
    assert seen.profile is False and seen.phone is False


def test_identity_scope_alone_changes_nothing():
    for status in STATUSES:
        assert policy.decide(status, ["identity"], "alumni") == policy.Visibility()


@pytest.mark.parametrize("role", ["applicant", "", "somebody"])
def test_other_roles_see_nothing(role):
    for status in STATUSES:
        assert policy.decide(status, ALL_SCOPES, role) == policy.Visibility()


def test_admin_owner_is_treated_like_alumni():
    for status in STATUSES:
        for scopes in ([], ["profile"], ["cv", "video"], list(ALL_SCOPES)):
            assert policy.decide(status, scopes, "admin") == policy.decide(
                status, scopes, "alumni"
            )


def test_unknown_status_never_shows_phone():
    seen = policy.decide("weird", ALL_SCOPES, "alumni")
    assert seen == policy.Visibility(profile=True, phone=False, cv=True, video=True)


def test_scopes_can_be_any_iterable():
    assert policy.decide("accepted", {"profile"}, "alumni").phone is True
    assert policy.decide("accepted", iter(["profile"]), "alumni").phone is True


def test_visibility_is_immutable():
    seen = policy.decide("accepted", ALL_SCOPES, "alumni")
    with pytest.raises(dataclasses.FrozenInstanceError):
        seen.phone = False


NOW = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(days=28)
PAST_WINDOW = LATER + timedelta(days=1)


def state(status="accepted", scopes=("identity",), expires_at=LATER, now=NOW, role="alumni"):
    return policy.identity_state(status, scopes, expires_at, now, role)


def test_identity_is_available_inside_the_window():
    assert state() == "available"
    assert state(now=LATER) == "available"  # still open at the very last moment


def test_identity_expires_after_the_window():
    assert state(now=LATER + timedelta(seconds=1)) == "expired"
    assert state(now=PAST_WINDOW) == "expired"


@pytest.mark.parametrize("status", [s for s in STATUSES if s != "accepted"])
def test_identity_is_locked_unless_accepted(status):
    assert state(status=status) == "locked"
    # past the window it is still locked, not expired
    assert state(status=status, now=PAST_WINDOW) == "locked"


def test_identity_is_locked_without_an_active_identity_consent():
    for scopes in ([], ["profile", "cv", "video"]):
        assert state(scopes=scopes) == "locked"
        assert state(scopes=scopes, now=PAST_WINDOW) == "locked"


def test_identity_without_a_recorded_window_stays_locked():
    assert state(expires_at=None) == "locked"


@pytest.mark.parametrize("role", ["applicant", "", "somebody"])
def test_identity_is_locked_for_other_roles(role):
    assert state(role=role) == "locked"


def test_admin_owner_identity_matches_alumni():
    for kwargs in ({}, {"now": PAST_WINDOW}, {"status": "shortlisted"}, {"scopes": []}):
        assert state(role="admin", **kwargs) == state(role="alumni", **kwargs)


def test_expiry_is_shown_only_when_not_locked():
    assert policy.shown_expiry("available", LATER) == LATER
    assert policy.shown_expiry("expired", LATER) == LATER
    assert policy.shown_expiry("locked", LATER) is None
    assert policy.shown_expiry("locked", None) is None


def test_identity_scopes_can_be_any_iterable():
    assert state(scopes={"identity"}) == "available"
    assert state(scopes=iter(["identity"])) == "available"


def window(status="accepted", scopes=("identity",), expires_at=LATER, now=NOW):
    return policy.identity_window(status, scopes, expires_at, now)


def test_window_states_do_not_depend_on_a_role():
    assert window() == "available"
    assert window(now=LATER) == "available"
    assert window(now=LATER + timedelta(seconds=1)) == "expired"
    assert window(expires_at=None) == "locked"
    assert window(scopes=[]) == "locked"
    assert window(status="shortlisted") == "locked"
    # past the window it is still locked, not expired, unless accepted with the consent
    assert window(status="rejected", now=PAST_WINDOW) == "locked"
    assert window(scopes=[], now=PAST_WINDOW) == "locked"


def test_window_scopes_can_be_any_iterable():
    assert window(scopes={"identity"}) == "available"
    assert window(scopes=iter(["identity"])) == "available"


def test_identity_state_is_the_window_for_owner_roles():
    for status in STATUSES:
        for scopes in ((), ("identity",), ("profile", "cv", "video"), ALL_SCOPES):
            for when in (NOW, LATER, PAST_WINDOW):
                for expires_at in (None, LATER):
                    expected = policy.identity_window(status, scopes, expires_at, when)
                    for role in ("alumni", "admin"):
                        assert policy.identity_state(status, scopes, expires_at, when, role) == expected


def test_window_open_is_true_only_while_available():
    assert policy.identity_window_open("accepted", ["identity"], LATER, NOW) is True
    assert policy.identity_window_open("accepted", ["identity"], LATER, PAST_WINDOW) is False
    assert policy.identity_window_open("accepted", ["identity"], None, NOW) is False
    assert policy.identity_window_open("accepted", [], LATER, NOW) is False
    assert policy.identity_window_open("shortlisted", ["identity"], LATER, NOW) is False
    for status in STATUSES:
        for scopes in ((), ("identity",), ALL_SCOPES):
            for when in (NOW, LATER, PAST_WINDOW):
                for expires_at in (None, LATER):
                    opened = policy.identity_window_open(status, scopes, expires_at, when)
                    assert opened is (policy.identity_window(status, scopes, expires_at, when) == "available")