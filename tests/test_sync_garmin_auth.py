import json
import os
import sys
import tempfile
import types
import unittest
from types import SimpleNamespace
from unittest import mock


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

yaml_stub = types.ModuleType("yaml")
yaml_stub.safe_load = lambda *_args, **_kwargs: {}
sys.modules.setdefault("yaml", yaml_stub)

import sync_garmin  # noqa: E402
from garmin_token_store import encode_token_store_dir_as_zip_b64  # noqa: E402


class SyncGarminAuthTests(unittest.TestCase):
    def test_load_garmin_client_passes_local_token_store_for_credentials(self) -> None:
        instances = []

        class FakeGarmin:
            def __init__(self, email=None, password=None):
                self.email = email
                self.password = password
                self.login_calls = []
                instances.append(self)

            def login(self, *args, **kwargs):
                self.login_calls.append((args, kwargs))
                return None, None

        fake_module = SimpleNamespace(Garmin=FakeGarmin)
        config = {"garmin": {"email": "runner@example.com", "password": "secret"}}

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with mock.patch.dict(sys.modules, {"garminconnect": fake_module}):
                    client = sync_garmin._load_garmin_client(config)
            finally:
                os.chdir(old_cwd)

        self.assertIs(client, instances[0])
        self.assertEqual(
            instances[0].login_calls[0],
            ((), {"tokenstore": sync_garmin.TOKEN_STORE_PATH}),
        )

    def test_load_garmin_client_writes_native_token_store_secret(self) -> None:
        instances = []

        class FakeGarmin:
            def __init__(self, email=None, password=None):
                self.login_calls = []
                instances.append(self)

            def login(self, *args, **kwargs):
                self.login_calls.append((args, kwargs))
                token_store = kwargs.get("tokenstore") or (args[0] if args else "")
                self.loaded_token_path = os.path.join(token_store, "garmin_tokens.json")
                if not os.path.isfile(self.loaded_token_path):
                    raise RuntimeError("missing native token file")
                return None, None

        with tempfile.TemporaryDirectory() as token_dir:
            with open(os.path.join(token_dir, "garmin_tokens.json"), "w", encoding="utf-8") as f:
                json.dump({"di_token": "a", "di_refresh_token": "b"}, f)
            encoded = encode_token_store_dir_as_zip_b64(token_dir)

        fake_module = SimpleNamespace(Garmin=FakeGarmin)
        config = {"garmin": {"token_store_b64": encoded}}

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with mock.patch.dict(sys.modules, {"garminconnect": fake_module}):
                    client = sync_garmin._load_garmin_client(config)
            finally:
                os.chdir(old_cwd)

        self.assertIs(client, instances[0])
        self.assertTrue(client.loaded_token_path.endswith("garmin_tokens.json"))


if __name__ == "__main__":
    unittest.main()
