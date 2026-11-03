"""Parser worker process, plus the client that runs untrusted files through it.

Native parsers can misbehave on hostile input: tree-sitter's error recovery takes quadratic
time on some inputs (minutes for a 512 KB file of quote characters) and offers no safe way to
interrupt it. Running them in a child process makes that harmless. A slow file is killed at
its per-file time limit, and a crash loses the worker rather than the server.

Protocol: one JSON object per line. The parent sends ``{"path", "extension"}``; the worker reads
the file itself and answers with the extracted facts. Source code never crosses the pipe.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from app.analyzers.parsers import ImportRecord, ParseResult, parse_imports

BACKEND_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WORKER_COMMAND = (sys.executable, "-m", "app.analyzers.parsers.worker")
_POLL_SECONDS = 0.05
_EOF = object()


def _clean(text: str) -> str:
    """Parsed strings can hold lone surrogates ("\\ud800"), which cannot be encoded as UTF-8 later."""
    return text.encode("utf-8", "replace").decode("utf-8")


def _from_message(message: dict) -> ParseResult:
    return ParseResult(
        imports=[
            ImportRecord(_clean(item["specifier"]), item["line"], item["kind"], item["level"], tuple(_clean(n) for n in item["names"]))
            for item in message["imports"]
        ],
        routes=[(_clean(url), line) for url, line in message["routes"]],
        url_refs=[(_clean(url), line) for url, line in message["url_refs"]],
        browser_api=message["browser_api"],
        dynamic_unknown=message["dynamic_unknown"],
        error=message["error"],
        partial=message["partial"],
    )


class IsolatedParser:
    """Parses files in a child process, restarting it after a timeout or crash. One per thread."""

    def __init__(
        self,
        *,
        per_file_seconds: float,
        should_stop: Callable[[], bool] = lambda: False,
        worker_command: tuple[str, ...] = DEFAULT_WORKER_COMMAND,
    ) -> None:
        self._per_file_seconds = per_file_seconds
        self._should_stop = should_stop
        self._command = worker_command
        self._process: subprocess.Popen | None = None
        self._replies: queue.Queue = queue.Queue()

    def __enter__(self) -> IsolatedParser:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        process.kill()
        process.wait()
        for stream in (process.stdin, process.stdout):
            try:
                stream.close()
            except OSError:
                pass

    def _start(self) -> None:
        self._process = subprocess.Popen(
            list(self._command),
            cwd=BACKEND_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self._replies = queue.Queue()
        threading.Thread(target=self._read_replies, args=(self._process.stdout, self._replies), daemon=True).start()

    @staticmethod
    def _read_replies(stream, replies: queue.Queue) -> None:
        try:
            for line in stream:
                replies.put(line)
        except (OSError, ValueError):
            pass
        replies.put(_EOF)

    def parse(self, path: Path, extension: str) -> ParseResult:
        if self._process is None:
            self._start()
        request = json.dumps({"path": os.fspath(path), "extension": extension}).encode() + b"\n"
        try:
            self._process.stdin.write(request)
            self._process.stdin.flush()
        except OSError:
            self.close()
            return ParseResult(error="parser_crashed")

        deadline = time.monotonic() + self._per_file_seconds
        while True:
            try:
                reply = self._replies.get(timeout=_POLL_SECONDS)
            except queue.Empty:
                if self._should_stop():
                    self.close()
                    return ParseResult(error="parse_cancelled")
                if time.monotonic() > deadline:
                    self.close()
                    return ParseResult(error="parse_timeout")
                continue
            if reply is _EOF:
                self.close()
                return ParseResult(error="parser_crashed")
            return _from_message(json.loads(reply))


def _handle(request: dict) -> ParseResult:
    try:
        data = Path(request["path"]).read_bytes()
    except OSError:
        return ParseResult(error="unreadable")
    return parse_imports(data, request["extension"], lambda: False)


def main() -> None:
    for line in sys.stdin.buffer:
        print(json.dumps(asdict(_handle(json.loads(line)))), flush=True)


if __name__ == "__main__":
    main()
