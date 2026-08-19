import os
import sys
import types
import unittest


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

yaml_stub = types.ModuleType("yaml")
yaml_stub.safe_load = lambda *_args, **_kwargs: {}
sys.modules.setdefault("yaml", yaml_stub)

import sync_garmin  # noqa: E402


def _base_payload() -> dict:
    return {
        "activityId": "12345",
        "startTimeLocal": "2026-03-14 07:00:00",
        "startTimeGMT": "2026-03-14 14:00:00",
        "activityType": {"typeKey": "running"},
        "distance": 5000,
        "duration": 1800,
        "movingDuration": 1750,
    }


class SyncGarminNormalizeHeartRateTests(unittest.TestCase):
    def test_normalize_activity_extracts_top_level_average_hr(self) -> None:
        payload = dict(_base_payload(), averageHR=152)

        normalized = sync_garmin._normalize_activity(payload)

        self.assertAlmostEqual(normalized["average_heartrate"], 152.0)

    def test_normalize_activity_extracts_summary_dto_average_hr(self) -> None:
        payload = dict(_base_payload())
        payload["summaryDTO"] = {"averageHR": 145}

        normalized = sync_garmin._normalize_activity(payload)

        self.assertAlmostEqual(normalized["average_heartrate"], 145.0)

    def test_normalize_activity_extracts_activity_summary_average_hr(self) -> None:
        payload = dict(_base_payload())
        payload["activitySummary"] = {"averageHR": 138}

        normalized = sync_garmin._normalize_activity(payload)

        self.assertAlmostEqual(normalized["average_heartrate"], 138.0)

    def test_normalize_activity_omits_average_heartrate_when_missing(self) -> None:
        payload = dict(_base_payload())

        normalized = sync_garmin._normalize_activity(payload)

        self.assertNotIn("average_heartrate", normalized)

    def test_normalize_activity_rejects_implausible_heart_rate(self) -> None:
        payload = dict(_base_payload(), averageHR=300)

        normalized = sync_garmin._normalize_activity(payload)

        self.assertNotIn("average_heartrate", normalized)

    def test_normalize_activity_prefers_first_plausible_candidate(self) -> None:
        payload = dict(_base_payload())
        payload["averageHR"] = 0
        payload["summaryDTO"] = {"averageHR": 160}

        normalized = sync_garmin._normalize_activity(payload)

        self.assertAlmostEqual(normalized["average_heartrate"], 160.0)


if __name__ == "__main__":
    unittest.main()
