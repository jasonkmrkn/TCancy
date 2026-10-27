import os

import pytest
from sqlalchemy import text

from app import audit, benchmarks, config, crypto, filetype, ratelimit
from app.db import engine
from test_document import as_applicant, content_for, upload
from test_job import as_user
from test_vault import empty_database

API = "/api/v1"
ADMIN = API + "/admin/benchmarks"
MiB = 1024 * 1024


@pytest.fixture(autouse=True)
def modes(monkeypatch):
    monkeypatch.setattr(config, "ENCRYPTION_POLICY", "assignment")
    monkeypatch.setattr(config, "INTEGRITY_MODE", "off")


def ciphertext(client, doc_id, n=None):
    query = "" if n is None else "?bytes=%s" % n
    return client.get("%s/me/documents/%s/ciphertext%s" % (API, doc_id, query))


def bench(client, doc_id, body=None):
    return client.post("%s/me/documents/%s/benchmark" % (API, doc_id), json=body)


def a_pdf(client, body=b"x" * 5000):
    return upload(client, "cv", "a.pdf", content_for("a.pdf", body)).json()["id"]


def count(sql="SELECT count(*) FROM crypto_benchmarks", **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def admin(client, name="root"):
    as_user(client, name, "admin")


# --- ciphertext view -----------------------------------------------------------


def test_ciphertext_view_shape(client):
    as_applicant(client)
    content = content_for("a.pdf", b"hello world " * 500)
    doc_id = upload(client, "cv", "a.pdf", content).json()["id"]
    r = ciphertext(client, doc_id)
    assert r.status_code == 200
    body = r.json()
    assert body["document"] == {"id": doc_id, "type": "cv", "ext": "pdf", "size": len(content)}
    assert body["preview_bytes"] == 48
    assert bytes.fromhex(body["plaintext_preview_hex"]) == content[:48]
    assert 0 < body["plaintext_entropy_bits_per_byte"] < 8
    copies = {c["algorithm"]: c for c in body["copies"]}
    assert [c["algorithm"] for c in body["copies"]] == ["aes", "des", "rc4"]
    keys = {"algorithm", "name", "mode", "kind", "key_bits", "block_bits", "plaintext_size", "ciphertext_size",
            "nonce_hex", "preview_hex", "bytes_changed", "entropy_bits_per_byte"}
    for c in copies.values():
        assert set(c) == keys
        assert c["plaintext_size"] == c["ciphertext_size"] == len(content)
        assert len(bytes.fromhex(c["preview_hex"])) == 48
        assert c["preview_hex"] != body["plaintext_preview_hex"]
        assert 0 < c["bytes_changed"] <= 48
        assert c["entropy_bits_per_byte"] > body["plaintext_entropy_bits_per_byte"]
    assert copies["aes"]["kind"] == copies["des"]["kind"] == "block cipher"
    assert copies["aes"]["mode"] == "CTR" and copies["aes"]["key_bits"] == 256 and copies["aes"]["block_bits"] == 128
    assert len(bytes.fromhex(copies["aes"]["nonce_hex"])) == 8
    assert len(bytes.fromhex(copies["des"]["nonce_hex"])) == 4
    rc4 = copies["rc4"]
    assert rc4["kind"] == "stream cipher" and rc4["mode"] == "none (stream cipher)"
    assert rc4["block_bits"] is None and rc4["nonce_hex"] is None


def test_ciphertext_view_never_shows_key_or_salt(client):
    as_applicant(client)
    doc_id = a_pdf(client)
    raw = ciphertext(client, doc_id, 128).text.lower()
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT algorithm, salt FROM document_copies WHERE document_id = :d"),
                            {"d": doc_id}).all()
    for alg, salt in rows:
        salt = bytes(salt)
        key = crypto.derive_key(salt, "%s:file:%s" % (alg, doc_id), crypto.KEY_BYTES[alg])
        for secret in (salt.hex(), key.hex()):
            assert secret not in raw


@pytest.mark.parametrize("n, status", [(7, 422), (8, 200), (128, 200), (129, 422)])
def test_preview_bytes_bounds(client, n, status):
    as_applicant(client)
    doc_id = a_pdf(client)
    r = ciphertext(client, doc_id, n)
    assert r.status_code == status
    if status == 200:
        assert r.json()["preview_bytes"] == n
        assert all(len(bytes.fromhex(c["preview_hex"])) == n for c in r.json()["copies"])


# --- access and policy -----------------------------------------------------------


def test_other_users_document_is_404(client):
    as_applicant(client, "budi")
    doc_id = a_pdf(client)
    client.post(API + "/auth/logout")
    as_applicant(client, "siti")
    for r in (ciphertext(client, doc_id), bench(client, doc_id)):
        assert r.status_code == 404 and r.json()["detail"] == "DOCUMENT_NOT_FOUND"


def test_production_shows_and_benchmarks_only_aes(client, monkeypatch):
    monkeypatch.setattr(config, "ENCRYPTION_POLICY", "production")
    as_applicant(client)
    doc_id = a_pdf(client)
    assert [c["algorithm"] for c in ciphertext(client, doc_id).json()["copies"]] == ["aes"]
    r = bench(client, doc_id, {"repeats": 2})
    assert [x["algorithm"] for x in r.json()["results"]] == ["aes"]
    assert count() == 2


# --- user benchmark --------------------------------------------------------------


def test_benchmark_records_and_orders_results(client):
    as_applicant(client)
    doc_id = a_pdf(client, os.urandom(2 * MiB))
    r = bench(client, doc_id, {"repeats": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["repeats"] == 3 and body["document"]["id"] == doc_id
    assert [x["algorithm"] for x in body["results"]] == ["aes", "des", "rc4"]
    assert count() == 9
    assert count("SELECT count(*) FROM crypto_benchmarks WHERE operation = 'decrypt' AND source = 'user' "
                 "AND document_id = :d", d=doc_id) == 9
    for res in body["results"]:
        assert len(res["runs"]) == 3
        assert res["kind"] == ("stream cipher" if res["algorithm"] == "rc4" else "block cipher")
        for key in ("total_ms", "crypto_ms"):
            s = res[key]
            assert s["min"] <= s["avg"] <= s["max"]
        for run in res["runs"]:
            assert run["crypto_ms"] <= run["total_ms"] and run["integrity_ms"] == 0
        assert res["crypto_mb_per_s"] is None or res["crypto_mb_per_s"] > 0
    assert bench(client, doc_id).json()["repeats"] == 5  # default


@pytest.mark.parametrize("repeats", [0, 11, 1.5, "a", "5", True])
def test_bad_repeats_422(client, repeats):
    as_applicant(client)
    doc_id = a_pdf(client)
    assert bench(client, doc_id, {"repeats": repeats}).status_code == 422
    assert count() == 0


def test_one_byte_file_does_not_break_throughput(client, monkeypatch):
    monkeypatch.setattr(filetype, "detect", lambda head, doc_type: "pdf")
    as_applicant(client)
    doc_id = upload(client, "cv", "a.pdf", b"x").json()["id"]
    r = bench(client, doc_id, {"repeats": 1})
    assert r.status_code == 200
    for res in r.json()["results"]:
        assert res["crypto_mb_per_s"] is None or isinstance(res["crypto_mb_per_s"], float)
    assert benchmarks._mb_per_s(1, 0) is None and benchmarks._mb_per_s(1, 0.0) is None
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO crypto_benchmarks (algorithm, operation, size_bytes, crypto_ms, total_ms, source) "
            "VALUES ('aes', 'decrypt', 1, 0, 0, 'benchmark')"))
    client.post(API + "/auth/logout")
    admin(client)
    rows = client.get(ADMIN + "?source=benchmark").json()
    assert rows[0]["crypto_mb_per_s"] is None


# --- limits ----------------------------------------------------------------------


def test_too_large_for_user_and_admin(client, monkeypatch):
    monkeypatch.setattr(benchmarks, "USER_MAX_BYTES", 1000)
    monkeypatch.setattr(benchmarks, "ADMIN_MAX_BYTES", 1000)
    as_applicant(client)
    doc_id = a_pdf(client)
    r = bench(client, doc_id, {"repeats": 1})
    assert r.status_code == 422 and r.json()["detail"] == "BENCHMARK_TOO_LARGE"
    client.post(API + "/auth/logout")
    admin(client)
    r = client.post(ADMIN + "/run", json={"sizes": [1000], "repeats": 1})
    assert r.status_code == 422 and r.json()["detail"] == "BENCHMARK_TOO_LARGE"
    assert count() == 0


def test_real_admin_limit_counts_three_ciphers(client):
    admin(client)
    # 6 x 4 MiB x 1 x 3 = 72 MiB > 64 MiB
    r = client.post(ADMIN + "/run", json={"sizes": [4 * MiB] * 6, "repeats": 1})
    assert r.status_code == 422 and r.json()["detail"] == "BENCHMARK_TOO_LARGE"


def test_rate_limited_429(client, monkeypatch):
    real_hit = ratelimit.hit

    def refuse_benchmarks(bucket, *args):
        if "benchmark" in bucket:
            return ratelimit.RateResult(False, 60)
        return real_hit(bucket, *args)  # registration and login keep working

    monkeypatch.setattr(ratelimit, "hit", refuse_benchmarks)
    as_applicant(client)
    doc_id = a_pdf(client)
    r = bench(client, doc_id, {"repeats": 1})
    assert r.status_code == 429 and r.json()["detail"] == "BENCHMARK_RATE_LIMITED"
    assert r.headers["retry-after"] == "60"
    client.post(API + "/auth/logout")
    admin(client)
    r = client.post(ADMIN + "/run", json={"sizes": [16], "repeats": 1})
    assert r.status_code == 429 and r.json()["detail"] == "BENCHMARK_RATE_LIMITED"
    assert count() == 0


def test_user_rate_limit_is_30_per_hour(client):
    as_applicant(client)
    doc_id = a_pdf(client, b"x" * 10)
    for _ in range(30):
        assert bench(client, doc_id, {"repeats": 1}).status_code == 200
    assert bench(client, doc_id, {"repeats": 1}).status_code == 429


# --- admin -----------------------------------------------------------------------


def test_admin_run_numbers_samples_and_summary(client):
    as_applicant(client)
    doc_id = a_pdf(client)
    bench(client, doc_id, {"repeats": 1})
    client.post(API + "/auth/logout")
    admin(client)
    first = client.post(ADMIN + "/run", json={"sizes": [16, 1024], "repeats": 2}).json()
    assert first == {"run_no": 1, "samples": 3 * 2 * 2 * 2}
    second = client.post(ADMIN + "/run").json()  # defaults: 3 sizes, 3 repeats
    assert second == {"run_no": 2, "samples": 3 * 2 * 3 * 3}
    assert count("SELECT count(*) FROM crypto_benchmarks WHERE source = 'benchmark'") == 24 + 54

    rows = client.get(ADMIN + "?source=benchmark").json()
    assert {(r["algorithm"], r["operation"]) for r in rows} == {
        (a, o) for a in ("aes", "des", "rc4") for o in ("encrypt", "decrypt")}
    assert all(r["source"] == "benchmark" and r["samples"] == (24 + 54) // 6 for r in rows)
    keys = {"algorithm", "operation", "source", "samples", "avg_crypto_ms", "avg_integrity_ms", "avg_total_ms",
            "min_total_ms", "max_total_ms", "crypto_mb_per_s"}
    for r in rows:
        assert set(r) == keys and r["min_total_ms"] <= r["avg_total_ms"] <= r["max_total_ms"]
    users = client.get(ADMIN + "?source=user").json()
    assert [(r["algorithm"], r["operation"], r["samples"]) for r in users] == [
        ("aes", "decrypt", 1), ("des", "decrypt", 1), ("rc4", "decrypt", 1)]
    assert len(client.get(ADMIN).json()) == 9
    assert client.get(ADMIN + "?source=other").status_code == 422


@pytest.mark.parametrize("body", [
    {"sizes": []}, {"sizes": [1] * 7}, {"sizes": [0]}, {"sizes": [4 * MiB + 1]},
    {"repeats": 0}, {"repeats": 11}, {"sizes": [1.5]}, {"extra": 1},
])
def test_admin_run_validation(client, body):
    admin(client)
    assert client.post(ADMIN + "/run", json=body).status_code == 422


def test_admin_endpoints_refuse_applicants_and_alumni(client):
    as_applicant(client)
    assert client.post(ADMIN + "/run").status_code == 403
    assert client.get(ADMIN).status_code == 403
    client.post(API + "/auth/logout")
    as_user(client, "alumna", "alumni")
    assert client.post(ADMIN + "/run").status_code == 403
    assert client.get(ADMIN).status_code == 403


# --- audit and integrity -----------------------------------------------------------


def test_audit_details_are_numbers_only(client, monkeypatch):
    calls = []
    monkeypatch.setattr(audit, "record", lambda db, **kw: calls.append(kw))
    as_applicant(client)
    doc_id = a_pdf(client)
    ciphertext(client, doc_id)
    bench(client, doc_id, {"repeats": 1})
    client.post(API + "/auth/logout")
    admin(client)
    client.post(ADMIN + "/run", json={"sizes": [16], "repeats": 1})
    wanted = ("document.ciphertext_view", "document.benchmark", "admin.benchmark_run")
    by_action = {c["action"]: c["details"] for c in calls if c["action"] in wanted}
    assert set(wanted) <= set(by_action)
    for action in ("document.ciphertext_view", "document.benchmark", "admin.benchmark_run"):
        details = by_action[action]
        assert details and all(isinstance(v, int) and not isinstance(v, bool) for v in details.values())


@pytest.mark.parametrize("mode", ["off", "log-only", "enforce"])
def test_integrity_ms_follows_mode(client, monkeypatch, mode):
    monkeypatch.setattr(config, "INTEGRITY_MODE", mode)
    as_applicant(client)
    doc_id = a_pdf(client, os.urandom(MiB))
    runs = [run for res in bench(client, doc_id, {"repeats": 2}).json()["results"] for run in res["runs"]]
    client.post(API + "/auth/logout")
    admin(client)
    client.post(ADMIN + "/run", json={"sizes": [4096], "repeats": 1})
    with engine.connect() as conn:
        synthetic = [r for (r,) in conn.execute(text(
            "SELECT integrity_ms FROM crypto_benchmarks WHERE source = 'benchmark' AND operation = 'decrypt'"))]
    if mode == "off":
        assert all(r["integrity_ms"] == 0 for r in runs) and all(v == 0 for v in synthetic)
    else:
        assert all(r["integrity_ms"] >= 0 for r in runs) and any(r["integrity_ms"] > 0 for r in runs)
        assert all(v >= 0 for v in synthetic)


# --- migration ---------------------------------------------------------------------


def test_axel_benchmark_migration_upgrade_downgrade_upgrade_on_an_empty_database():
    with empty_database() as (alembic, scalar):
        def has_table():
            return scalar("SELECT to_regclass('crypto_benchmarks')") is not None

        alembic("upgrade", "axel@head")
        assert has_table()
        alembic("downgrade", "axel_03_integrity")
        assert not has_table()
        alembic("upgrade", "axel@head")
        assert has_table()
