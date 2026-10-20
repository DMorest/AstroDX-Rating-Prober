import tempfile
import unittest
from pathlib import Path
from src.catalog_cache import load_catalog, save_catalog, cache_key

class CatalogCacheTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [{"title": "テスト曲", "difficulty": "MASTER", "constant": 13.7}]
            save_catalog("SaltMeta · 日本 JP", rows, Path(tmp))
            loaded = load_catalog("SaltMeta · 日本 JP", Path(tmp))
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded[0], rows)
            self.assertEqual(loaded[1]["row_count"], 1)

    def test_source_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            save_catalog("SaltMeta · 日本 JP", [{"title": "JP"}], Path(tmp))
            self.assertIsNone(load_catalog("SaltMeta · 国际服 INTL", Path(tmp)))

    def test_safe_key(self):
        self.assertNotIn("/", cache_key("../weird/source"))

if __name__ == "__main__":
    unittest.main()
