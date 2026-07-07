import io
import json
import os
import sys
import tempfile
import unittest
import zipfile


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from garmin_token_store import (  # noqa: E402
    decode_token_store_b64,
    encode_token_store_dir_as_zip_b64,
    GARMIN_TOKENS_FILENAME,
    hydrate_token_store_from_legacy_file,
    token_store_ready,
    write_token_store_bytes,
)


class GarminTokenStoreTests(unittest.TestCase):
    def _write_required_tokens(self, directory: str) -> None:
        with open(os.path.join(directory, "oauth1_token.json"), "w", encoding="utf-8") as f:
            json.dump({"oauth_token": "a", "oauth_token_secret": "b"}, f)
        with open(os.path.join(directory, "oauth2_token.json"), "w", encoding="utf-8") as f:
            json.dump({"access_token": "c"}, f)

    def test_round_trip_zip_b64_write(self) -> None:
        with tempfile.TemporaryDirectory() as src_dir:
            self._write_required_tokens(src_dir)
            encoded = encode_token_store_dir_as_zip_b64(src_dir)
            token_bytes = decode_token_store_b64(encoded)

            with tempfile.TemporaryDirectory() as dst_dir:
                token_store = os.path.join(dst_dir, ".garmin_token_store")
                write_token_store_bytes(token_bytes, token_store)
                self.assertTrue(token_store_ready(token_store))

    def test_zip_b64_is_deterministic_for_same_files(self) -> None:
        with tempfile.TemporaryDirectory() as src_dir:
            self._write_required_tokens(src_dir)

            first = encode_token_store_dir_as_zip_b64(src_dir)
            second = encode_token_store_dir_as_zip_b64(src_dir)

        self.assertEqual(first, second)

    def test_native_garmin_tokens_file_marks_store_ready(self) -> None:
        with tempfile.TemporaryDirectory() as token_store:
            with open(
                os.path.join(token_store, GARMIN_TOKENS_FILENAME),
                "w",
                encoding="utf-8",
            ) as f:
                json.dump({"di_token": "a", "di_refresh_token": "b"}, f)

            self.assertTrue(token_store_ready(token_store))

    def test_write_native_json_payload(self) -> None:
        payload = {"di_token": "a", "di_refresh_token": "b", "di_client_id": "c"}
        token_bytes = json.dumps(payload).encode("utf-8")

        with tempfile.TemporaryDirectory() as dst_dir:
            token_store = os.path.join(dst_dir, ".garmin_token_store")
            write_token_store_bytes(token_bytes, token_store)

            self.assertTrue(token_store_ready(token_store))
            self.assertTrue(os.path.isfile(os.path.join(token_store, GARMIN_TOKENS_FILENAME)))

    def test_decode_invalid_base64_raises(self) -> None:
        with self.assertRaises(ValueError):
            decode_token_store_b64("!not-valid-base64!")

    def test_write_legacy_json_payload(self) -> None:
        payload = {
            "oauth1_token": {"oauth_token": "a", "oauth_token_secret": "b"},
            "oauth2_token": {"access_token": "c"},
        }
        token_bytes = json.dumps(payload).encode("utf-8")

        with tempfile.TemporaryDirectory() as dst_dir:
            token_store = os.path.join(dst_dir, ".garmin_token_store")
            write_token_store_bytes(token_bytes, token_store)
            self.assertTrue(token_store_ready(token_store))

    def test_hydrate_from_legacy_file(self) -> None:
        payload = {
            "oauth1_token": {"oauth_token": "a", "oauth_token_secret": "b"},
            "oauth2_token": {"access_token": "c"},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            legacy_path = os.path.join(tmpdir, "garth-session.json")
            with open(legacy_path, "w", encoding="utf-8") as f:
                json.dump(payload, f)

            hydrate_token_store_from_legacy_file(legacy_path, tmpdir)
            self.assertTrue(token_store_ready(tmpdir))

    def test_zip_slip_is_rejected(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("../evil.txt", "blocked")
        token_bytes = buffer.getvalue()

        with tempfile.TemporaryDirectory() as dst_dir:
            token_store = os.path.join(dst_dir, ".garmin_token_store")
            with self.assertRaises(ValueError):
                write_token_store_bytes(token_bytes, token_store)


if __name__ == "__main__":
    unittest.main()
