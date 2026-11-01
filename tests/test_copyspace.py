import tempfile
import unittest
from pathlib import Path

from copyspace_core import CopySpaceStore, classify_clipboard_text, sensitive_reason, _migrate_legacy_data_directory


class CopySpaceCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = CopySpaceStore(Path(self.temp.name))

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_save_text_and_search(self):
        result = self.store.add_text("print('hello')")
        self.assertEqual(result["status"], "saved")
        rows = self.store.list_clips(query="hello")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "text")

    def test_classifies_links(self):
        self.assertEqual(classify_clipboard_text("https://example.com/path")[0], "link")
        self.assertEqual(classify_clipboard_text("www.example.com")[0], "link")
        self.assertEqual(classify_clipboard_text("example.com/page")[0], "link")
        self.assertEqual(classify_clipboard_text("192.168.1.10")[0], "link")
        self.assertEqual(classify_clipboard_text("mailto:user@example.com")[0], "link")
        self.assertEqual(classify_clipboard_text("https://example.com\nhttps://openai.com")[0], "link")

    def test_plain_words_are_not_links(self):
        for value in ("hello", "привет", "CopySpace", "документы", "version 0.4.2"):
            with self.subTest(value=value):
                self.assertEqual(classify_clipboard_text(value), ("text", "Без категории"))

    def test_mixed_text_and_url_stays_text(self):
        self.assertEqual(classify_clipboard_text("Смотри: https://example.com"), ("text", "Без категории"))

    def test_invalid_url_is_not_link(self):
        self.assertEqual(classify_clipboard_text("https://")[0], "text")
        self.assertEqual(classify_clipboard_text("not-a-domain")[0], "text")

    def test_startup_repairs_old_false_positive_links(self):
        self.store.add_text("обычное слово", category="Ссылки", content_type="link")
        root = Path(self.temp.name)
        self.store.close()
        self.store = CopySpaceStore(root)
        rows = self.store.list_clips()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["content_type"], "text")
        self.assertEqual(rows[0]["category"], "Без категории")

    def test_link_scope_and_category(self):
        result = self.store.add_text("https://example.com", category="Ссылки", content_type="link")
        rows = self.store.list_clips(scope="links")
        self.assertEqual(result["status"], "saved")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["content_type"], "link")

    def test_deduplicate_consecutive_clip(self):
        first = self.store.add_text("same value")
        second = self.store.add_text("same value")
        self.assertEqual(first["status"], "saved")
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(self.store.stats()["total"], 1)

    def test_blocks_obvious_password_and_token(self):
        self.assertIsNotNone(sensitive_reason("password: hunter2"))
        self.assertEqual(self.store.add_text("password: hunter2")["status"], "blocked")
        self.assertEqual(self.store.add_text("Bearer abcdefghijklmnopqrstuvwxyz123456")["status"], "blocked")

    def test_favorites_and_category(self):
        result = self.store.add_text("A useful note")
        clip_id = result["id"]
        ok, name = self.store.add_category("Проекты")
        self.assertTrue(ok)
        self.store.update_category(clip_id, name)
        self.store.update_flag(clip_id, "favorite", True)
        self.assertEqual(len(self.store.list_clips(scope="favorites", category="Проекты")), 1)

    def test_delete_category_moves_items_to_default(self):
        result = self.store.add_text("A note")
        self.store.add_category("Temporary")
        self.store.update_category(result["id"], "Temporary")
        self.assertTrue(self.store.delete_category("Temporary")[0])
        self.assertEqual(self.store.get_clip(result["id"])["category"], "Без категории")

    def test_delete_and_clear(self):
        one = self.store.add_text("one")
        self.store.add_text("two")
        self.store.delete_clip(one["id"])
        self.assertEqual(self.store.stats()["total"], 1)
        self.assertEqual(self.store.clear_history(), 1)
        self.assertEqual(self.store.stats()["total"], 0)

    def test_image_storage_and_images_scope(self):
        result = self.store.add_image(b"fake-png-binary")
        self.assertEqual(result["status"], "saved")
        row = self.store.get_clip(result["id"])
        self.assertEqual(row["kind"], "image")
        self.assertTrue(Path(row["image_path"]).exists())
        self.assertEqual(len(self.store.list_clips(scope="images")), 1)
        self.assertEqual(row["category"], "Без категории")
        self.store.delete_clip(result["id"])
        self.assertFalse(Path(row["image_path"]).exists())

    def test_default_category_is_available_for_filtering(self):
        self.assertIn("Без категории", self.store.categories())
        self.store.add_text("A loose note")
        self.assertEqual(
            len(self.store.list_clips(category="Без категории")),
            1,
        )

    def test_legacy_clipvault_folder_is_copied_to_copyspace(self):
        base = Path(self.temp.name) / "migration-root"
        legacy = base / "ClipVault"
        legacy_store = CopySpaceStore(legacy)
        legacy_store.add_text("saved before the rename")
        legacy_image = legacy_store.add_image(b"legacy-image-bytes")
        legacy_image_path = Path(legacy_store.get_clip(legacy_image["id"])["image_path"])
        legacy_store.close()
        (legacy / "copyspace.db").rename(legacy / "clipvault.db")

        _migrate_legacy_data_directory(base)

        current = base / "CopySpace"
        migrated_store = CopySpaceStore(current)
        try:
            rows = migrated_store.list_clips()
            self.assertEqual(len(rows), 2)
            self.assertTrue(any(row.get("text_content") == "saved before the rename" for row in rows))
            image_row = next(row for row in rows if row["kind"] == "image")
            self.assertTrue(Path(image_row["image_path"]).exists())
            self.assertEqual(Path(image_row["image_path"]).read_bytes(), b"legacy-image-bytes")
            self.assertEqual(Path(image_row["image_path"]).parent, (current / "images").resolve())
        finally:
            migrated_store.close()

        # Migration is non-destructive: the original folder remains as a backup.
        self.assertTrue((legacy / "clipvault.db").exists())
        self.assertTrue(legacy_image_path.exists())


if __name__ == "__main__":
    unittest.main()
