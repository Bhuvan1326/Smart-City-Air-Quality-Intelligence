import base64

import pytest
from app.core.sanitization import UnsafeInputError
from app.services.evidence_storage import EvidenceStorage


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.evidence_storage.settings.MEDIA_ROOT", str(tmp_path)
    )
    monkeypatch.setattr(
        "app.services.evidence_storage.settings.MAX_EVIDENCE_PHOTO_MB", 1.0
    )
    return EvidenceStorage()


def _tiny_jpeg_data_url() -> str:
    payload = base64.b64encode(b"\xff\xd8\xff\xe0fake-jpeg-bytes").decode()
    return f"data:image/jpeg;base64,{payload}"


def test_save_photo_writes_file_and_returns_url(storage, tmp_path):
    url = storage.save_photo("action-1", _tiny_jpeg_data_url())
    assert url.startswith("/media/evidence/action-1/")
    assert url.endswith(".jpg")

    saved_files = list((tmp_path / "evidence" / "action-1").glob("*.jpg"))
    assert len(saved_files) == 1


def test_rejects_malformed_base64(storage):
    with pytest.raises(UnsafeInputError):
        storage.save_photo("action-2", "data:image/jpeg;base64,not-valid-base64!!!")


def test_rejects_unsupported_prefix(storage):
    with pytest.raises(UnsafeInputError):
        storage.save_photo("action-3", "data:application/pdf;base64,AAAA")


def test_rejects_oversized_photo(storage):
    # 2MB of data, but limit is set to 1MB in the fixture.
    big_payload = base64.b64encode(b"0" * (2 * 1024 * 1024)).decode()
    data_url = f"data:image/png;base64,{big_payload}"
    with pytest.raises(UnsafeInputError):
        storage.save_photo("action-4", data_url)


def test_each_photo_gets_a_unique_filename(storage):
    url1 = storage.save_photo("action-5", _tiny_jpeg_data_url())
    url2 = storage.save_photo("action-5", _tiny_jpeg_data_url())
    assert url1 != url2


def test_read_photo_round_trips_saved_photo(storage):
    data_url = _tiny_jpeg_data_url()
    url = storage.save_photo("action-6", data_url)

    result = storage.read_photo(url)

    assert result is not None
    raw_bytes, media_type = result
    assert media_type == "image/jpeg"
    assert raw_bytes == base64.b64decode(data_url.split(",", 1)[1])


def test_read_photo_returns_none_for_missing_file(storage):
    assert storage.read_photo("/media/evidence/nonexistent/y.jpg") is None


def test_read_photo_returns_none_for_wrong_prefix(storage):
    assert storage.read_photo("/some/other/path.jpg") is None


def test_read_photo_rejects_path_traversal(storage):
    assert storage.read_photo("/media/evidence/../../etc/passwd") is None
