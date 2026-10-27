"""Contract for app.vault: what store_field, load_field and load_fields promise."""
from app import vault


def test_store_then_load_returns_the_same_value(db, make_user):
    user = make_user()
    vault.store_field(db, user.id, "nik", "3578012345678901")
    db.commit()
    assert vault.load_field(db, user.id, "nik") == "3578012345678901"


def test_field_never_stored_is_none(db, make_user):
    user = make_user()
    assert vault.load_field(db, user.id, "never_stored") is None


def test_storing_twice_keeps_the_latest_value(db, make_user):
    user = make_user()
    vault.store_field(db, user.id, "phone", "+628111")
    db.commit()
    vault.store_field(db, user.id, "phone", "+628222")
    db.commit()
    assert vault.load_field(db, user.id, "phone") == "+628222"


def test_fields_and_users_are_independent(db, make_user):
    a, b = make_user(), make_user()
    vault.store_field(db, a.id, "nik", "111")
    vault.store_field(db, a.id, "phone", "222")
    vault.store_field(db, b.id, "nik", "333")
    db.commit()
    assert vault.load_field(db, a.id, "nik") == "111"
    assert vault.load_field(db, a.id, "phone") == "222"
    assert vault.load_field(db, b.id, "nik") == "333"
    assert vault.load_field(db, b.id, "phone") is None


def test_non_ascii_text_round_trips(db, make_user):
    user = make_user()
    value = "Jl. Keputih No. 5, Surabaya — café ñ 中文"
    vault.store_field(db, user.id, "address", value)
    db.commit()
    assert vault.load_field(db, user.id, "address") == value


def test_load_fields_is_keyed_by_the_given_user_ids(db, make_user):
    a, b = make_user(), make_user()
    vault.store_field(db, a.id, "nik", "111")
    vault.store_field(db, b.id, "nik", "222")
    db.commit()
    assert vault.load_fields(db, [a.id, b.id], "nik") == {a.id: "111", b.id: "222"}


def test_load_fields_leaves_out_users_without_a_value(db, make_user):
    a, b = make_user(), make_user()
    vault.store_field(db, a.id, "nik", "111")
    db.commit()
    assert vault.load_fields(db, [a.id, b.id], "nik") == {a.id: "111"}


def test_load_fields_with_no_users_is_empty(db):
    assert vault.load_fields(db, [], "nik") == {}