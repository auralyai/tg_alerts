import json
import logging
import os
from typing import Any

from flask import Flask, jsonify, request


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger("coolify_webhook")


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
