"""Small local HTTP server. Uploaded XER bytes are checked in this process."""

from __future__ import annotations

from email.parser import BytesParser
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from xercheck.check import check_named, parse_threshold
from xercheck.html_report import render_form, render_html, render_message
from xercheck.limits import MAX_FILE_BYTES, MAX_FILES, MAX_TOTAL_BYTES

_MAX_BODY = MAX_TOTAL_BYTES + 200_000


def safe_filename(name: str) -> str:
    base = name.replace("\\", "/").split("/")[-1].replace("\x00", "").strip()
    if not base or base in {".", ".."}:
        return "upload.xer"
    return base


def parse_multipart(content_type: str, body: bytes) -> list[tuple[str, str, bytes]]:
    if "boundary=" not in content_type.lower():
        raise ValueError("The form must be multipart data.")
    header = (
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n"
    ).encode("utf-8", errors="replace")
    message = BytesParser(policy=HTTP).parsebytes(header + body)
    if not message.is_multipart():
        raise ValueError("The form must be multipart data.")
    parts: list[tuple[str, str, bytes]] = []
    for part in message.iter_parts():
        field_name = part.get_param("name", header="content-disposition") or ""
        filename = part.get_filename() or ""
        payload = part.get_payload(decode=True)
        if payload is None:
            raw = part.get_payload()
            payload = raw.encode("utf-8") if isinstance(raw, str) else b""
        parts.append((field_name, filename, payload))
    return parts


def evaluate_upload(
    files: list[tuple[str, bytes]], threshold_text: str
) -> tuple[int, str]:
    """Return an HTTP status and an HTML page for one upload."""
    if not files:
        return 400, render_message("Choose a file", "Choose at least one XER file.")
    if len(files) > MAX_FILES:
        return 400, render_message(
            "Too many files",
            f"At most {MAX_FILES} files can be checked at once.",
        )
    total = 0
    items: list[tuple[str, bytes]] = []
    for name, data in files:
        if len(data) > MAX_FILE_BYTES:
            return 413, render_message(
                "File is too large",
                f"{safe_filename(name)} is {len(data)} bytes, above the {MAX_FILE_BYTES} byte cap.",
            )
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            return 413, render_message(
                "Upload is too large",
                f"The files together exceed the {MAX_TOTAL_BYTES} byte cap.",
            )
        items.append((safe_filename(name), data))
    try:
        threshold = parse_threshold(threshold_text)
    except ValueError as exc:
        return 400, render_message("Threshold was not accepted", str(exc))
    report = check_named(items, threshold)
    return 200, render_html(report, show_home_link=True)


class CheckerHandler(BaseHTTPRequestHandler):
    server_version = "xercheck"

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path not in {"/", ""}:
            self._send(404, render_message("Not found", "That page is not part of this checker."))
            return
        self._send(200, render_form())

    def do_POST(self) -> None:  # noqa: N802
        length_text = self.headers.get("Content-Length", "")
        try:
            length = int(length_text)
        except ValueError:
            self._send(400, render_message("Request was not accepted", "Content-Length is missing."))
            return
        if length < 0 or length > _MAX_BODY:
            self._send(
                413,
                render_message(
                    "Upload is too large",
                    f"The request body exceeds the {_MAX_BODY} byte cap.",
                ),
            )
            return
        body = self.rfile.read(length)
        try:
            parts = parse_multipart(self.headers.get("Content-Type", ""), body)
        except ValueError as exc:
            self._send(400, render_message("Request was not accepted", str(exc)))
            return
        threshold = "160"
        files: list[tuple[str, bytes]] = []
        for field_name, filename, payload in parts:
            if field_name == "high_float_hours" and not filename:
                threshold = payload.decode("utf-8", errors="replace").strip() or "160"
            elif filename:
                files.append((filename, payload))
        status, page = evaluate_upload(files, threshold)
        self._send(status, page)

    def _send(self, status: int, page: str) -> None:
        data = page.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        return


def serve(host: str, port: int) -> None:
    httpd = ThreadingHTTPServer((host, port), CheckerHandler)
    print(f"XER checker at http://{host}:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
