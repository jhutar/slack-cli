"""Extract authentication tokens and cookie from the Slack desktop app's local storage."""

import hashlib
import json
import sqlite3
from pathlib import Path

DEFAULT_SEARCH_PATHS = [
    (Path("~/.var/app/com.slack.Slack/config/Slack").expanduser(), "flatpak"),
    (Path("~/.config/Slack").expanduser(), "standard"),
]


def find_slack_installation(search_paths=None):
    if search_paths is None:
        search_paths = DEFAULT_SEARCH_PATHS

    for base_path, label in search_paths:
        leveldb_path = base_path / "Local Storage" / "leveldb"
        if leveldb_path.is_dir():
            return {
                "base_path": base_path,
                "leveldb_path": leveldb_path,
                "cookies_path": base_path / "Cookies",
                "source": label,
            }

    searched = ", ".join(str(p) for p, _ in search_paths)
    raise SystemExit(
        f"Error: No Slack installation found. Searched: {searched}"
    )


def extract_tokens(leveldb_path):
    import plyvel

    try:
        db = plyvel.DB(str(leveldb_path))
    except plyvel.Error as e:
        if "lock" in str(e).lower():
            raise SystemExit(
                "Error: Slack's database is locked. "
                "Quit the Slack app and try again."
            ) from e
        raise SystemExit(
            f"Error: Could not open Slack's local storage: {e}"
        ) from e

    try:
        cfg_value = None
        for key, value in db.iterator():
            if b"localConfig_v2" in key:
                cfg_value = value
                break

        if cfg_value is None:
            raise SystemExit(
                "Error: No workspace tokens found in Slack's local storage. "
                "The Slack app may need to be opened at least once."
            )

        data = _parse_local_config(cfg_value)

        tokens = []
        for team in data["teams"].values():
            tokens.append({
                "url": team["url"],
                "name": team["name"],
                "token": team["token"],
            })
        return tokens
    finally:
        db.close()


def decrypt_cookie(cookies_path):
    if not cookies_path.exists():
        raise SystemExit(
            f"Error: Cookie database not found at {cookies_path}. "
            "The Slack app may need to be opened at least once."
        )

    encrypted_value = _read_cookie_from_db(cookies_path)
    password = _get_safe_storage_password()
    return _decrypt_v11_cookie(encrypted_value, password)


def _read_cookie_from_db(cookies_path):
    conn = sqlite3.connect(f"file:{cookies_path}?mode=ro", uri=True)
    try:
        cursor = conn.execute(
            "SELECT encrypted_value FROM cookies "
            "WHERE host_key = '.slack.com' AND name = 'd'"
        )
        row = cursor.fetchone()
        if row is None:
            raise SystemExit(
                "Error: No authentication cookie found in Slack's cookie store. "
                "Log into at least one workspace in the Slack app first."
            )
        return row[0]
    finally:
        conn.close()


def _get_safe_storage_password():
    import secretstorage

    try:
        connection = secretstorage.dbus_init()
        collection = secretstorage.get_default_collection(connection)
        if collection.is_locked():
            collection.unlock()

        for item in collection.get_all_items():
            if item.get_label() == "Slack Safe Storage":
                return item.get_secret().decode("utf-8")
    except Exception as e:
        raise SystemExit(
            "Error: Could not decrypt the authentication cookie. "
            f"Ensure GNOME Keyring is unlocked. ({e})"
        ) from e

    raise SystemExit(
        "Error: Could not find 'Slack Safe Storage' in the keyring. "
        "The Slack app may need to be opened at least once."
    )


def _decrypt_v11_cookie(encrypted_value, password):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    if not encrypted_value[:3] == b"v11":
        raise SystemExit(
            "Error: Unexpected cookie encryption format. "
            "Expected v11, got: " + encrypted_value[:3].hex()
        )

    iv = encrypted_value[3:19]
    ciphertext = encrypted_value[19:]

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA1(),
        length=16,
        salt=b"saltysalt",
        iterations=1,
    )
    key = kdf.derive(password.encode("utf-8"))

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    # Strip PKCS7 padding
    pad_len = plaintext[-1]
    plaintext = plaintext[:-pad_len]

    return plaintext.decode("utf-8")


def _parse_local_config(raw):
    if not raw:
        raise ValueError("localConfig is empty")

    if raw[:1] in (b"\x00", b"\x01", b"\x02"):
        data = raw[1:]
    else:
        data = raw

    if data.count(0) > len(data) // 4:
        encodings = ("utf-16-le", "utf-8")
    else:
        encodings = ("utf-8", "utf-16-le")

    last_err = None
    for enc in encodings:
        try:
            text = data.decode(enc)
        except UnicodeDecodeError as e:
            last_err = e
            continue

        for strict in (True, False):
            try:
                return json.loads(text, strict=strict)
            except json.JSONDecodeError as e:
                last_err = e

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = text[start : end + 1]
            for strict in (True, False):
                try:
                    return json.loads(snippet, strict=strict)
                except json.JSONDecodeError as e:
                    last_err = e

    if last_err:
        raise last_err
    raise ValueError("localConfig not parseable")
