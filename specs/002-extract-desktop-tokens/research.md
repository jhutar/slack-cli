# Research: Extract Tokens from Slack Desktop App

## R1: LevelDB Python Library Selection

**Decision**: Use `plyvel` instead of `leveldb==0.201`.

**Rationale**: The `leveldb==0.201` package (used by `external/slacktokens`) relies on deprecated `PyUnicode_AS_UNICODE` and is pinned to Python <3.12. The system Python is 3.14. `plyvel` is a maintained LevelDB wrapper using Cython bindings that works with modern Python. It requires `libleveldb-dev` as a system dependency (already common on Linux).

**Alternatives considered**:
- `leveldb==0.201`: Only works up to Python 3.11. Too restrictive.
- Vendored `slacktokens.py` as-is: Same `leveldb` dependency problem; also hardcodes paths and doesn't support Flatpak.
- Reading LevelDB files without a library: LevelDB's on-disk format (sorted string tables, write-ahead log, manifest) is complex — not practical to reimplement.

## R2: Cookie Extraction Approach

**Decision**: Implement cookie decryption directly using `secretstorage` + `cryptography`, without depending on `pycookiecheat`.

**Rationale**: The cookie is stored in a standard Chromium SQLite `Cookies` database with `v11` encryption (AES-128-CBC, key derived via PBKDF2 from the GNOME Keyring safe-storage password). Both `secretstorage` and `cryptography` are already available on the system. Implementing the ~30 lines of decryption ourselves avoids pulling in `pycookiecheat` and its transitive dependencies (which also has hardcoded paths that don't cover Flatpak). This aligns with Constitution Principle I (Minimal Dependencies).

The decryption process:
1. Query GNOME Keyring (via `secretstorage`) for the "Slack Safe Storage" password.
2. Derive the AES key using PBKDF2-HMAC-SHA1 (1 iteration, 16-byte key, salt `saltysalt`).
3. Read the `encrypted_value` from the SQLite `cookies` table where `name='d'` and `host_key='.slack.com'`.
4. Strip the `v11` prefix (3 bytes), extract the IV (16 bytes), decrypt the remaining ciphertext with AES-128-CBC, and strip PKCS7 padding.

**Alternatives considered**:
- `pycookiecheat`: Brings many transitive deps, hardcodes browser paths, doesn't handle Flatpak Slack paths.
- Prompting the user for the cookie: Defeats the purpose of zero-browser extraction.

## R3: Flatpak Path Detection Strategy

**Decision**: Check paths in priority order: Flatpak first (`~/.var/app/com.slack.Slack/config/Slack/`), then standard (`~/.config/Slack/`). Use the first path where the `Local Storage/leveldb` subdirectory exists.

**Rationale**: Per the clarification, Flatpak is preferred when both exist. The detection is a simple directory existence check — no Flatpak CLI or D-Bus queries needed.

**Paths confirmed** (from user's filesystem):
- Flatpak LevelDB: `~/.var/app/com.slack.Slack/config/Slack/Local Storage/leveldb`
- Flatpak Cookies: `~/.var/app/com.slack.Slack/config/Slack/Cookies`
- Standard LevelDB: `~/.config/Slack/Local Storage/leveldb`
- Standard Cookies: `~/.config/Slack/Cookies`

## R4: Vendoring vs. Dependency Strategy

**Decision**: Do NOT use `external/slacktokens` as-is. Implement token extraction as a new module within `slack_cli` that reuses the `localConfig_v2` parsing logic but with configurable paths and modern dependencies.

**Rationale**: The vendored `slacktokens.py` has incompatible Python version constraints (`<3.12`), hardcoded paths, and pulls in `pycookiecheat`. Extracting the core logic (~40 lines for LevelDB parsing + `_parse_local_config`) into our own module gives us Flatpak support, modern Python compatibility, and minimal dependencies — all aligned with the constitution.

## R5: New Dependencies Required

| Package         | Purpose                            | Justification                                                |
|-----------------|-------------------------------------|--------------------------------------------------------------|
| `plyvel`        | Read LevelDB databases              | No stdlib alternative for LevelDB; essential for the feature |
| `secretstorage` | Access GNOME Keyring encryption key  | Required for cookie decryption on Linux/GNOME                |
| `cryptography`  | AES-128-CBC decryption               | Required for Chromium cookie decryption                      |

All three provide substantial value that cannot be achieved with reasonable effort using the standard library (Constitution Principle I).
