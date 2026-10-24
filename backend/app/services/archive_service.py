"""Secure ZIP import.

Treats every archive as hostile. Before anything is decompressed it:
- reads the end-of-central-directory record itself and counts central-directory headers
  against ``max_archive_entries``, so a huge directory is rejected before ``zipfile`` loads it;
- normalises every entry name and rejects absolute paths and ``..`` traversal (ZIP slip);
- skips symlinks, device files, encrypted entries, case-insensitive collisions and duplicates;
- reads ``.gitignore`` files (size-bounded) and applies the exclusion policy, so excluded paths
  are never extracted and do not count toward limits;
- enforces the file, directory and depth limits.

It then extracts the planned files one chunk at a time. The per-file size, the total
uncompressed size, the whole-archive compression ratio and the time budget are all enforced
on bytes actually produced, never on sizes the archive declares. Files are created with
``O_EXCL | O_NOFOLLOW`` inside a caller-owned temporary directory. Nothing is executed.
"""

from __future__ import annotations

import calendar
import os
import stat
import struct
import unicodedata
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from app.analyzers.exclusions import MAX_GITIGNORE_BYTES, MAX_GITIGNORE_FILES, ExclusionPolicy
from app.core.config import Settings
from app.core.errors import AppError
from app.services.analysis_context import AnalysisContext

CHUNK_SIZE = 64 * 1024
ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06")

_EOCD = struct.Struct("<4sHHHHIIH")
_EOCD_SIG = b"PK\x05\x06"
_ZIP64_LOCATOR = struct.Struct("<4sIQI")
_ZIP64_LOCATOR_SIG = b"PK\x06\x07"
_ZIP64_EOCD = struct.Struct("<4sQHHIIQQQQ")
_ZIP64_EOCD_SIG = b"PK\x06\x06"
_CENTRAL_HEADER = struct.Struct("<4s24sHHH12s")  # signature, fixed fields, name/extra/comment lengths, rest
_CENTRAL_HEADER_SIG = b"PK\x01\x02"
_MAX_COMMENT = 0xFFFF

FATAL_ENTRY_REASONS = {"absolute_path", "path_traversal"}
_MAX_NAME_BYTES = 255


class UnsafeEntry(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _SkipEntry(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class ExcludedEntry:
    kind: str  # "directory" or "file"
    reason: str
    rule: str
    entry_count: int = 0


@dataclass
class ExtractionReport:
    archive_size: int
    entry_count: int
    extracted_file_count: int = 0
    extracted_bytes: int = 0
    skipped: list[tuple[str, str]] = field(default_factory=list)
    excluded: dict[str, ExcludedEntry] = field(default_factory=dict)
    gitignore_problems: list[tuple[str, str]] = field(default_factory=list)


def _invalid(message: str = "The file is not a valid ZIP archive or is corrupted.") -> AppError:
    return AppError("invalid_archive", message, 400)


def read_central_directory_bounds(fp: BinaryIO, archive_size: int) -> tuple[int, int, int]:
    """Return ``(declared_entry_count, cd_size, cd_offset)`` from the (ZIP64) end records."""
    tail_len = min(archive_size, _EOCD.size + _MAX_COMMENT)
    tail_start = archive_size - tail_len
    fp.seek(tail_start)
    tail = fp.read(tail_len)

    candidate = -1
    pos = tail.rfind(_EOCD_SIG)
    while pos >= 0:
        if pos + _EOCD.size <= len(tail):
            comment_len = _EOCD.unpack_from(tail, pos)[7]
            if pos + _EOCD.size + comment_len == len(tail):
                candidate = pos
                break
            if candidate < 0:
                candidate = pos
        pos = tail.rfind(_EOCD_SIG, 0, pos)
    if candidate < 0:
        raise _invalid()

    _, _, _, _, entries, cd_size, cd_offset, _ = _EOCD.unpack_from(tail, candidate)
    if entries == 0xFFFF or cd_size == 0xFFFFFFFF or cd_offset == 0xFFFFFFFF:
        locator_at = tail_start + candidate - _ZIP64_LOCATOR.size
        if locator_at < 0:
            raise _invalid()
        fp.seek(locator_at)
        locator = fp.read(_ZIP64_LOCATOR.size)
        if len(locator) != _ZIP64_LOCATOR.size or locator[:4] != _ZIP64_LOCATOR_SIG:
            raise _invalid()
        zip64_offset = _ZIP64_LOCATOR.unpack(locator)[2]
        if zip64_offset + _ZIP64_EOCD.size > archive_size:
            raise _invalid()
        fp.seek(zip64_offset)
        record = fp.read(_ZIP64_EOCD.size)
        if len(record) != _ZIP64_EOCD.size or record[:4] != _ZIP64_EOCD_SIG:
            raise _invalid()
        _, _, _, _, _, _, _, entries, cd_size, cd_offset = _ZIP64_EOCD.unpack(record)

    if cd_offset + cd_size > archive_size:
        raise _invalid()
    return entries, cd_size, cd_offset


def count_central_directory_entries(fp: BinaryIO, cd_offset: int, cd_size: int, limit: int) -> int:
    """Walk the central directory headers without materialising them, stopping past ``limit``.

    The declared entry count in the end record can lie; walking the headers cannot.
    """
    fp.seek(cd_offset)
    consumed = 0
    count = 0
    while consumed < cd_size:
        header = fp.read(_CENTRAL_HEADER.size)
        if len(header) != _CENTRAL_HEADER.size or header[:4] != _CENTRAL_HEADER_SIG:
            raise _invalid()
        _, _, name_len, extra_len, comment_len, _ = _CENTRAL_HEADER.unpack(header)
        variable = name_len + extra_len + comment_len
        fp.seek(variable, os.SEEK_CUR)
        consumed += _CENTRAL_HEADER.size + variable
        count += 1
        if count > limit:
            raise AppError(
                "too_many_entries",
                f"The archive has more than {limit:,} entries, which exceeds the server limit.",
                413,
            )
    return count


def decode_entry_name(info: zipfile.ZipInfo) -> str:
    """Recover UTF-8 names stored without the UTF-8 flag (common in macOS and Linux zips)."""
    name = info.filename
    if not info.flag_bits & 0x800:
        try:
            name = name.encode("cp437").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return name


def normalize_entry_name(name: str, max_path_length: int) -> tuple[tuple[str, ...], bool]:
    """Split an archive entry name into safe path components. Returns ``(parts, is_directory)``."""
    if "\x00" in name:
        raise UnsafeEntry("unsafe_name")
    name = name.replace("\\", "/")
    is_directory = name.endswith("/")
    if name.startswith("/") or (len(name) >= 2 and name[1] == ":" and name[0].isalpha()):
        raise UnsafeEntry("absolute_path")

    parts: list[str] = []
    for part in name.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise UnsafeEntry("path_traversal")
        if any(ord(char) < 0x20 or ord(char) == 0x7F for char in part):
            raise UnsafeEntry("unsafe_name")
        part = unicodedata.normalize("NFC", part)
        if len(part.encode("utf-8")) > _MAX_NAME_BYTES:
            raise UnsafeEntry("name_too_long")
        parts.append(part)

    if len("/".join(parts)) > max_path_length:
        raise UnsafeEntry("path_too_long")
    return tuple(parts), is_directory


def display_name(name: str) -> str:
    cleaned = "".join("�" if ord(char) < 0x20 or ord(char) == 0x7F else char for char in name)
    return cleaned if len(cleaned) <= 300 else cleaned[:299] + "…"


class _PathRegistry:
    """Tracks planned paths case-insensitively, so extraction never merges or overwrites entries.

    Behaviour is the same on case-sensitive Linux and case-insensitive macOS filesystems.
    """

    def __init__(self) -> None:
        self._kinds: dict[str, tuple[str, str]] = {}
        self.directories: list[str] = []

    def add_directory(self, parts: tuple[str, ...]) -> str | None:
        for depth in range(1, len(parts) + 1):
            path = "/".join(parts[:depth])
            existing = self._kinds.get(path.casefold())
            if existing is None:
                self._kinds[path.casefold()] = ("dir", path)
                self.directories.append(path)
            elif existing[0] == "file":
                return "path_conflict"
            elif existing[1] != path:
                return "case_collision"
        return None

    def add_file(self, parts: tuple[str, ...]) -> str | None:
        conflict = self.add_directory(parts[:-1])
        if conflict:
            return conflict
        path = "/".join(parts)
        existing = self._kinds.get(path.casefold())
        if existing is not None:
            if existing[0] == "dir":
                return "path_conflict"
            return "duplicate_entry" if existing[1] == path else "case_collision"
        self._kinds[path.casefold()] = ("file", path)
        return None


def _entry_kind(info: zipfile.ZipInfo, is_directory: bool) -> str:
    file_type = stat.S_IFMT(info.external_attr >> 16)
    if is_directory or file_type == stat.S_IFDIR:
        return "directory"
    if file_type == stat.S_IFLNK:
        return "symlink"
    if file_type not in (0, stat.S_IFREG):
        return "special"
    return "file"


def inspect_archive(fp: BinaryIO, settings: Settings) -> tuple[int, int]:
    """Cheap structural checks that need no decompression. Returns ``(archive_size, entry_count)``.

    Safe to run synchronously in the upload request so bad uploads fail immediately.
    """
    archive_size = fp.seek(0, os.SEEK_END)
    if archive_size == 0:
        raise _invalid("The uploaded file is empty.")
    if archive_size > settings.max_upload_bytes:
        raise AppError("upload_too_large", "The upload exceeds the maximum archive size.", 413)
    fp.seek(0)
    if fp.read(4) not in ZIP_MAGIC:
        raise AppError("unsupported_file_type", "The uploaded file is not a ZIP archive.", 415)
    _, cd_size, cd_offset = read_central_directory_bounds(fp, archive_size)
    entry_count = count_central_directory_entries(fp, cd_offset, cd_size, settings.max_archive_entries)
    fp.seek(0)
    return archive_size, entry_count


def extract_archive(
    fp: BinaryIO,
    destination: Path,
    settings: Settings,
    policy: ExclusionPolicy,
    context: AnalysisContext,
) -> ExtractionReport:
    """Validate ``fp`` as a ZIP archive and extract the safe, non-excluded files into ``destination``.

    ``destination`` must not exist yet; it is created with mode 0700. The caller owns cleanup.
    ``.gitignore`` files are read from the archive into ``policy`` before planning.
    """
    context.set_phase("inspecting")
    archive_size, entry_count = inspect_archive(fp, settings)

    try:
        archive = zipfile.ZipFile(fp)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, ValueError, EOFError, OSError, struct.error):
        raise _invalid() from None

    report = ExtractionReport(archive_size=archive_size, entry_count=entry_count)
    with archive:
        infos = archive.infolist()
        if policy.respect_gitignore:
            _load_gitignores(archive, infos, settings, policy, report, context)
        context.set_phase("planning", total=len(infos))
        planned = _plan_entries(infos, settings, policy, report, context)

        context.set_phase("extracting", total=len(planned.files))
        destination.mkdir(mode=0o700)
        root_real = os.path.realpath(destination)
        verified_parents: set[tuple[str, ...]] = set()
        for directory in planned.registry.directories:
            destination.joinpath(*directory.split("/")).mkdir(mode=0o700, parents=True, exist_ok=True)
        for info, parts in planned.files:
            context.checkpoint()
            target = destination.joinpath(*parts)
            # Defence in depth: names were validated already and no symlinks are ever created,
            # but confirm the real parent directory is inside the root (once per directory).
            if parts[:-1] not in verified_parents:
                if os.path.commonpath([root_real, os.path.realpath(target.parent)]) != root_real:
                    raise AppError("unsafe_archive", "The archive tried to write outside its extraction folder.", 400)
                verified_parents.add(parts[:-1])
            try:
                written = _extract_file(archive, info, target, settings, report, context)
            except _SkipEntry as skip:
                report.skipped.append(("/".join(parts), skip.reason))
                context.advance()
                continue
            context.advance()
            report.extracted_file_count += 1
            report.extracted_bytes += written
            if (
                report.extracted_bytes > settings.compression_ratio_floor_bytes
                and report.extracted_bytes / archive_size > settings.max_compression_ratio
            ):
                raise AppError(
                    "suspected_decompression_bomb",
                    "The archive expands far more than real source code does and was rejected.",
                    413,
                )
    return report


def _load_gitignores(
    archive: zipfile.ZipFile,
    infos: list[zipfile.ZipInfo],
    settings: Settings,
    policy: ExclusionPolicy,
    report: ExtractionReport,
    context: AnalysisContext,
) -> None:
    """Read every ``.gitignore`` in the archive (bounded in size and number) into the policy.

    These are the only file contents CodeAtlas reads, because they decide what to extract.
    """
    loaded = 0
    for position, info in enumerate(infos):
        if position % 1000 == 0:
            context.checkpoint()
        if not info.filename.endswith(".gitignore"):
            continue
        try:
            parts, is_directory = normalize_entry_name(decode_entry_name(info), settings.max_path_length)
        except UnsafeEntry:
            continue  # reported (or rejected) during planning
        if not parts or parts[-1] != ".gitignore" or _entry_kind(info, is_directory) != "file" or info.flag_bits & 0x1:
            continue
        path = "/".join(parts)
        if loaded >= MAX_GITIGNORE_FILES:
            report.gitignore_problems.append((path, f"more than {MAX_GITIGNORE_FILES} .gitignore files; the rest were not applied"))
            break
        try:
            with archive.open(info) as handle:
                data = handle.read(MAX_GITIGNORE_BYTES + 1)
        except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, struct.error):
            report.gitignore_problems.append((path, "could not be read"))
            continue
        if len(data) > MAX_GITIGNORE_BYTES:
            report.gitignore_problems.append((path, f"larger than {MAX_GITIGNORE_BYTES // 1024} KB and was not applied"))
            continue
        if policy.add_gitignore(parts[:-1], data.decode("utf-8", errors="replace")):
            loaded += 1


@dataclass
class _Plan:
    registry: _PathRegistry
    files: list[tuple[zipfile.ZipInfo, tuple[str, ...]]]


def _plan_entries(
    infos: list[zipfile.ZipInfo],
    settings: Settings,
    policy: ExclusionPolicy,
    report: ExtractionReport,
    context: AnalysisContext,
) -> _Plan:
    registry = _PathRegistry()
    files: list[tuple[zipfile.ZipInfo, tuple[str, ...]]] = []
    declared_total = 0

    for position, info in enumerate(infos):
        if position % 1000 == 0:
            context.checkpoint()
        context.advance()
        raw_name = decode_entry_name(info)
        try:
            parts, is_directory = normalize_entry_name(raw_name, settings.max_path_length)
        except UnsafeEntry as unsafe:
            if unsafe.reason in FATAL_ENTRY_REASONS:
                raise AppError(
                    "unsafe_archive",
                    "The archive contains an entry that points outside the project folder "
                    f"({unsafe.reason.replace('_', ' ')}). It was rejected without extracting anything.",
                    400,
                ) from None
            report.skipped.append((display_name(raw_name), unsafe.reason))
            continue
        if not parts:
            continue
        if len(parts) > settings.max_depth:
            raise AppError(
                "archive_too_deep",
                f"The archive nests folders deeper than {settings.max_depth} levels.",
                413,
            )

        kind = _entry_kind(info, is_directory)
        excluded = policy.first_excluded(parts, kind == "directory")
        if excluded is not None:
            index, match = excluded
            excluded_parts = parts[: index + 1]
            excluded_is_directory = index < len(parts) - 1 or kind == "directory"
            record = report.excluded.setdefault(
                "/".join(excluded_parts),
                ExcludedEntry("directory" if excluded_is_directory else "file", match.reason, match.rule),
            )
            if not (kind == "directory" and index == len(parts) - 1):
                record.entry_count += 1
            # Create the excluded folder (or the excluded file's parent) so it appears in the tree.
            registry.add_directory(excluded_parts if excluded_is_directory else parts[:-1])
            continue

        if kind == "directory":
            conflict = registry.add_directory(parts)
            if conflict:
                report.skipped.append(("/".join(parts), conflict))
            continue
        if kind == "symlink":
            report.skipped.append(("/".join(parts), "symlink_not_followed"))
            continue
        if kind == "special":
            report.skipped.append(("/".join(parts), "special_file"))
            continue
        if info.flag_bits & 0x1:
            report.skipped.append(("/".join(parts), "encrypted"))
            continue

        conflict = registry.add_file(parts)
        if conflict:
            report.skipped.append(("/".join(parts), conflict))
            continue
        files.append((info, parts))
        declared_total += info.file_size

    if len(files) > settings.max_files:
        raise AppError(
            "too_many_files",
            f"The archive contains {len(files):,} files to analyze; the limit is {settings.max_files:,}. "
            "Exclude folders you do not need (custom rules or .gitignore) and try again.",
            413,
        )
    if len(registry.directories) > settings.max_directories:
        raise AppError(
            "too_many_directories",
            f"The archive contains {len(registry.directories):,} folders; the limit is {settings.max_directories:,}.",
            413,
        )
    if declared_total > settings.max_uncompressed_bytes:
        raise AppError(
            "archive_uncompressed_too_large",
            "The archive would extract to more data than the server allows.",
            413,
        )
    return _Plan(registry=registry, files=files)


def _extract_file(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    target: Path,
    settings: Settings,
    report: ExtractionReport,
    context: AnalysisContext,
) -> int:
    remaining_total = settings.max_uncompressed_bytes - report.extracted_bytes
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(target, flags, 0o600)
    except FileExistsError:
        raise _SkipEntry("path_conflict") from None

    written = 0
    try:
        with archive.open(info) as source, os.fdopen(fd, "wb") as sink:
            while chunk := source.read(CHUNK_SIZE):
                written += len(chunk)
                if written > remaining_total:
                    raise AppError(
                        "archive_uncompressed_too_large",
                        "The archive would extract to more data than the server allows.",
                        413,
                    )
                if written > settings.max_file_bytes:
                    raise _SkipEntry("file_too_large")
                sink.write(chunk)
                context.checkpoint()
    except _SkipEntry:
        target.unlink(missing_ok=True)
        raise
    except NotImplementedError:
        target.unlink(missing_ok=True)
        raise _SkipEntry("unsupported_compression") from None
    except (zipfile.BadZipFile, zlib.error, EOFError, struct.error):
        target.unlink(missing_ok=True)
        raise _SkipEntry("corrupt_entry") from None

    try:
        timestamp = calendar.timegm((*info.date_time, 0, 0, 0))
        os.utime(target, (timestamp, timestamp))
    except (ValueError, OverflowError, OSError):
        pass
    return written
