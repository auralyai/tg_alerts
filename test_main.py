import unittest

from main import create_app


class CoolifyWebhookTestCase(unittest.TestCase):
    def setUp(self):
        app = create_app()
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_accepts_test_event(self):
        response = self.client.post(
            "/webhooks/coolify",
            json={
                "success": True,
                "event": "test",
                "message": "This is a test webhook notification from Coolify.",
                "url": "https://coolify.example.com",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True, "event": "test"})

    def test_accepts_unknown_event_with_extra_fields(self):
        response = self.client.post(
            "/webhooks/coolify",
            json={
                "success": False,
                "event": "future_event",
                "message": "A new event",
                "new_field": {"nested": True},
            },
        )

        self.assertEqual(response.status_code, 200)

    def test_rejects_missing_required_field(self):
        response = self.client.post(
            "/webhooks/coolify",
            json={"success": True, "event": "test"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {"ok": False, "error": "Missing required field: message"},
        )

    def test_rejects_non_json_body(self):
        response = self.client.post(
            "/webhooks/coolify",
            data="not json",
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
