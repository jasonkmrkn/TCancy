"""Contract for app.storage: what write, read and delete promise."""
from app import storage


def _chunks():
    # More than one 64 KiB piece, so chunked reading is exercised.
    return [b"hello ", b"world", b"x" * 200_000, b"!"]


def test_write_returns_a_string_key():
    key = storage.write(iter(_chunks()))
    assert isinstance(key, str) and key


def test_read_returns_exactly_what_was_written():
    key = storage.write(iter(_chunks()))
    assert b"".join(storage.read(key)) == b"".join(_chunks())


def test_read_yields_bytes():
    key = storage.write(iter(_chunks()))
    pieces = list(storage.read(key))
    assert pieces and all(isinstance(piece, bytes) for piece in pieces)


def test_write_accepts_a_generator():
    key = storage.write(chunk for chunk in _chunks())
    assert b"".join(storage.read(key)) == b"".join(_chunks())


def test_each_write_gets_its_own_key():
    first = storage.write(iter([b"one"]))
    second = storage.write(iter([b"two"]))
    assert first != second
    assert b"".join(storage.read(first)) == b"one"
    assert b"".join(storage.read(second)) == b"two"


def test_delete_removes_the_data(files_on_disk):
    key = storage.write(iter(_chunks()))
    assert files_on_disk()
    storage.delete(key)
    assert files_on_disk() == set()


def test_delete_leaves_other_keys_alone():
    first = storage.write(iter([b"keep"]))
    second = storage.write(iter([b"drop"]))
    storage.delete(second)
    assert b"".join(storage.read(first)) == b"keep"


def test_deleting_an_unknown_key_does_not_raise():
    assert storage.delete("does-not-exist") is None