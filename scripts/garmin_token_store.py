import base64
import io
import json
import os
import shutil
import zipfile
from typing import Any


GARMIN_TOKENS_FILENAME = "garmin_tokens.json"
OAUTH1_TOKEN_FILENAME = "oauth1_token.json"
OAUTH2_TOKEN_FILENAME = "oauth2_token.json"


def token_store_ready(directory: str) -> bool:
    return os.path.isfile(os.path.join(directory, GARMIN_TOKENS_FILENAME)) or (
        os.path.isfile(os.path.join(directory, OAUTH1_TOKEN_FILENAME))
        and os.path.isfile(os.path.join(directory, OAUTH2_TOKEN_FILENAME))
    )


def hydrate_token_store_from_legacy_file(path: str, directory: str) -> None:
    if not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return
    if not isinstance(payload, dict):
        return

    oauth1 = payload.get("oauth1_token")
    oauth2 = payload.get("oauth2_token")
    if isinstance(oauth1, dict):
        _write_json(os.path.join(directory, OAUTH1_TOKEN_FILENAME), oauth1)
    if isinstance(oauth2, dict):
        _write_json(os.path.join(directory, OAUTH2_TOKEN_FILENAME), oauth2)


def encode_token_store_dir_as_zip_b64(directory: str) -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for root, _dirs, files in os.walk(directory):
            for filename in sorted(files):
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, directory)
                info = zipfile.ZipInfo(rel_path)
                info.date_time = (1980, 1, 1, 0, 0, 0)
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(full_path, "rb") as f:
                    archive.writestr(info, f.read())
    data = buffer.getvalue()
    if not data:
        raise RuntimeError("Generated Garmin token store archive was empty.")
    return base64.b64encode(data).decode("ascii")


def decode_token_store_b64(encoded: str) -> bytes:
    try:
        return base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError(f"Invalid Garmin token_store_b64 value: {exc}") from exc


def write_token_store_bytes(token_bytes: bytes, token_store_path: str) -> str:
    _clear_and_prepare_dir(token_store_path)

    extracted = False
    try:
        with zipfile.ZipFile(io.BytesIO(token_bytes)) as archive:
            _safe_extract_zip(archive, token_store_path)
            extracted = True
    except zipfile.BadZipFile:
        extracted = False

    if extracted:
        return token_store_path

    # Legacy fallback for earlier secret format variants.
    try:
        payload = json.loads(token_bytes.decode("utf-8"))
    except Exception:
        payload = None
    if isinstance(payload, dict):
        if _is_native_token_payload(payload):
            _write_json(os.path.join(token_store_path, GARMIN_TOKENS_FILENAME), payload)
        oauth1 = payload.get("oauth1_token")
        oauth2 = payload.get("oauth2_token")
        if isinstance(oauth1, dict):
            _write_json(os.path.join(token_store_path, OAUTH1_TOKEN_FILENAME), oauth1)
        if isinstance(oauth2, dict):
            _write_json(os.path.join(token_store_path, OAUTH2_TOKEN_FILENAME), oauth2)
        if "oauth_token" in payload and "oauth_token_secret" in payload:
            _write_json(os.path.join(token_store_path, OAUTH1_TOKEN_FILENAME), payload)
        if "access_token" in payload:
            _write_json(os.path.join(token_store_path, OAUTH2_TOKEN_FILENAME), payload)

    return token_store_path


def _clear_and_prepare_dir(path: str) -> None:
    if os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)


def _safe_extract_zip(archive: zipfile.ZipFile, target_dir: str) -> None:
    target_abs = os.path.abspath(target_dir)
    for member in archive.infolist():
        raw_name = member.filename or ""
        if not raw_name:
            continue
        normalized_name = raw_name.replace("\\", "/")
        if normalized_name.startswith("/") or normalized_name.startswith("../"):
            raise ValueError(f"Unsafe token store archive entry: {raw_name}")
        if "/../" in normalized_name or normalized_name == "..":
            raise ValueError(f"Unsafe token store archive entry: {raw_name}")

        destination = os.path.abspath(os.path.join(target_abs, normalized_name))
        if destination != target_abs and not destination.startswith(target_abs + os.sep):
            raise ValueError(f"Unsafe token store archive entry: {raw_name}")

        if member.is_dir():
            os.makedirs(destination, exist_ok=True)
            continue

        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with archive.open(member, "r") as src, open(destination, "wb") as dst:
            shutil.copyfileobj(src, dst)


def _write_json(path: str, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def _is_native_token_payload(payload: dict[str, Any]) -> bool:
    return any(
        isinstance(payload.get(key), str) and payload.get(key)
        for key in ("di_token", "di_refresh_token", "di_client_id")
    )
