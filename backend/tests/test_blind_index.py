import pytest

from app import blind_index, config

OTHER_KEY = "cd" * 32


def test_index_is_32_bytes():
    result = blind_index.compute("email", "a@example.com")
    assert isinstance(result, bytes)
    assert len(result) == 32


def test_deterministic():
    assert blind_index.compute("email", "a@example.com") == blind_index.compute("email", "a@example.com")
    assert blind_index.compute("nik", "3201234567890001") == blind_index.compute("nik", "3201234567890001")


def test_email_is_normalized():
    expected = blind_index.compute("email", "a@example.com")
    assert blind_index.compute("email", "A@Example.COM") == expected
    assert blind_index.compute("email", "  a@example.com  ") == expected


def test_nik_is_not_normalized():
    assert blind_index.compute("nik", "3201234567890001") != blind_index.compute("nik", " 3201234567890001 ")


def test_different_kind_gives_different_index():
    assert blind_index.compute("email", "same-text") != blind_index.compute("nik", "same-text")


def test_unknown_kind_raises_value_error():
    with pytest.raises(ValueError):
        blind_index.compute("phone", "08123456789")


def test_different_key_gives_different_index(monkeypatch):
    before = blind_index.compute("email", "a@example.com")
    monkeypatch.setattr(config, "BLIND_INDEX_KEY", OTHER_KEY)
    after = blind_index.compute("email", "a@example.com")
    assert before != after


def test_empty_or_invalid_key_raises_runtime_error(monkeypatch):
    for bad_key in ("", "zz" * 32, "ab" * 16, "ab" * 33):
        monkeypatch.setattr(config, "BLIND_INDEX_KEY", bad_key)
        with pytest.raises(RuntimeError):
            blind_index.compute("email", "a@example.com")