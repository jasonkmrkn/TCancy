import dataclasses

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