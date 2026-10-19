import os
import sys
import unittest


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import activity_types  # noqa: E402


class ActivityTypesTests(unittest.TestCase):
    def test_canonicalize_activity_type_maps_garmin_aliases(self) -> None:
        self.assertEqual(
            activity_types.canonicalize_activity_type("trail running", source="garmin"),
            "TrailRun",
        )
        self.assertEqual(
            activity_types.canonicalize_activity_type("virtual cycling", source="garmin"),
            "VirtualRide",
        )

    def test_canonicalize_activity_type_falls_back_to_known_shape(self) -> None:
        self.assertEqual(activity_types.canonicalize_activity_type("strength session"), "WeightTraining")
        self.assertEqual(activity_types.canonicalize_activity_type(""), "Unknown")

    def test_normalize_activity_type_honors_alias_then_grouping(self) -> None:
        featured = ["Run", "Ride"]
        group_aliases = {"TrailRun": "Run"}
        normalized_alias = activity_types.normalize_activity_type(
            "TrailRun",
            featured_types=featured,
            group_other_types=False,
            other_bucket="OtherSports",
            group_aliases=group_aliases,
        )
        self.assertEqual(normalized_alias, "Run")

        normalized_grouped = activity_types.normalize_activity_type(
            "Soccer",
            featured_types=featured,
            group_other_types=True,
            other_bucket="OtherSports",
            group_aliases={},
        )
        self.assertEqual(normalized_grouped, "TeamSports")

    def test_type_label_and_accent_remain_stable(self) -> None:
        self.assertEqual(activity_types.type_label("HighIntensityIntervalTraining"), "HITT")
        self.assertEqual(activity_types.type_label("MountainBikeRide"), "Mountain Bike Ride")
        self.assertEqual(activity_types.type_accent("Run"), "#01cdfe")
        self.assertEqual(activity_types.type_accent("CompletelyNewType"), activity_types.type_accent("CompletelyNewType"))

    def test_ordered_types_prefers_featured_then_count_then_label(self) -> None:
        counts = {"Run": 2, "Swim": 3, "Walk": 3}
        featured = ["Run", "Ride"]
        ordered = activity_types.ordered_types(counts, featured)
        self.assertEqual(ordered, ["Run", "Ride", "Swim", "Walk"])

    def test_ordered_types_includes_featured_types_without_counts(self) -> None:
        counts = {"Run": 5, "Swim": 3}
        featured = ["Run", "Ride", "Commute", "Swim"]
        ordered = activity_types.ordered_types(counts, featured)
        self.assertEqual(ordered, ["Run", "Swim", "Ride", "Commute"])

    def test_ordered_types_falls_back_to_featured_when_no_counts(self) -> None:
        self.assertEqual(activity_types.ordered_types({}, ["Run", "Ride"]), ["Run", "Ride"])

    def test_build_type_meta_contains_labels_and_accents(self) -> None:
        meta = activity_types.build_type_meta(["Run", "OtherSports"])
        self.assertEqual(meta["Run"]["label"], "Run")
        self.assertEqual(meta["Run"]["accent"], "#01cdfe")
        self.assertIn("label", meta["OtherSports"])
        self.assertIn("accent", meta["OtherSports"])


if __name__ == "__main__":
    unittest.main()
