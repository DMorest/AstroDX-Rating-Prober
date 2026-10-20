import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.b50_image_api import build_session_image_payload, score_icon, request_session_image

class ImageApiTests(unittest.TestCase):
    def test_payload_maps_scores_and_caps_at_50(self):
        records = [{"title": "Song", "difficulty": "Re:MASTER", "song_type": "DX", "achievement": 100.5, "dx_score": 1234}]
        payload = build_session_image_payload(records, 15000, "jp")
        self.assertEqual(payload["cmd_type"], "best50")
        self.assertEqual(payload["records"]["best"][0]["difficulty"], "remaster")
        self.assertEqual(payload["records"]["best"][0]["type"], "dx")
        self.assertEqual(payload["records"]["best"][0]["score_icon"], "sssp")
        self.assertEqual(payload["records"]["best"][0]["dx_score"], "1234")
        self.assertEqual(len(build_session_image_payload(records * 60, 999, "intl")["records"]["best"]), 50)

    def test_score_icons(self):
        self.assertEqual(score_icon(100.5), "sssp")
        self.assertEqual(score_icon(100.0), "sss")
        self.assertEqual(score_icon(99.5), "ssp")
        self.assertEqual(score_icon(85.0), "a")

    def test_rejects_unsupported_region(self):
        with self.assertRaises(ValueError):
            build_session_image_payload([], 0, "cn")

    def test_image_response_mime_and_bytes(self):
        class Response:
            ok = True
            content = b"image-bytes"
            headers = {"content-type": "image/png"}
            def raise_for_status(self): pass
        with patch("src.network.requests.Session.post", return_value=Response()):
            self.assertEqual(request_session_image({}), (b"image-bytes", "image/png", "png"))

if __name__ == "__main__":
    unittest.main()
