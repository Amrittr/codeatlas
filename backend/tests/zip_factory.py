"""Helpers that build ZIP archives in memory, including deliberately hostile ones."""

from __future__ import annotations

import io
import stat
import zipfile
from dataclasses import dataclass


@dataclass
class Entry:
    name: str
    data: bytes = b""
    mode: int | None = None  # full st_mode, e.g. stat.S_IFLNK | 0o777
    utf8_flag: bool = True
    compress: int = zipfile.ZIP_DEFLATED
    encrypted_flag: bool = False


def build_zip(entries: list[Entry | str | tuple[str, bytes | str]]) -> bytes:
    """Build a ZIP. ``"dir/"`` creates a directory entry; ``(name, data)`` a file."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for raw in entries:
            entry = _coerce(raw)
            info = zipfile.ZipInfo("placeholder", date_time=(2024, 5, 17, 12, 30, 0))
            # Assign the name afterwards so ZipInfo cannot normalise hostile names.
            info.filename = entry.name
            info.orig_filename = entry.name
            info.compress_type = entry.compress
            if entry.mode is not None:
                info.external_attr = entry.mode << 16
                info.create_system = 3
            elif entry.name.endswith("/"):
                info.external_attr = (stat.S_IFDIR | 0o755) << 16 | 0x10
            else:
                info.external_attr = (stat.S_IFREG | 0o644) << 16
            if entry.utf8_flag:
                info.flag_bits |= 0x800
            archive.writestr(info, entry.data)
            if entry.encrypted_flag:
                info.flag_bits |= 0x1
    data = buffer.getvalue()
    return data


def build_raw_name_zip(name_bytes: bytes, data: bytes = b"x") -> bytes:
    """A ZIP whose single entry name is stored as raw bytes without the UTF-8 flag."""
    placeholder = b"P" * len(name_bytes)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(zipfile.ZipInfo(placeholder.decode("ascii"), date_time=(2024, 1, 1, 0, 0, 0)), data)
    return buffer.getvalue().replace(placeholder, name_bytes)


def _coerce(raw: Entry | str | tuple[str, bytes | str]) -> Entry:
    if isinstance(raw, Entry):
        return raw
    if isinstance(raw, str):
        return Entry(raw)
    name, data = raw
    return Entry(name, data.encode() if isinstance(data, str) else data)


SAMPLE_PROJECT: list[Entry | str | tuple[str, bytes | str]] = [
    "sample-app/",
    ("sample-app/README.md", "# Sample app\n"),
    ("sample-app/LICENSE", "MIT\n"),
    ("sample-app/package.json", '{"name": "sample-app"}\n'),
    ("sample-app/.gitignore", "node_modules/\n.env\n"),
    ("sample-app/.env.example", "API_URL=http://localhost\n"),
    ("sample-app/Dockerfile", "FROM python:3.12-slim\n"),
    ("sample-app/Makefile", "test:\n\tpytest\n"),
    ("sample-app/src/index.js", "import { App } from './App.js';\n"),
    ("sample-app/src/App.js", "export const App = () => null;\n"),
    ("sample-app/src/utils/format.ts", "export const fmt = (n: number) => `${n}`;\n"),
    ("sample-app/src/styles/main.css", "body { margin: 0 }\n"),
    ("sample-app/src/components/Button.jsx", "export default function Button() {}\n"),
    ("sample-app/src/components/index.js", "export * from './Button.jsx';\n"),
    ("sample-app/server/main.py", "print('hello')\n"),
    ("sample-app/server/api/routes.py", "ROUTES = []\n"),
    ("sample-app/server/api/__init__.py", ""),
    ("sample-app/tests/test_routes.py", "def test_ok():\n    assert True\n"),
    ("sample-app/tests/App.test.js", "test('ok', () => {});\n"),
    ("sample-app/docs/guide.md", "# Guide\n"),
    ("sample-app/docs/über-café.md", "# Unicode\n"),
    ("sample-app/assets/logo.svg", "<svg/>"),
    ("sample-app/data/seed.csv", "id,name\n1,a\n"),
    "sample-app/empty-folder/",
    ("sample-app/node_modules/left-pad/index.js", "module.exports = 1;\n"),
    ("sample-app/node_modules/left-pad/package.json", "{}\n"),
    ("sample-app/.git/HEAD", "ref: refs/heads/main\n"),
]
