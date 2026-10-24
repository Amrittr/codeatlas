"""Hostile and malformed archives: every case must fail safely and leave no files behind."""

from __future__ import annotations

import io
import os
import stat
import struct
import warnings
import zipfile

import pytest

from app.analyzers.exclusions import ExclusionPolicy
from app.core.errors import AppError
from app.services.analysis_context import AnalysisContext
from app.services.archive_service import (
    count_central_directory_entries,
    extract_archive,
    normalize_entry_name,
    read_central_directory_bounds,
    UnsafeEntry,
)
from tests.zip_factory import Entry, build_raw_name_zip, build_zip


def assert_no_leftovers(temp_root):
    assert list(temp_root.iterdir()) == [], "temporary extraction directory was not cleaned up"


def error_code(response) -> str:
    return response.json()["error"]["code"]


@pytest.mark.parametrize(
    "name",
    [
        "../evil.txt",
        "project/../../evil.txt",
        "..\\..\\evil.txt",
        "/etc/passwd",
        "C:/Windows/evil.txt",
        "C:\\evil.txt",
    ],
)
def test_path_traversal_and_absolute_paths_reject_whole_archive(upload, temp_root, tmp_path, name):
    data = build_zip([("project/ok.txt", "fine"), (name, "pwned")])
    response = upload(data)
    assert response.status_code == 400
    assert error_code(response) == "unsafe_archive"
    assert not (tmp_path / "evil.txt").exists()
    assert_no_leftovers(temp_root)


def test_symlink_entries_are_skipped_not_created(upload, temp_root):
    data = build_zip([
        ("project/real.txt", "real"),
        Entry("project/link-to-passwd", b"/etc/passwd", mode=stat.S_IFLNK | 0o777),
    ])
    response = upload(data)
    assert response.status_code == 201
    body = response.json()
    assert body["stats"]["totalFiles"] == 1
    assert {"path": "project/link-to-passwd", "reason": "symlink_not_followed"} in body["skipped"]
    assert any(w["code"] == "entries_skipped" for w in body["warnings"])
    assert_no_leftovers(temp_root)


def test_special_files_are_skipped(upload):
    data = build_zip([("p/a.txt", "a"), Entry("p/fifo", b"", mode=stat.S_IFIFO | 0o644)])
    body = upload(data).json()
    assert {"path": "p/fifo", "reason": "special_file"} in body["skipped"]


def test_random_bytes_are_not_a_zip(upload, temp_root):
    response = upload(os.urandom(2048), name="notes.zip")
    assert response.status_code == 415
    assert error_code(response) == "unsupported_file_type"
    assert_no_leftovers(temp_root)


def test_zip_signature_with_garbage_is_invalid(upload, temp_root):
    response = upload(b"PK\x03\x04" + os.urandom(4096))
    assert response.status_code == 400
    assert error_code(response) == "invalid_archive"
    assert_no_leftovers(temp_root)


def test_truncated_archive_is_invalid(upload, temp_root):
    data = build_zip([("p/a.py", "x" * 500), ("p/b.py", "y" * 500)])
    response = upload(data[: len(data) - 30])
    assert response.status_code == 400
    assert error_code(response) == "invalid_archive"
    assert_no_leftovers(temp_root)


def test_empty_upload_is_rejected(upload):
    response = upload(b"")
    assert response.status_code == 400
    assert error_code(response) == "invalid_archive"


def test_upload_over_limit_is_rejected_by_service(make_client, upload, temp_root):
    client = make_client(max_upload_bytes=1000)
    data = build_zip([Entry("p/blob.bin", os.urandom(4000), compress=zipfile.ZIP_STORED)])
    response = upload(data, test_client=client)
    assert response.status_code == 413
    assert error_code(response) == "upload_too_large"
    assert_no_leftovers(temp_root)


def test_upload_over_limit_is_rejected_before_parsing(make_client, upload):
    client = make_client(max_upload_bytes=10)
    data = build_zip([Entry("p/blob.bin", os.urandom(1_200_000), compress=zipfile.ZIP_STORED)])
    response = upload(data, test_client=client)
    assert response.status_code == 413
    assert error_code(response) == "upload_too_large"


def test_chunked_upload_over_limit_is_rejected(make_client):
    client = make_client(max_upload_bytes=10)
    payload = build_zip([Entry("p/blob.bin", os.urandom(1_200_000), compress=zipfile.ZIP_STORED)])
    boundary = "codeatlasboundary"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"p.zip\"\r\n"
        "Content-Type: application/zip\r\n\r\n"
    ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()

    def chunks():
        for start in range(0, len(body), 64 * 1024):
            yield body[start : start + 64 * 1024]

    response = client.post(
        "/api/projects/analyze",
        content=chunks(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert response.status_code == 413
    assert error_code(response) == "upload_too_large"


def test_file_count_limit(make_client, upload, temp_root):
    client = make_client(max_files=3)
    data = build_zip([(f"p/f{i}.txt", "x") for i in range(5)])
    response = upload(data, test_client=client)
    assert response.status_code == 413
    assert error_code(response) == "too_many_files"
    assert_no_leftovers(temp_root)


def test_excluded_entries_do_not_count_toward_file_limit(make_client, upload):
    client = make_client(max_files=3)
    data = build_zip([("p/a.js", "a"), *[(f"p/node_modules/m/f{i}.js", "x") for i in range(10)]])
    response = upload(data, test_client=client)
    assert response.status_code == 201
    assert response.json()["exclusions"][0]["entryCount"] == 10


def test_archive_entry_limit_counts_excluded_entries(make_client, upload):
    client = make_client(max_archive_entries=5)
    data = build_zip([(f"p/node_modules/f{i}.js", "x") for i in range(10)])
    response = upload(data, test_client=client)
    assert response.status_code == 413
    assert error_code(response) == "too_many_entries"


def test_directory_limit(make_client, upload):
    client = make_client(max_directories=3)
    data = build_zip([f"p/d{i}/" for i in range(5)])
    response = upload(data, test_client=client)
    assert response.status_code == 413
    assert error_code(response) == "too_many_directories"


def test_depth_limit(make_client, upload, temp_root):
    client = make_client(max_depth=3)
    response = upload(build_zip([("a/b/c/d/e.txt", "deep")]), test_client=client)
    assert response.status_code == 413
    assert error_code(response) == "archive_too_deep"
    assert_no_leftovers(temp_root)


def test_oversized_single_file_is_skipped(make_client, upload):
    client = make_client(max_file_bytes=1000)
    data = build_zip([("p/small.txt", "ok"), ("p/huge.log", b"\0" * 50_000)])
    response = upload(data, test_client=client)
    assert response.status_code == 201
    body = response.json()
    assert body["stats"]["totalFiles"] == 1
    assert {"path": "p/huge.log", "reason": "file_too_large"} in body["skipped"]


def test_total_uncompressed_limit(make_client, upload, temp_root):
    client = make_client(max_uncompressed_bytes=10_000)
    data = build_zip([("p/a.bin", b"\0" * 8000), ("p/b.bin", b"\0" * 8000)])
    response = upload(data, test_client=client)
    assert response.status_code == 413
    assert error_code(response) == "archive_uncompressed_too_large"
    assert_no_leftovers(temp_root)


def test_compression_ratio_bomb_is_rejected(make_client, upload, temp_root):
    client = make_client(compression_ratio_floor_bytes=1000, max_compression_ratio=5)
    data = build_zip([("p/zeros.bin", b"\0" * 200_000)])
    response = upload(data, test_client=client)
    assert response.status_code == 413
    assert error_code(response) == "suspected_decompression_bomb"
    assert_no_leftovers(temp_root)


def test_lying_size_header_cannot_bypass_limits(make_settings, tmp_path):
    """Declare a tiny uncompressed size for a large entry; extraction must not exceed it."""
    data = bytearray(build_zip([("p/zeros.bin", b"\0" * 100_000)]))
    real_size = struct.pack("<I", 100_000)
    fake_size = struct.pack("<I", 10)
    data = bytes(data).replace(real_size, fake_size)
    report = extract_archive(io.BytesIO(data), tmp_path / "out", make_settings(), ExclusionPolicy(), AnalysisContext.started(30))
    assert report.extracted_bytes <= 10
    assert ("p/zeros.bin", "corrupt_entry") in report.skipped


def test_encrypted_entries_are_skipped(upload):
    data = build_zip([("p/a.txt", "a"), Entry("p/secret.txt", b"xxxx", encrypted_flag=True)])
    body = upload(data).json()
    assert {"path": "p/secret.txt", "reason": "encrypted"} in body["skipped"]


def test_duplicate_entries_are_reported(upload):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        data = build_zip([("p/a.txt", "first"), ("p/a.txt", "second")])
    body = upload(data).json()
    assert body["stats"]["totalFiles"] == 1
    assert {"path": "p/a.txt", "reason": "duplicate_entry"} in body["skipped"]


def test_case_collisions_are_reported_consistently(upload):
    data = build_zip([("p/src/App.js", "a"), ("p/src/app.js", "b"), ("p/Src/other.js", "c")])
    body = upload(data).json()
    assert body["stats"]["totalFiles"] == 1
    reasons = {item["path"]: item["reason"] for item in body["skipped"]}
    assert reasons == {"p/src/app.js": "case_collision", "p/Src/other.js": "case_collision"}


def test_file_and_directory_with_same_path(upload):
    data = build_zip([("p/thing", "file"), ("p/thing/inner.txt", "x")])
    body = upload(data).json()
    assert {"path": "p/thing/inner.txt", "reason": "path_conflict"} in body["skipped"]


def test_control_characters_in_names_are_skipped(upload):
    data = build_zip([("p/ok.txt", "x"), ("p/bad\x01name.txt", "x")])
    body = upload(data).json()
    assert body["stats"]["totalFiles"] == 1
    assert body["skipped"][0]["reason"] == "unsafe_name"
    assert "\x01" not in body["skipped"][0]["path"]


def test_utf8_names_without_flag_are_recovered(upload):
    body = upload(build_raw_name_zip("docs/résumé.md".encode())).json()
    tree = body["stats"]["largestFiles"]
    assert tree[0]["path"] == "docs/résumé.md"


def test_unicode_names_are_nfc_normalized(upload):
    body = upload(build_zip([("p/cafe\u0301.md", "x")])).json()
    assert body["stats"]["largestFiles"][0]["path"] == "p/caf\u00e9.md"


def test_failed_analysis_cleans_up(make_client, upload, temp_root):
    client = make_client(max_files=1)
    upload(build_zip([("a.txt", "a"), ("b.txt", "b")]), test_client=client)
    assert_no_leftovers(temp_root)


def test_successful_analysis_cleans_up(upload, temp_root):
    assert upload(build_zip([("a/b.txt", "secret source")])).status_code == 201
    assert_no_leftovers(temp_root)


def test_deadline_is_enforced(make_settings, tmp_path):
    data = build_zip([("p/a.txt", "a")])
    context = AnalysisContext.started(30)
    context.expire_now()
    with pytest.raises(AppError) as raised:
        extract_archive(io.BytesIO(data), tmp_path / "out", make_settings(), ExclusionPolicy(), context)
    assert raised.value.code == "analysis_timeout"
    assert raised.value.status_code == 408


def test_extracted_files_are_private(make_settings, tmp_path):
    data = build_zip([Entry("p/run.sh", b"#!/bin/sh\n", mode=stat.S_IFREG | 0o777)])
    extract_archive(io.BytesIO(data), tmp_path / "out", make_settings(), ExclusionPolicy(), AnalysisContext.started(30))
    mode = (tmp_path / "out" / "p" / "run.sh").stat().st_mode
    assert not mode & (stat.S_IXUSR | stat.S_IRWXG | stat.S_IRWXO)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("a/b/c.txt", (("a", "b", "c.txt"), False)),
        ("./a//b/", (("a", "b"), True)),
        ("a\\b\\c.py", (("a", "b", "c.py"), False)),
    ],
)
def test_normalize_entry_name(name, expected):
    assert normalize_entry_name(name, 1024) == expected


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("../x", "path_traversal"),
        ("/x", "absolute_path"),
        ("D:x", "absolute_path"),
        ("a/\x07b", "unsafe_name"),
        ("a/" + "x" * 256, "name_too_long"),
    ],
)
def test_normalize_entry_name_rejections(name, reason):
    with pytest.raises(UnsafeEntry) as raised:
        normalize_entry_name(name, 1024)
    assert raised.value.reason == reason


def test_central_directory_reader_handles_comments():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("a.txt", "a")
        archive.writestr("b.txt", "b")
        archive.comment = b"PK\x05\x06 fake signature inside the comment"
    data = buffer.getvalue()
    fp = io.BytesIO(data)
    _, cd_size, cd_offset = read_central_directory_bounds(fp, len(data))
    assert count_central_directory_entries(fp, cd_offset, cd_size, 10) == 2


def test_central_directory_reader_handles_zip64():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for index in range(65_536):  # one past the classic 16-bit entry count forces ZIP64 records
            archive.writestr(f"{index}", b"")
    data = buffer.getvalue()
    fp = io.BytesIO(data)
    declared, cd_size, cd_offset = read_central_directory_bounds(fp, len(data))
    assert declared == 65_536
    with pytest.raises(AppError) as raised:
        count_central_directory_entries(fp, cd_offset, cd_size, 1000)
    assert raised.value.code == "too_many_entries"
