import json
import tempfile
import unittest
from pathlib import Path

from bot import NotificationBot


class NotificationBotTestCase(unittest.TestCase):
    def test_empty_saved_chat_id_does_not_override_configured_chat_id(self):
        with tempfile.TemporaryDirectory() as directory:
            bindings_file = Path(directory) / "bindings.json"
            bindings_file.write_text(json.dumps({"chat_id": 0, "topics": {}}))

            bot = NotificationBot(
                token="",
                chat_id=123456,
                bindings_file=str(bindings_file),
            )

            self.assertEqual(bot._chat_id, 123456)


if __name__ == "__main__":
    unittest.main()
