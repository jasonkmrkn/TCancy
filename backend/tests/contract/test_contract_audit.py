"""Contract for app.audit.record: accepts the documented arguments and returns None."""
import uuid

from app import audit


def test_record_with_minimal_arguments_returns_none(db):
    assert audit.record(db, actor_id=None, actor_role=None, action="contract.minimal") is None
    db.commit()


def test_record_with_every_argument_returns_none(db, make_user):
    user = make_user()
    result = audit.record(
        db,
        actor_id=user.id,
        actor_role="applicant",
        action="contract.full",
        target_type="document",
        target_id=uuid.uuid4(),
        ip="203.0.113.7",
        user_agent="pytest",
        details={"reason": "contract", "count": 2},
    )
    assert result is None
    db.commit()