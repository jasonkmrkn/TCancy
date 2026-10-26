"""Benchmarks: decrypting a user's own document, and synthetic encrypt/decrypt runs for admins.

Timings use time.perf_counter_ns. crypto_ms covers only the cipher calls, integrity_ms only the
HMAC work (from the integrity check, 0 when INTEGRITY_MODE is off), and total_ms everything,
disk reads included. Every sample is stored in crypto_benchmarks. The numbers depend on the
machine, its load and the data size.
"""
import os
import time
import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import crypto, documents, ratelimit, storage, vault
from app.analysis import CIPHERS, copies_of
from app.models import CryptoBenchmark, IntegrityTag, User

MiB = 1024 * 1024
HOUR = 3600
USER_LIMIT = 30  # document benchmarks per user per hour
ADMIN_LIMIT = 6  # synthetic runs per admin per hour
USER_MAX_BYTES = 256 * MiB  # file size x repeats x copies
ADMIN_MAX_BYTES = 64 * MiB  # sum(sizes) x repeats x ciphers

# The same cipher calls and chunking documents.put/stream use.
_ENCRYPT = documents._ENCRYPT
_DECRYPT = documents._DECRYPT


def _ms(ns: int) -> float:
    return ns / 1_000_000


def _mb_per_s(total_bytes: int, crypto_ms: float) -> float | None:
    """Throughput in MB/s (10^6 bytes); None when no measurable time was spent."""
    if not crypto_ms or crypto_ms <= 0:
        return None
    return round(total_bytes / 1e6 / (crypto_ms / 1000), 3)


def _stats(values: list[float]) -> dict:
    return {"avg": sum(values) / len(values), "min": min(values), "max": max(values)}


def _check_rate(bucket: str, user_id: uuid.UUID, limit: int) -> None:
    result = ratelimit.hit(bucket, str(user_id), limit, HOUR)
    if not result.allowed:
        raise HTTPException(
            status_code=429, detail="BENCHMARK_RATE_LIMITED",
            headers={"Retry-After": str(result.retry_after)},
        )


def _decrypt_run(db: Session, doc, copy) -> dict:
    """One repetition: verify the copy's tags (when enabled), then read and decrypt every chunk."""
    item = documents._item(doc.id)
    start = time.perf_counter_ns()
    integrity_ms = 0.0
    if vault.integrity_enabled():
        tags = list(db.scalars(
            select(IntegrityTag.tag).where(IntegrityTag.document_copy_id == copy.id).order_by(IntegrityTag.chunk_index)
        ))
        integrity_ms = vault.verify_file(
            documents._rechunk(storage.read(copy.storage_key)), tags, copy.algorithm, item,
            copy.salt, copy.nonce, "document %s copy %s (%s)" % (doc.id, copy.id, copy.algorithm),
        )
    crypto_ns = 0
    for index, chunk in enumerate(documents._rechunk(storage.read(copy.storage_key))):
        t = time.perf_counter_ns()
        _DECRYPT[copy.algorithm](chunk, copy.salt, copy.nonce, item, index)
        crypto_ns += time.perf_counter_ns() - t
    return {
        "crypto_ms": _ms(crypto_ns),
        "integrity_ms": integrity_ms,
        "total_ms": _ms(time.perf_counter_ns() - start),
    }


def run_document(db: Session, user: User, doc_id: str, repeats: int) -> dict:
    """Decrypt each stored copy of the user's document `repeats` times. Does not commit."""
    doc = documents.get_owned(db, user, doc_id)
    copies = copies_of(db, doc.id)
    if doc.size_bytes * repeats * len(copies) > USER_MAX_BYTES:
        raise HTTPException(status_code=422, detail="BENCHMARK_TOO_LARGE")
    _check_rate("benchmark", user.id, USER_LIMIT)
    results = []
    try:
        for copy in copies:
            runs = [_decrypt_run(db, doc, copy) for _ in range(repeats)]
            db.add_all(CryptoBenchmark(
                document_id=doc.id, algorithm=copy.algorithm, operation="decrypt",
                size_bytes=doc.size_bytes, source="user", **run,
            ) for run in runs)
            crypto = [r["crypto_ms"] for r in runs]
            results.append({
                "algorithm": copy.algorithm,
                **{k: CIPHERS[copy.algorithm][k] for k in ("name", "mode", "kind", "key_bits")},
                "runs": runs,
                "total_ms": _stats([r["total_ms"] for r in runs]),
                "crypto_ms": _stats(crypto),
                "crypto_mb_per_s": _mb_per_s(doc.size_bytes * repeats, sum(crypto)),
            })
    except storage.StorageError:
        raise HTTPException(status_code=500, detail="STORAGE_ERROR")
    db.flush()
    return {
        "document": {"id": str(doc.id), "type": doc.type, "ext": doc.ext, "size": doc.size_bytes},
        "repeats": repeats,
        "results": results,
    }


def run_synthetic(db: Session, user: User, sizes: list[int], repeats: int) -> dict:
    """Encrypt and decrypt random data with every cipher. Does not commit."""
    total_bytes = sum(sizes) * repeats * len(CIPHERS)
    if total_bytes > ADMIN_MAX_BYTES:
        raise HTTPException(status_code=422, detail="BENCHMARK_TOO_LARGE")
    _check_rate("admin_benchmark", user.id, ADMIN_LIMIT)
    # ponytail: two runs at the same moment can get the same run_no; use a sequence if that matters.
    run_no = (db.scalar(select(func.max(CryptoBenchmark.run_no)).where(CryptoBenchmark.source == "benchmark")) or 0) + 1
    item = "benchmark:%d" % run_no
    check = vault.integrity_enabled()
    samples = []
    for alg in CIPHERS:
        for size in sizes:
            for _ in range(repeats):
                data = os.urandom(size)
                salt, nonce = crypto.new_params(alg, item)
                start = time.perf_counter_ns()
                ciphertext = _ENCRYPT[alg](data, salt, nonce, item, 0)
                encrypt_ns = time.perf_counter_ns() - start
                samples.append((alg, "encrypt", size, _ms(encrypt_ns), 0.0, _ms(encrypt_ns)))

                tag = vault.tag_file_chunk(alg, item, salt, nonce, 0, True, ciphertext)  # not timed
                start = time.perf_counter_ns()
                integrity_ms = vault.verify_file([ciphertext], [tag], alg, item, salt, nonce, item) if check else 0.0
                t = time.perf_counter_ns()
                _DECRYPT[alg](ciphertext, salt, nonce, item, 0)
                end = time.perf_counter_ns()
                samples.append((alg, "decrypt", size, _ms(end - t), integrity_ms, _ms(end - start)))
    db.add_all(CryptoBenchmark(
        algorithm=alg, operation=op, size_bytes=size, crypto_ms=c, integrity_ms=i, total_ms=t,
        source="benchmark", run_no=run_no,
    ) for alg, op, size, c, i, t in samples)
    db.flush()
    return {"run_no": run_no, "samples": len(samples), "total_bytes": total_bytes}


def summary(db: Session, source: str | None) -> list[dict]:
    """Aggregates per (algorithm, operation, source), optionally for one source."""
    query = select(
        CryptoBenchmark.algorithm, CryptoBenchmark.operation, CryptoBenchmark.source,
        func.count(), func.avg(CryptoBenchmark.crypto_ms), func.avg(CryptoBenchmark.integrity_ms),
        func.avg(CryptoBenchmark.total_ms), func.min(CryptoBenchmark.total_ms), func.max(CryptoBenchmark.total_ms),
        func.sum(CryptoBenchmark.size_bytes), func.sum(CryptoBenchmark.crypto_ms),
    ).group_by(CryptoBenchmark.algorithm, CryptoBenchmark.operation, CryptoBenchmark.source)
    if source is not None:
        query = query.where(CryptoBenchmark.source == source)
    order = list(CIPHERS)
    rows = sorted(db.execute(query), key=lambda r: (r[2], order.index(r[0]) if r[0] in order else 99, r[1]))
    return [
        {
            "algorithm": alg, "operation": op, "source": src, "samples": n,
            "avg_crypto_ms": avg_c, "avg_integrity_ms": avg_i, "avg_total_ms": avg_t,
            "min_total_ms": min_t, "max_total_ms": max_t,
            "crypto_mb_per_s": _mb_per_s(int(size_sum), crypto_sum),
        }
        for alg, op, src, n, avg_c, avg_i, avg_t, min_t, max_t, size_sum, crypto_sum in rows
    ]
