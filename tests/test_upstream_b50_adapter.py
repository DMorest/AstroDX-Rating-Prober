import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.rating import DX_STAR_COLORS, achievement_rank, achievement_rank_color
from src.upstream_b50_adapter import (
    _difficulty_index,
    _music_list_for,
    _patch_upstream_source,
    _rank_label,
    _record_to_chart_info,
    _ensure_upstream_source,
    validate_static_dir,
)


class UpstreamB50AdapterTests(unittest.TestCase):
    def test_dx_star_tiers_use_green_to_gold_palette(self):
        self.assertEqual(DX_STAR_COLORS, {
            1: "#409d0e", 2: "#79c11a", 3: "#dc4916", 4: "#ef6f1b", 5: "#ed9a18",
        })

    def test_rank_names_match_upstream_icon_mapping(self):
        self.assertEqual(_rank_label(100.5), "sssp")
        self.assertEqual(_rank_label(99.5), "ssp")
        self.assertEqual(_rank_label(98.0), "sp")
        self.assertEqual(_rank_label(94.0), "AAA")
        self.assertEqual(_rank_label(72.0), "bb")

    def test_achievement_rank_thresholds_and_colors(self):
        samples = [
            (100.5, "SSS+", "rainbow"), (100.0, "SSS", "rainbow"),
            (99.5, "SS+", "gold"), (99.0, "SS", "gold"),
            (98.0, "S+", "gold"), (97.0, "S", "gold"),
            (94.0, "AAA", "red"), (90.0, "AA", "red"),
            (80.0, "A", "red"), (75.0, "BBB", "blue"),
            (70.0, "BB", "blue"), (60.0, "B", "blue"),
            (50.0, "C", "green"), (49.999, "D", "gray"),
        ]
        for achievement, label, color in samples:
            with self.subTest(achievement=achievement):
                self.assertEqual(achievement_rank(achievement), label)
                self.assertEqual(achievement_rank_color(achievement), color)

    def test_upstream_source_is_prepared_from_local_vendor_without_network(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vendor = root / "vendor" / "maimai-b50-image-generator-1.2.1"
            (vendor / "libs").mkdir(parents=True)
            for relative in ("libs/__init__.py", "libs/consts.py", "libs/image.py", "libs/tools.py", "LICENSE"):
                file_path = vendor / relative
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text("# local fixture\n", encoding="utf-8")
            target = root / "data" / "upstream_b50" / "v1.2.1"
            with patch("src.upstream_b50_adapter.ROOT", root), \
                 patch("src.upstream_b50_adapter.LOCAL_SOURCE_DIR", root / "vendor" / "maimai-b50-image-generator"), \
                 patch("src.upstream_b50_adapter.VENDOR_DIR", target):
                resolved = _ensure_upstream_source()
            self.assertEqual(resolved, target)
            self.assertTrue((target / "libs" / "image.py").is_file())
            self.assertTrue((target / "UPSTREAM_SOURCE.json").is_file())

    def test_difficulty_and_local_record_conversion(self):
        self.assertEqual(_difficulty_index({"difficulty": "Re:MASTER"}), 4)
        record = {
            "title": "Test Song", "difficulty": "MASTER", "constant": 14.0,
            "achievement": 100.1234, "dx_score": 1200, "rating": 300,
            "song_id": "12345", "song_type": "DX", "notes": 400,
        }
        item = _record_to_chart_info(record, 12345)
        self.assertEqual(item.level_index, 3)
        self.assertEqual(item.song_id, 12345)
        self.assertEqual(item.type, "DX")
        self.assertEqual(item.achievements, 100.1234)

    def test_local_music_metadata_supplies_note_count_without_api(self):
        old = [{"title": "Old", "difficulty": "MASTER", "constant": 13.0,
                "achievement": 99.0, "dx_score": 1100, "rating": 250,
                "song_id": "100", "song_type": "SD", "notes": 500}]
        new = [{"title": "New", "difficulty": "EXPERT", "constant": 12.0,
                "achievement": 98.0, "dx_score": 800, "rating": 200,
                "song_id": "200", "song_type": "DX", "notes": 350}]
        sd, dx, music_list = _music_list_for(old + new, old, new)
        self.assertEqual(len(sd), 1)
        self.assertEqual(len(dx), 1)
        self.assertEqual(sum(music_list.by_id("100").charts[3].notes), 500)
        self.assertEqual(sum(music_list.by_id("200").charts[2].notes), 350)

    def test_renderer_patching_is_syntax_valid_and_repeatable(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            libs = source / "libs"
            libs.mkdir()
            (libs / "__init__.py").write_text("# source package\n", encoding="utf-8")
            (libs / "consts.py").write_text(
                "from pathlib import Path\nimport os\nroot = Path(__file__).parent.parent\n"
                "static: Path = root / 'static'\n"
                "HAN: Path = static / 'ResourceHanRoundedCN-Bold.ttf'\n"
                "TORUS: Path = static / 'Torus SemiBold.otf'\n",
                encoding="utf-8",
            )
            (libs / "image.py").write_text(
                "from typing import List, Union, Tuple\n"
                "from .models import ChartInfo, UserInfo\n"
                "from .api import MusicList\nfrom .config import Config\n"
                "class X:\n"
                "    def draw(self, config):\n"
                "        self._to.draw(\n"
                "            570, 172, 17,\n"
                "            f'B35: {sdrating} + B15: {dxrating} = {self.rating}',\n"
                "            (0, 0, 0, 255), 'mm', 3, (255, 255, 255, 255)\n"
                "        )\n",
                encoding="utf-8",
            )
            (libs / "tools.py").write_text("# unused for patch test\n", encoding="utf-8")
            _patch_upstream_source(source)
            _patch_upstream_source(source)
            consts = (libs / "consts.py").read_text(encoding="utf-8")
            image = (libs / "image.py").read_text(encoding="utf-8")
            self.assertIn("ASTRODX_B50_STATIC", consts)
            self.assertIn("rating_summary = config.get('rating_summary')", image)
            self.assertNotIn(r"ChartInfo = Any\n", image)
            compile(consts, str(libs / "consts.py"), "exec")
            compile(image, str(libs / "image.py"), "exec")

    def test_static_dir_reports_missing_assets_instead_of_throwing(self):
        valid, description = validate_static_dir("/definitely/not/a/real/static/folder")
        self.assertFalse(valid)
        self.assertIn("static", description)


if __name__ == "__main__":
    unittest.main()
