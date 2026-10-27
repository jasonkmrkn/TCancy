"""Contract for app.documents: what put, list_for_owner, get_meta, stream, delete and
purge_user_files promise."""
import io
import uuid

import pytest
from fastapi import HTTPException

from app import documents
from app.models import Application, Job

ID_FORMS = pytest.mark.parametrize("as_text", [True, False], ids=["str", "uuid"])


def _put(db, user, content, name="cv.pdf", doc_type="cv"):
    return documents.put(db, user.id, doc_type, name, io.BytesIO(content))


def _id(meta, as_text=True):
    return meta["id"] if as_text else uuid.UUID(str(meta["id"]))


def _bytes_of(db, document_id):
    return b"".join(documents.stream(db, document_id))


def test_put_returns_the_document_summary(db, make_user, pdf_content):
    meta = _put(db, make_user(), pdf_content)
    assert {"id", "type", "ext", "size", "created_at"} <= set(meta)
    uuid.UUID(str(meta["id"]))
    assert meta["type"] == "cv"
    assert meta["ext"] == "pdf"
    assert meta["size"] == len(pdf_content)
    assert meta["created_at"] is not None


def test_list_for_owner_includes_the_document(db, make_user, pdf_content):
    user = make_user()
    meta = _put(db, user, pdf_content)
    listed = documents.list_for_owner(db, user.id)
    assert [d["id"] for d in listed] == [meta["id"]]
    assert {"id", "type", "ext", "size", "created_at"} <= set(listed[0])


def test_list_for_owner_only_lists_that_owners_documents(db, make_user, pdf_content):
    owner, other = make_user(), make_user()
    _put(db, owner, pdf_content)
    assert documents.list_for_owner(db, other.id) == []


@ID_FORMS
def test_get_meta_describes_the_document(db, make_user, pdf_content, as_text):
    user = make_user()
    meta = _put(db, user, pdf_content)
    doc = documents.get_meta(db, _id(meta, as_text))
    assert doc.id == uuid.UUID(str(meta["id"]))
    assert doc.owner_id == user.id
    assert doc.type == "cv"
    assert doc.ext == "pdf"
    assert doc.size_bytes == len(pdf_content)


def test_get_meta_of_an_unknown_document_is_none(db):
    assert documents.get_meta(db, uuid.uuid4()) is None
    assert documents.get_meta(db, "not-a-uuid") is None


@ID_FORMS
def test_stream_returns_the_stored_bytes(db, make_user, pdf_content, as_text):
    meta = _put(db, make_user(), pdf_content)
    assert _bytes_of(db, _id(meta, as_text)) == pdf_content


def test_stream_of_an_unknown_document_is_404(db):
    with pytest.raises(HTTPException) as exc:
        _bytes_of(db, uuid.uuid4())
    assert exc.value.status_code == 404
    assert exc.value.detail == "DOCUMENT_NOT_FOUND"


@ID_FORMS
def test_delete_removes_the_document_and_its_data(db, make_user, pdf_content, files_on_disk, as_text):
    user = make_user()
    meta = _put(db, user, pdf_content)
    assert files_on_disk()
    documents.delete(db, user.id, _id(meta, as_text))
    assert documents.get_meta(db, meta["id"]) is None
    assert documents.list_for_owner(db, user.id) == []
    assert files_on_disk() == set()


def test_delete_of_an_unknown_document_is_404(db, make_user):
    with pytest.raises(HTTPException) as exc:
        documents.delete(db, make_user().id, uuid.uuid4())
    assert exc.value.status_code == 404
    assert exc.value.detail == "DOCUMENT_NOT_FOUND"


def test_delete_cannot_remove_another_owners_document(db, make_user, pdf_content):
    owner, intruder = make_user(), make_user()
    meta = _put(db, owner, pdf_content)
    with pytest.raises(HTTPException) as exc:
        documents.delete(db, intruder.id, meta["id"])
    assert exc.value.status_code == 404
    assert exc.value.detail == "DOCUMENT_NOT_FOUND"
    assert documents.get_meta(db, meta["id"]) is not None


def test_delete_refuses_a_document_used_by_an_active_application(db, make_user, pdf_content):
    applicant = make_user()
    employer = make_user(role="alumni")
    meta = _put(db, applicant, pdf_content)
    job = Job(
        owner_id=employer.id, title="Backend Intern", company="Acme",
        type="internship", work_mode="remote", description="Build things",
    )
    db.add(job)
    db.commit()
    db.add(Application(job_id=job.id, applicant_id=applicant.id, cv_document_id=uuid.UUID(meta["id"])))
    db.commit()
    with pytest.raises(HTTPException) as exc:
        documents.delete(db, applicant.id, meta["id"])
    assert exc.value.status_code == 409
    assert exc.value.detail == "DOCUMENT_IN_USE"
    assert documents.get_meta(db, meta["id"]) is not None


def test_purge_user_files_removes_every_file_of_that_user(db, make_user, pdf_content, files_on_disk):
    user = make_user()
    _put(db, user, pdf_content)
    _put(db, user, pdf_content)
    assert files_on_disk()
    documents.purge_user_files(db, user.id)
    db.commit()
    assert files_on_disk() == set()


def test_purge_user_files_leaves_other_users_alone(db, make_user, pdf_content):
    user, other = make_user(), make_user()
    _put(db, user, pdf_content)
    kept = _put(db, other, pdf_content)
    documents.purge_user_files(db, user.id)
    db.commit()
    assert _bytes_of(db, kept["id"]) == pdf_content