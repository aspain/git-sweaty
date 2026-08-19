import os
import sys
import unittest


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import provider_fields  # noqa: E402


class ProviderFieldsTests(unittest.TestCase):
    def test_coalesce(self) -> None:
        self.assertEqual(provider_fields.coalesce(None, "", [], "ok", "later"), "ok")
        self.assertIsNone(provider_fields.coalesce(None, "", []))

    def test_get_nested(self) -> None:
        payload = {"a": {"b": {"c": 1}}}
        self.assertEqual(provider_fields.get_nested(payload, ["a", "b", "c"]), 1)
        self.assertIsNone(provider_fields.get_nested(payload, ["a", "x"]))

    def test_pick_duration_seconds_prefers_positive(self) -> None:
        self.assertEqual(provider_fields.pick_duration_seconds(None, 0, -10, 35, 99), 35)
        self.assertEqual(provider_fields.pick_duration_seconds("bad", -5, 0), -5)
        self.assertEqual(provider_fields.pick_duration_seconds(None, "", []), 0.0)

    def test_pick_heart_rate_accepts_plausible_and_rejects_out_of_range(self) -> None:
        self.assertEqual(provider_fields.pick_heart_rate(0.0, 148.6), 148.6)
        self.assertEqual(provider_fields.pick_heart_rate(None, "", []), 0.0)
        self.assertEqual(provider_fields.pick_heart_rate(1.0), 1.0)
        self.assertEqual(provider_fields.pick_heart_rate(255.0), 255.0)
        self.assertEqual(provider_fields.pick_heart_rate(256.0), 0.0)
        self.assertEqual(provider_fields.pick_heart_rate(-5.0), 0.0)
        self.assertEqual(provider_fields.pick_heart_rate("bad", 152.0), 152.0)


if __name__ == "__main__":
    unittest.main()
