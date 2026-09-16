from __future__ import annotations

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent


def _run_local(*args: str) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(PROJECT_DIR / "tg_userbot.py"), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(PROJECT_DIR),
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "tg_userbot failed")
    payload = json.loads(proc.stdout or "{}")
    if not isinstance(payload, dict):
        raise RuntimeError("tg_userbot returned non-object payload")
    return payload


class Handler(BaseHTTPRequestHandler):
    server_version = "tg-userbot-sidecar/1.0"

    def _send_json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send_json(200, {"ok": True, "service": "tg-userbot-sidecar"})
            return
        self._send_json(404, {"ok": False, "error": "not-found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/run":
            self._send_json(404, {"ok": False, "error": "not-found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            payload = json.loads((self.rfile.read(length) or b"{}").decode("utf-8"))
            args = payload.get("args") or []
            if not isinstance(args, list) or not all(isinstance(x, str) for x in args):
                raise ValueError("args must be a list[str]")
            result = _run_local(*args)
            self._send_json(200, result)
        except Exception as exc:
            self._send_json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def main() -> None:
    port = int(os.getenv("TELEGRAM_USERBOT_PORT", "8091"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(json.dumps({"ok": True, "service": "tg-userbot-sidecar", "port": port}, ensure_ascii=False), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
