from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import shutil
import sqlite3
import uuid
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_NAME = "CopySpace"
APP_VERSION = "0.4.3"
LEGACY_APP_NAME = "ClipVault"
MAX_TEXT_BYTES = 1_000_000
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
DEFAULT_HISTORY_LIMIT = 800

DEFAULT_CATEGORIES = ["Без категории", "Код", "Ссылки", "Работа", "Учёба", "Личное"]

# Intentionally conservative: these checks reduce accidental storage of obvious
# credentials. They are heuristics, not a guarantee that every secret is detected.
SENSITIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("похоже на пароль", re.compile(r"(?i)\b(password|passwd|passphrase|пароль)\s*[:=]\s*\S+")),
    ("похоже на одноразовый код", re.compile(r"(?i)\b(otp|one[- ]time code|verification code|код подтверждения)\D{0,12}\d{4,8}\b")),
    ("похоже на приватный ключ", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("похоже на токен доступа", re.compile(r"(?i)\b(bearer\s+[a-z0-9._~-]{16,}|ghp_[a-z0-9]{20,}|github_pat_[a-z0-9_]{20,}|sk-[a-z0-9]{20,})")),
    ("похоже на ключ облачного сервиса", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
]


def _copy_missing_tree(source: Path, destination: Path) -> None:
    """Copy legacy files without replacing anything already in the new folder."""
    if not source.exists():
        return
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            _copy_missing_tree(item, target)
        elif not target.exists():
            shutil.copy2(item, target)


def _rename_legacy_database(folder: Path) -> None:
    """Rename the database and SQLite sidecars after copying the old app folder."""
    old_db = folder / "clipvault.db"
    new_db = folder / "copyspace.db"
    if old_db.exists() and not new_db.exists():
        old_db.rename(new_db)
    for suffix in ("-wal", "-shm"):
        old_sidecar = folder / f"clipvault.db{suffix}"
        new_sidecar = folder / f"copyspace.db{suffix}"
        if old_sidecar.exists() and not new_sidecar.exists():
            old_sidecar.rename(new_sidecar)


def _rewrite_migrated_image_paths(database: Path, legacy: Path, current: Path) -> None:
    """Point copied image records at their new CopySpace image files."""
    if not database.exists():
        return
    old_images = (legacy / "images").resolve()
    new_images = (current / "images").resolve()
    with sqlite3.connect(database) as connection:
        try:
            rows = connection.execute(
                "SELECT id, image_path FROM clips WHERE image_path IS NOT NULL"
            ).fetchall()
        except sqlite3.Error:
            return
        for clip_id, raw_path in rows:
            try:
                relative = Path(str(raw_path)).resolve().relative_to(old_images)
            except (OSError, ValueError):
                continue
            migrated_path = new_images / relative
            if migrated_path.exists():
                connection.execute(
                    "UPDATE clips SET image_path=? WHERE id=?",
                    (str(migrated_path), clip_id),
                )


def _migrate_legacy_data_directory(base: Path) -> None:
    """Preserve an existing ClipVault archive when the app becomes CopySpace.

    The old folder is intentionally retained as a backup. When a CopySpace
    folder already exists, only missing files are copied; no existing database
    or image is overwritten.
    """
    legacy = base / LEGACY_APP_NAME
    current = base / APP_NAME
    if not legacy.is_dir():
        return

    copied_legacy_database = False
    if not current.exists():
        shutil.copytree(legacy, current)
        copied_legacy_database = (current / "clipvault.db").exists()
    elif not (current / "copyspace.db").exists():
        _copy_missing_tree(legacy, current)
        copied_legacy_database = (current / "clipvault.db").exists()

    _rename_legacy_database(current)
    if copied_legacy_database:
        _rewrite_migrated_image_paths(current / "copyspace.db", legacy, current)


def data_directory() -> Path:
    """Return the CopySpace data directory and migrate a prior ClipVault archive."""
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        base = Path(os.environ["LOCALAPPDATA"])
    else:
        base = Path.home() / ".local" / "share"
    base.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_data_directory(base)
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    (path / "images").mkdir(parents=True, exist_ok=True)
    return path


def _utc_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _luhn_valid(digits: str) -> bool:
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    total = 0
    parity = len(digits) % 2
    for index, char in enumerate(digits):
        number = int(char)
        if index % 2 == parity:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def sensitive_reason(text: str) -> str | None:
    for reason, pattern in SENSITIVE_PATTERNS:
        if pattern.search(text):
            return reason
    # Also avoid obvious payment-card numbers. Luhn reduces accidental matches
    # from ordinary long numeric strings.
    for match in re.finditer(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)", text):
        digits = re.sub(r"\D", "", match.group(0))
        if _luhn_valid(digits):
            return "похоже на номер платёжной карты"
    return None



def _is_url_candidate(value: str) -> bool:
    """Check that a single value is a plausible URL, not just one bare word."""
    candidate = value.strip().strip("<>").rstrip(".,;:!?)]}\"'")
    if not candidate or any(ch.isspace() for ch in candidate):
        return False

    lowered = candidate.lower()
    if lowered.startswith("mailto:"):
        address = candidate[7:].split("?", 1)[0]
        return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", address))

    explicit_scheme = bool(re.match(r"^(?:https?|ftp)://", candidate, re.IGNORECASE))
    has_www = lowered.startswith("www.")
    if re.match(r"^[a-z][a-z0-9+.-]*://", candidate, re.IGNORECASE) and not explicit_scheme:
        return False

    normalized = candidate if explicit_scheme else "https://" + candidate
    try:
        parsed = urlparse(normalized)
        host = parsed.hostname
        if parsed.scheme.lower() not in {"http", "https", "ftp"} or not host:
            return False
        # Reject malformed ports (urlparse validates them lazily).
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            return False
    except ValueError:
        return False

    # Explicit URLs may use local hostnames (for example, an intranet server).
    # Without a scheme, require a dotted domain or a valid IP address so that
    # ordinary words like "hello" are never promoted to links.
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass

    try:
        ascii_host = host.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        return False
    labels = ascii_host.split(".")
    if explicit_scheme:
        return all(
            label and len(label) <= 63 and re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)
            for label in labels
        )
    if not (has_www or len(labels) >= 2) or len(labels[-1]) < 2:
        return False
    return all(
        label and len(label) <= 63 and re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)
        for label in labels
    )


def classify_clipboard_text(text: str) -> tuple[str, str]:
    """Return (content_type, suggested_category) for actual URLs or plain text."""
    # Support one URL or a clipboard list containing only URLs. Mixed prose and
    # URLs remains plain text to avoid classifying notes as links.
    candidates = [line.strip() for line in str(text).splitlines() if line.strip()]
    if candidates and all(_is_url_candidate(line) for line in candidates):
        return "link", "Ссылки"
    return "text", "Без категории"


class CopySpaceStore:
    """Small local SQLite store for clipboard entries and saved image files."""

    def __init__(self, root: Path | None = None, history_limit: int = DEFAULT_HISTORY_LIMIT):
        self.root = Path(root) if root else data_directory()
        self.root.mkdir(parents=True, exist_ok=True)
        self.images_dir = self.root / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "copyspace.db"
        self.history_limit = max(50, int(history_limit))
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._initialize()

    def _initialize(self) -> None:
        with self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS clips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL CHECK(kind IN ('text', 'image')),
                    text_content TEXT,
                    image_path TEXT,
                    preview TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT 'Без категории',
                    favorite INTEGER NOT NULL DEFAULT 0,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_clips_created ON clips(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_clips_hash ON clips(content_hash);
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            columns = {row[1] for row in self.conn.execute("PRAGMA table_info(clips)").fetchall()}
            if "content_type" not in columns:
                self.conn.execute("ALTER TABLE clips ADD COLUMN content_type TEXT NOT NULL DEFAULT 'text'")

            # Repair false-positive link labels created by older releases, while
            # preserving real links and any user-selected non-default category.
            previously_tagged_links = self.conn.execute(
                "SELECT id, text_content, category FROM clips "
                "WHERE kind='text' AND content_type='link'"
            ).fetchall()
            for item in previously_tagged_links:
                actual_type, _ = classify_clipboard_text(item["text_content"] or "")
                if actual_type != "link":
                    repaired_category = (
                        "Без категории" if item["category"] == "Ссылки" else item["category"]
                    )
                    self.conn.execute(
                        "UPDATE clips SET content_type='text', category=? WHERE id=?",
                        (repaired_category, item["id"]),
                    )

            for category in DEFAULT_CATEGORIES:
                self.conn.execute(
                    "INSERT OR IGNORE INTO categories(name, created_at) VALUES(?, ?)",
                    (category, _utc_now()),
                )

    def close(self) -> None:
        self.conn.close()

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )

    def categories(self) -> list[str]:
        rows = self.conn.execute("SELECT name FROM categories ORDER BY id").fetchall()
        return [str(row["name"]) for row in rows]

    def add_category(self, name: str) -> tuple[bool, str]:
        clean = " ".join(str(name).split())
        if not clean:
            return False, "Название категории не может быть пустым."
        if len(clean) > 32:
            return False, "Название категории должно быть не длиннее 32 символов."
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO categories(name, created_at) VALUES(?, ?)",
                    (clean, _utc_now()),
                )
            return True, clean
        except sqlite3.IntegrityError:
            return False, "Такая категория уже существует."

    def delete_category(self, name: str) -> tuple[bool, str]:
        if name == "Без категории":
            return False, "Категорию «Без категории» нельзя удалить."
        with self.conn:
            self.conn.execute(
                "UPDATE clips SET category='Без категории' WHERE category=?", (name,)
            )
            cursor = self.conn.execute("DELETE FROM categories WHERE name=?", (name,))
        return (cursor.rowcount > 0, "Категория удалена." if cursor.rowcount else "Категория не найдена.")

    def add_text(self, text: str, category: str = "Без категории", content_type: str = "text") -> dict[str, Any]:
        clean = str(text).replace("\x00", "")
        if not clean.strip():
            return {"status": "ignored", "reason": "Пустой текст."}
        raw = clean.encode("utf-8", errors="replace")
        if len(raw) > MAX_TEXT_BYTES:
            return {"status": "ignored", "reason": "Текст слишком большой (лимит 1 МБ)."}
        reason = sensitive_reason(clean)
        if reason:
            return {"status": "blocked", "reason": f"Не сохранено: {reason}."}
        digest = hashlib.sha256(b"text\0" + raw).hexdigest()
        latest = self.conn.execute(
            "SELECT id, content_hash FROM clips ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if latest and latest["content_hash"] == digest:
            with self.conn:
                self.conn.execute(
                    "UPDATE clips SET created_at=?, content_type=?, category=? WHERE id=?",
                    (_utc_now(), content_type, category if category in self.categories() else "Без категории", latest["id"]),
                )
            return {"status": "duplicate", "id": int(latest["id"]), "reason": "Этот фрагмент уже последний в истории."}
        if category not in self.categories():
            category = "Без категории"
        preview = clean.strip().replace("\r", " ").replace("\n", "  ·  ")
        if len(preview) > 220:
            preview = preview[:217] + "…"
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO clips(kind, text_content, preview, category, created_at, content_hash, size_bytes, content_type) "
                "VALUES('text', ?, ?, ?, ?, ?, ?, ?)",
                (clean, preview, category, _utc_now(), digest, len(raw), content_type),
            )
            clip_id = int(cursor.lastrowid)
        self._prune()
        return {"status": "saved", "id": clip_id}

    def add_image(self, image_bytes: bytes, category: str = "Без категории") -> dict[str, Any]:
        if not image_bytes:
            return {"status": "ignored", "reason": "Пустое изображение."}
        if len(image_bytes) > MAX_IMAGE_BYTES:
            return {"status": "ignored", "reason": "Изображение больше лимита 8 МБ."}
        digest = hashlib.sha256(b"image\0" + image_bytes).hexdigest()
        latest = self.conn.execute(
            "SELECT id, content_hash FROM clips ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if latest and latest["content_hash"] == digest:
            with self.conn:
                self.conn.execute(
                    "UPDATE clips SET created_at=?, category=? WHERE id=?",
                    (_utc_now(), category if category in self.categories() else "Без категории", latest["id"]),
                )
            return {"status": "duplicate", "id": int(latest["id"]), "reason": "Это изображение уже последнее в истории."}
        filename = f"{uuid.uuid4().hex}.png"
        image_path = self.images_dir / filename
        image_path.write_bytes(image_bytes)
        if category not in self.categories():
            category = "Без категории"
        try:
            with self.conn:
                cursor = self.conn.execute(
                    "INSERT INTO clips(kind, image_path, preview, category, created_at, content_hash, size_bytes) "
                    "VALUES('image', ?, ?, ?, ?, ?, ?)",
                    (str(image_path), "Изображение из буфера обмена", category, _utc_now(), digest, len(image_bytes)),
                )
                clip_id = int(cursor.lastrowid)
        except Exception:
            image_path.unlink(missing_ok=True)
            raise
        self._prune()
        return {"status": "saved", "id": clip_id}

    def _prune(self) -> None:
        rows = self.conn.execute(
            "SELECT id, image_path FROM clips ORDER BY pinned DESC, created_at DESC, id DESC LIMIT -1 OFFSET ?",
            (self.history_limit,),
        ).fetchall()
        if not rows:
            return
        with self.conn:
            self.conn.executemany("DELETE FROM clips WHERE id=?", [(row["id"],) for row in rows])
        for row in rows:
            self._remove_image(row["image_path"])

    @staticmethod
    def _remove_image(image_path: str | None) -> None:
        if image_path:
            try:
                Path(image_path).unlink(missing_ok=True)
            except OSError:
                pass

    def list_clips(
        self,
        scope: str = "all",
        query: str = "",
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if scope == "favorites":
            clauses.append("favorite=1")
        elif scope == "text":
            clauses.append("kind='text'")
        elif scope == "images":
            clauses.append("kind='image'")
        elif scope == "links":
            clauses.append("content_type='link'")
        if category:
            clauses.append("category=?")
            params.append(category)
        clean_query = query.strip()
        if clean_query:
            clauses.append("(COALESCE(text_content, preview, '') LIKE ? OR category LIKE ?)")
            like = f"%{clean_query}%"
            params.extend([like, like])
        sql = "SELECT * FROM clips"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY pinned DESC, created_at DESC, id DESC LIMIT 1000"
        return [dict(row) for row in self.conn.execute(sql, params).fetchall()]

    def get_clip(self, clip_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM clips WHERE id=?", (int(clip_id),)).fetchone()
        return dict(row) if row else None

    def update_flag(self, clip_id: int, field: str, value: bool) -> None:
        if field not in {"favorite", "pinned"}:
            raise ValueError("Unsupported flag")
        with self.conn:
            self.conn.execute(f"UPDATE clips SET {field}=? WHERE id=?", (int(bool(value)), int(clip_id)))

    def update_category(self, clip_id: int, category: str) -> None:
        if category not in self.categories():
            category = "Без категории"
        with self.conn:
            self.conn.execute("UPDATE clips SET category=? WHERE id=?", (category, int(clip_id)))

    def delete_clip(self, clip_id: int) -> None:
        row = self.get_clip(clip_id)
        if not row:
            return
        with self.conn:
            self.conn.execute("DELETE FROM clips WHERE id=?", (int(clip_id),))
        self._remove_image(row.get("image_path"))

    def clear_history(self) -> int:
        rows = self.conn.execute("SELECT image_path FROM clips WHERE image_path IS NOT NULL").fetchall()
        count = int(self.conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0])
        with self.conn:
            self.conn.execute("DELETE FROM clips")
        for row in rows:
            self._remove_image(row["image_path"])
        return count

    def stats(self) -> dict[str, int]:
        row = self.conn.execute(
            "SELECT COUNT(*) AS total, SUM(kind='text') AS text_count, SUM(kind='image') AS image_count, "
            "SUM(favorite=1) AS favorites, COALESCE(SUM(size_bytes),0) AS bytes FROM clips"
        ).fetchone()
        return {
            "total": int(row["total"] or 0),
            "text": int(row["text_count"] or 0),
            "images": int(row["image_count"] or 0),
            "favorites": int(row["favorites"] or 0),
            "bytes": int(row["bytes"] or 0),
        }

    def integrity_check(self) -> str:
        return str(self.conn.execute("PRAGMA integrity_check").fetchone()[0])
