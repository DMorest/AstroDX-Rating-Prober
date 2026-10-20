import sys, unittest, zlib, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.cache_parser import decode_cache_bytes, parse_cache
from src.rating import chart_rating, select_b50, dx_star_count, rating_tier, rating_tier_for_slots, is_utage_record
from src.catalog import match_records, apply_manual_matches, score_signature, normalize_fetched_catalog
from unittest.mock import patch
from src.catalog_sources import fetch_saltmeta

class CoreTests(unittest.TestCase):
    def test_raw_deflate(self):
        payload = json.dumps({"version": 4, "level_metadata": {"Song": {"title": "Song", "difficulties": [{"id": 5, "value": "13", "stats": {"achievementRate": 99.5}}]}}}).encode()
        packed = zlib.compressobj(wbits=-zlib.MAX_WBITS)
        raw = packed.compress(payload) + packed.flush()
        self.assertEqual(decode_cache_bytes(raw)["version"], 4)

    def test_rating_cap(self):
        self.assertEqual(chart_rating(13.0, 100.5), 292)
        self.assertEqual(chart_rating(13.0, 0), 0)

    def test_official_dx_star_thresholds(self):
        # 100 notes => 300 theoretical DX points; official cutoffs: 85/90/93/95/97%.
        self.assertEqual(dx_star_count(254, 100), 0)
        self.assertEqual(dx_star_count(255, 100), 1)
        self.assertEqual(dx_star_count(270, 100), 2)
        self.assertEqual(dx_star_count(279, 100), 3)
        self.assertEqual(dx_star_count(285, 100), 4)
        self.assertEqual(dx_star_count(291, 100), 5)
        self.assertIsNone(dx_star_count(500, 0))

    def test_b50_split(self):
        rows = [{"is_new": False, "rating": 10, "achievement": 99, "dx_score": 0} for _ in range(40)]
        rows += [{"is_new": True, "rating": 20, "achievement": 99, "dx_score": 0} for _ in range(20)]
        old, new = select_b50(rows)
        self.assertEqual((len(old), len(new)), (35, 15))

    def test_version_target_split(self):
        rows = [{"version": "PRiSM", "rating": i, "achievement": 99, "dx_score": 0} for i in range(40)]
        rows += [{"version": "PRiSM PLUS", "rating": 100 + i, "achievement": 99, "dx_score": 0} for i in range(20)]
        old, new = select_b50(rows, mode="split", target_version="PRiSM PLUS")
        self.assertEqual((len(old), len(new)), (35, 15))
        self.assertTrue(all(x["version"] == "PRiSM PLUS" for x in new))

    def test_direct_b50(self):
        rows = [{"rating": i, "achievement": 99, "dx_score": 0} for i in range(60)]
        top, new = select_b50(rows, mode="direct")
        self.assertEqual(len(top), 50)
        self.assertEqual(new, [])
        self.assertEqual(top[0]["rating"], 59)

    def test_utage_prefix_matches_utage_only(self):
        score = {"title": "[宴会]Example Song", "difficulty": "UTAGE", "achievement": 100.0, "dx_score": 300, "cache_key": "song"}
        catalog = [
            {"title": "Example Song", "difficulty": "MASTER", "constant": 13.0, "song_type": "DX", "version": "X"},
            {"title": "Example Song", "difficulty": "UTAGE", "constant": 13.0, "song_type": "UTAGE", "version": "X"},
        ]
        matched, unmatched = match_records([score], catalog)
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["difficulty"], "UTAGE")
        self.assertEqual(unmatched, [])

    def test_title_sd_dx_marker(self):
        score = {"title": "Example Song [DX]", "difficulty": "MASTER", "achievement": 100.0, "dx_score": 500, "cache_key": "song"}
        catalog = [
            {"title": "Example Song", "difficulty": "MASTER", "constant": 13.0, "song_type": "SD", "version": "X"},
            {"title": "Example Song", "difficulty": "MASTER", "constant": 13.5, "song_type": "DX", "version": "X"},
        ]
        matched, unmatched = match_records([score], catalog)
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["song_type"], "DX")
        self.assertEqual(unmatched, [])

    def test_ambiguity_manual_selection(self):
        score = {"title": "Example Song", "difficulty": "MASTER", "achievement": 100.0, "dx_score": 100, "cache_key": "song"}
        catalog = [
            {"title": "Example Song", "difficulty": "MASTER", "constant": 13.0, "song_type": "SD", "version": "X"},
            {"title": "Example Song", "difficulty": "MASTER", "constant": 13.5, "song_type": "DX", "version": "X"},
        ]
        matched, unmatched = match_records([score], catalog)
        self.assertEqual(len(unmatched), 1)
        sig = score_signature(unmatched[0])
        matched, remaining = apply_manual_matches(matched, unmatched, {sig: 1})
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["song_type"], "DX")
        self.assertEqual(remaining, [])

    def test_chart_hash_distinguishes_sd_dx(self):
        score = {"title": "Example Song", "difficulty": "MASTER", "achievement": 100.0, "dx_score": 500, "cache_key": "song", "chart_hash": "987"}
        catalog = [
            {"title": "Example Song", "difficulty": "MASTER", "constant": 13.0, "song_type": "SD", "version": "X", "chart_hash": "123"},
            {"title": "Example Song", "difficulty": "MASTER", "constant": 13.5, "song_type": "DX", "version": "X", "chart_hash": "987"},
        ]
        matched, unmatched = match_records([score], catalog)
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["song_type"], "DX")
        self.assertEqual(matched[0]["match_status"], "谱面 hash 精确匹配")
        self.assertEqual(unmatched, [])

    def test_display_level_distinguishes_sd_dx_variants(self):
        # Real AstroDX cache behavior: MASTER level 14 must not match a MASTER 13+ chart.
        score = {
            "title": "Calamity Fortune", "difficulty": "MASTER", "difficulty_id": 5,
            "level_text": "14", "achievement": 98.6806417, "dx_score": 2839,
            "notes": 1142, "cache_key": "Calamity Fortune", "chart_hash": "cache-hash",
        }
        catalog = [
            {"title": "Calamity Fortune", "difficulty": "MASTER", "constant": 13.6,
             "level_text": "13+", "song_type": "DX", "version": "maimai でらっくす", "total_notes": 1100},
            {"title": "Calamity Fortune", "difficulty": "MASTER", "constant": 14.2,
             "level_text": "14", "song_type": "SD", "version": "MURASAKi PLUS", "total_notes": 1142},
        ]
        matched, unmatched = match_records([score], catalog)
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["song_type"], "SD")
        self.assertEqual(matched[0]["constant"], 14.2)
        self.assertEqual(matched[0]["match_status"], "已匹配")
        self.assertEqual(unmatched, [])

    def test_note_count_can_break_same_display_level_tie(self):
        score = {"title": "Example Song", "difficulty": "MASTER", "level_text": "14",
                 "achievement": 99.0, "dx_score": 100, "notes": 1000, "cache_key": "song"}
        catalog = [
            {"title": "Example Song", "difficulty": "MASTER", "constant": 14.1,
             "level_text": "14", "song_type": "SD", "version": "old", "total_notes": 900},
            {"title": "Example Song", "difficulty": "MASTER", "constant": 14.2,
             "level_text": "14", "song_type": "DX", "version": "new", "total_notes": 1000},
        ]
        matched, unmatched = match_records([score], catalog)
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["song_type"], "DX")
        self.assertEqual(unmatched, [])

    def test_saltmeta_keeps_display_level_and_note_count(self):
        payload = {
            "musics": [{
                "id": 123, "title": "Example Song", "artist": "Artist", "category": "Game",
                "charts": [{
                    "difficulty": 3, "type": "dx", "level": "13+", "internalLevel": 13.6,
                    "noteCounts": {"tap": 500, "hold": 100, "slide": 200, "touch": 100, "break": 242, "total": 1142},
                    "regions": {"jp": {"internalLevel": 13.6, "version": "maimai でらっくす"}},
                }],
            }]
        }
        with patch("src.catalog_sources._get_json", return_value=payload):
            rows = fetch_saltmeta("jp")
        normalized = normalize_fetched_catalog(rows)
        self.assertEqual(normalized[0]["level_text"], "13+")
        self.assertEqual(normalized[0]["total_notes"], 1142)


    def test_typographic_apostrophe_title_matches(self):
        # Cache can use curly apostrophes while online catalogues use straight ones.
        score = {"title": "Don’t Fight The Music", "difficulty": "MASTER", "level_text": "14",
                 "achievement": 100.3821, "dx_score": 2946, "notes": 1089, "cache_key": "song"}
        catalog = [{"title": "Don't Fight The Music", "difficulty": "MASTER", "constant": 14.0,
                    "level_text": "14", "song_type": "DX", "version": "DX", "total_notes": 1089}]
        matched, unmatched = match_records([score], catalog)
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["title"], "Don't Fight The Music")
        self.assertEqual(unmatched, [])

    def test_level_conflict_keeps_candidates_for_manual_selection(self):
        score = {"title": "Example Song", "difficulty": "MASTER", "level_text": "14",
                 "achievement": 99.0, "dx_score": 500, "cache_key": "song"}
        catalog = [{"title": "Example Song", "difficulty": "MASTER", "constant": 13.6,
                    "level_text": "13+", "song_type": "DX", "version": "DX"}]
        matched, unmatched = match_records([score], catalog)
        self.assertEqual(matched, [])
        self.assertEqual(len(unmatched), 1)
        self.assertEqual(len(unmatched[0]["candidates"]), 1)
        sig = score_signature(unmatched[0])
        matched, remaining = apply_manual_matches(matched, unmatched, {sig: 0})
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["match_status"], "手动匹配")
        self.assertEqual(remaining, [])

    def test_similar_title_candidates_are_manual_only(self):
        score = {"title": "Don’t Fight The Musi", "difficulty": "MASTER", "level_text": "14",
                 "achievement": 99.0, "dx_score": 500, "cache_key": "song"}
        catalog = [{"title": "Don't Fight The Music", "difficulty": "MASTER", "constant": 14.0,
                    "level_text": "14", "song_type": "DX", "version": "DX"}]
        matched, unmatched = match_records([score], catalog)
        self.assertEqual(matched, [])
        self.assertEqual(len(unmatched), 1)
        self.assertEqual(len(unmatched[0]["candidates"]), 1)
        self.assertIn("需手动确认", unmatched[0]["match_status"])


    def test_rating_tier_colors(self):
        self.assertEqual(rating_tier(15000), ("rainbow", "彩框"))
        self.assertEqual(rating_tier(14500), ("platinum", "白金"))
        self.assertEqual(rating_tier(14000), ("gold", "金色"))
        self.assertEqual(rating_tier(13999), ("silver", "银色"))
        self.assertEqual(rating_tier(13000), ("silver", "银色"))
        self.assertEqual(rating_tier(999), ("white", "白色"))

    def test_b35_b15_scaled_color_thresholds(self):
        self.assertEqual(rating_tier_for_slots(10500, 35), ("rainbow", "彩框"))
        self.assertEqual(rating_tier_for_slots(10150, 35), ("platinum", "白金"))
        self.assertEqual(rating_tier_for_slots(4500, 15), ("rainbow", "彩框"))
        self.assertEqual(rating_tier_for_slots(4350, 15), ("platinum", "白金"))
        self.assertEqual(rating_tier_for_slots(9800, 35), ("gold", "金色"))
        self.assertEqual(rating_tier_for_slots(4200, 15), ("gold", "金色"))

    def test_utage_charts_are_excluded_from_rating_selection(self):
        rows = [
            {"title": "Regular Song", "difficulty": "MASTER", "rating": 200, "version": "Old"},
            {"title": "[宴会場] Fun Song", "difficulty": "UTAGE", "difficulty_id": 7, "rating": 9999, "version": "Old"},
            {"title": "UTAGE song type", "difficulty": "MASTER", "song_type": "UTAGE", "rating": 9999, "version": "New"},
        ]
        old, new = select_b50(rows, mode="split", target_version="New")
        self.assertEqual([r["title"] for r in old], ["Regular Song"])
        self.assertEqual(new, [])
        direct, _ = select_b50(rows, mode="direct")
        self.assertEqual([r["title"] for r in direct], ["Regular Song"])
        self.assertTrue(is_utage_record(rows[1]))
        self.assertTrue(is_utage_record(rows[2]))

if __name__ == "__main__":
    unittest.main()
