from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import csv
import json
from urllib.parse import urlparse

from . import __version__


class ArtifactHandler(BaseHTTPRequestHandler):
    artifact_dir: Path

    def _send(self, status: int, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json_file(self, *names: str):
        for name in names:
            path = self.artifact_dir / name
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        return None

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/":
            self._send(200, {"service": "evidence-alpha", "version": __version__, "read_only": True, "endpoints": ["/health", "/api/v1/runs/latest", "/api/v1/runs/latest/signals", "/api/v1/runs/latest/orders", "/api/v1/runs/latest/fills", "/api/v1/runs/latest/event-study"]})
            return
        if path == "/health":
            self._send(200, {"status": "ok", "version": __version__, "artifact_ready": self._json_file("report.json") is not None})
            return
        mapping = {
            "/api/v1/runs/latest": ("report.json",),
            "/api/v1/runs/latest/signals": ("signals.json",),
            "/api/v1/runs/latest/orders": ("orders.json", "paper_orders.json"),
            "/api/v1/runs/latest/fills": ("fills.json",),
        }
        if path in mapping:
            payload = self._json_file(*mapping[path])
            self._send(200 if payload is not None else 404, payload or {"error": "artifact_not_found"})
            return
        if path == "/api/v1/runs/latest/event-study":
            source = self.artifact_dir / "event_study.csv"
            if not source.exists():
                self._send(404, {"error": "artifact_not_found"})
                return
            with source.open("r", encoding="utf-8", newline="") as handle:
                self._send(200, list(csv.DictReader(handle)))
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        self._send(405, {"error": "read_only_service"})

    def log_message(self, format: str, *args: object) -> None:
        print(f"api {self.address_string()} {format % args}")


def serve(artifact_dir: str | Path, host: str = "127.0.0.1", port: int = 8080) -> None:
    handler = type("ConfiguredArtifactHandler", (ArtifactHandler,), {"artifact_dir": Path(artifact_dir)})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Evidence-to-Alpha API listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

