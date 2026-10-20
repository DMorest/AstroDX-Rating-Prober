import sys
import unittest
from io import BytesIO
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.local_b50_image import generate_b50_png


class LocalB50ImageTests(unittest.TestCase):
    def test_generates_png_without_network(self):
        records = [{
            "title": "Don't Fight The Music",
            "difficulty": "MASTER",
            "constant": 14.0,
            "song_type": "DX",
            "achievement": 100.3821,
            "dx_score": 2946,
            "rating": 320,
            "song_id": "12345",
        }]
        raw = generate_b50_png(records, 15000, "标准 B35 + B15", "SaltMeta · 日本 JP", fetch_covers=False)
        with Image.open(BytesIO(raw)) as result:
            self.assertEqual(result.format, "PNG")
            self.assertEqual(result.width, 1600)
            self.assertGreater(result.height, 300)


if __name__ == "__main__":
    unittest.main()
