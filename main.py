import ipaddress
import json
import logging
import os
from typing import Any

from flask import Flask, abort, jsonify, request
from werkzeug.exceptions import HTTPException


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger("coolify_webhook")


def _parse_allowed_ips(raw: str | None) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    if not raw:
        return []
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        networks.append(ipaddress.ip_network(item))
    return networks


class ConnectionDrop(HTTPException):
    code = 444
    description = ""

    def get_body(self, environ=None, scope=None):
        return b""

    def get_headers(self, environ=None, scope=None):
        return []


def _read_secret(name: str) -> str | None:
    file_path = os.getenv(f"{name}_FILE")
    if file_path:
        try:
            with open(file_path) as fh:
                return fh.read().strip()
        except OSError as exc:
            logger.warning("Failed to read secret file %s: %s", file_path, exc)
    return os.getenv(name)


ALLOWED_IPS = _parse_allowed_ips(_read_secret("ALLOWED_IPS"))


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or ""


def _ip_allowed(ip_str: str) -> bool:
    if not ALLOWED_IPS:
        return True
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(addr in net for net in ALLOWED_IPS)


def validate_payload(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return "JSON body must be an object"

    expected_types = {
        "success": bool,
        "event": str,
        "message": str,
    }
    for field, expected_type in expected_types.items():
        if field not in payload:
            return f"Missing required field: {field}"
        if not isinstance(payload[field], expected_type):
            return f"Field {field} must be {expected_type.__name__}"

    return None


def create_app() -> Flask:
    app = Flask(__name__)

    @app.errorhandler(ConnectionDrop)
    def _drop(_error):
        return "", 444

    @app.before_request
    def _check_ip():
        if not request.path.startswith("/webhooks"):
            return None
        client_ip = _client_ip()
        if not _ip_allowed(client_ip):
            logger.warning("Rejected request from disallowed IP: %s", client_ip)
            abort(ConnectionDrop())
        return None

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.post("/webhooks/coolify")
    def coolify_webhook():
        payload = request.get_json(silent=True)
        validation_error = validate_payload(payload)

        if validation_error:
            logger.warning(
                "Rejected Coolify webhook: %s; body=%s",
                validation_error,
                request.get_data(as_text=True),
            )
            return jsonify(ok=False, error=validation_error), 400

        logger.info(
            "Received Coolify event=%s success=%s payload=%s",
            payload["event"],
            payload["success"],
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )

        return jsonify(ok=True, event=payload["event"])

    return app


app = create_app()


def main():
    app.run(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
