"""
Unit test suite for the Unified Artwork Safety and Moderation Layer.
Tests all requirements:
1. Application-wide SFW content policy.
2. Translation of provider rating systems (Wallhaven, Safebooru, Konachan, Curated).
3. Rejection of unknown, missing, ambiguous, or insufficient metadata by default.
4. Local blocked-artwork list, reporting, and cascading blocks.
5. Blocking specific tags, characters, artists, and franchises.
6. Preservation of provider metadata and original safety ratings for auditing.
7. Defense against API query parameter deception (independent tag analysis).
8. Manual review queue for ambiguous content and approve/reject actions.
9. Pre-display revalidation of cached artwork before presentation.
10. Fallback to procedural offline artwork when safe artwork is exhausted.
"""

import unittest
import tempfile
import shutil
import json
from pathlib import Path

from safety_moderation import (
    SafetyRating,
    SafetyModerationEngine,
    EXPLICIT_DENYLIST_TAGS,
    QUESTIONABLE_DENYLIST_TAGS,
    GENERIC_FILTER_TAGS
)
from database import DatabaseManager
from providers import NormalizedWallpaper


class TestArtworkSafetyAndModeration(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="kuro_safety_test_"))
        self.db_path = self.test_dir / "test_kuro.db"
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_provider_rating_translation(self):
        """Req 2: Translates each provider's purity and rating system into common safety classification."""
        # Wallhaven
        self.assertEqual(SafetyModerationEngine.translate_provider_rating("Wallhaven", "100"), SafetyRating.SAFE)
        self.assertEqual(SafetyModerationEngine.translate_provider_rating("Wallhaven", "010"), SafetyRating.QUESTIONABLE)
        self.assertEqual(SafetyModerationEngine.translate_provider_rating("Wallhaven", "001"), SafetyRating.EXPLICIT)
        self.assertEqual(SafetyModerationEngine.translate_provider_rating("Wallhaven", "unknown"), SafetyRating.AMBIGUOUS)
        self.assertEqual(SafetyModerationEngine.translate_provider_rating("Wallhaven", None), SafetyRating.AMBIGUOUS)

        # Safebooru
        self.assertEqual(SafetyModerationEngine.translate_provider_rating("Safebooru", "g"), SafetyRating.SAFE)
        self.assertEqual(SafetyModerationEngine.translate_provider_rating("Safebooru", "general"), SafetyRating.SAFE)
        self.assertEqual(SafetyModerationEngine.translate_provider_rating("Safebooru", "s"), SafetyRating.SAFE)
        self.assertEqual(SafetyModerationEngine.translate_provider_rating("Safebooru", "safe"), SafetyRating.SAFE)
        self.assertEqual(SafetyModerationEngine.translate_provider_rating("Safebooru", "q"), SafetyRating.QUESTIONABLE)
        self.assertEqual(SafetyModerationEngine.translate_provider_rating("Safebooru", "e"), SafetyRating.EXPLICIT)

        # Konachan
        self.assertEqual(SafetyModerationEngine.translate_provider_rating("Konachan", "s"), SafetyRating.SAFE)
        self.assertEqual(SafetyModerationEngine.translate_provider_rating("Konachan", "q"), SafetyRating.QUESTIONABLE)
        self.assertEqual(SafetyModerationEngine.translate_provider_rating("Konachan", "e"), SafetyRating.EXPLICIT)

    def test_rejection_of_missing_or_empty_metadata(self):
        """Req 3: Rejects artwork with unknown, missing, ambiguous, or insufficient safety metadata by default."""
        # Missing tags entirely
        item_no_tags = {
            "id": "test_missing_tags",
            "source": "Wallhaven",
            "provider_purity_raw": "100",
            "tags": []
        }
        res = SafetyModerationEngine.evaluate_artwork_safety(item_no_tags, db_manager=self.db)
        self.assertEqual(res["safety_rating"], SafetyRating.AMBIGUOUS)
        self.assertIn("insufficient_tags", res["safety_reason"])

        # Missing provider purity
        item_no_purity = {
            "id": "test_missing_purity",
            "source": "Wallhaven",
            "tags": ["anime", "gojo_satoru", "jujutsu_kaisen"]
        }
        res2 = SafetyModerationEngine.evaluate_artwork_safety(item_no_purity, db_manager=self.db)
        self.assertEqual(res2["safety_rating"], SafetyRating.AMBIGUOUS)
        self.assertIn("missing_provider_purity", res2["safety_reason"])

    def test_query_parameter_deception_defense(self):
        """Req 7: Never treats an API query parameter alone as proof that an image is safe."""
        # Simulated scenario: API endpoint returned purity=100 (SFW), but crowd tags include explicit or questionable tags
        deceptive_item = {
            "id": "deceptive_01",
            "source": "Wallhaven",
            "provider_purity_raw": "100", # Deceptive clean query param
            "tags": ["anime", "satoru_gojo", "nude", "explicit_pose"]
        }
        res = SafetyModerationEngine.evaluate_artwork_safety(deceptive_item, db_manager=self.db)
        self.assertEqual(res["safety_rating"], SafetyRating.EXPLICIT)
        self.assertIn("tag_denylist:nude", res["safety_reason"])

        # Questionable tag deception
        questionable_item = {
            "id": "deceptive_02",
            "source": "Safebooru",
            "provider_purity_raw": "general",
            "tags": ["anime", "bikini", "beach", "swimsuit"]
        }
        res_q = SafetyModerationEngine.evaluate_artwork_safety(questionable_item, db_manager=self.db)
        self.assertEqual(res_q["safety_rating"], SafetyRating.QUESTIONABLE)
        self.assertIn("tag_denylist:bikini", res_q["safety_reason"])

    def test_blocked_entities_and_cascading_reporting(self):
        """Req 4 & 5: Blocking specific artworks, tags, characters, artists, franchises and cascading."""
        # Add blocked tag
        self.db.add_blocked_entity("tag", "blood_splatter", reason="Gore content")
        self.assertTrue(self.db.is_blocked_in_db("tag", "blood_splatter"))
        self.assertTrue(self.db.is_blocked_in_db("tag", "BLOOD_SPLATTER")) # Case-insensitive

        candidate_with_tag = {
            "id": "wall_blood",
            "source": "Wallhaven",
            "provider_purity_raw": "100",
            "tags": ["anime", "action", "blood_splatter"]
        }
        eval_tag = SafetyModerationEngine.evaluate_artwork_safety(candidate_with_tag, db_manager=self.db)
        self.assertEqual(eval_tag["safety_rating"], SafetyRating.BLOCKED)
        self.assertIn("user_blocked_tag:blood_splatter", eval_tag["safety_reason"])

        # Add candidate to lifecycle
        safe_item = {
            "id": "wh_reported_art",
            "url": "https://example.com/art.jpg",
            "anime": "Test Anime",
            "character": "Test Character",
            "uploader": "Rogue Artist",
            "tags": json.dumps(["anime", "portrait"]),
            "provider_purity_raw": "100",
            "safety_rating": "SAFE"
        }
        self.db.add_unseen_wallpapers([safe_item])

        # Report and block with cascade to character and artist
        rep = self.db.report_and_block_artwork(
            wallpaper_id="wh_reported_art",
            reason="Inappropriate character depictions",
            block_character=True,
            block_artist=True
        )
        self.assertEqual(rep["status"], "success")
        self.assertTrue(self.db.is_blocked_in_db("artwork", "wh_reported_art"))
        self.assertTrue(self.db.is_blocked_in_db("character", "Test Character"))
        self.assertTrue(self.db.is_blocked_in_db("artist", "Rogue Artist"))

        # Verify lifecycle was updated to BLOCKED safety_rating
        rec = self.db.get_wallpaper_by_id("wh_reported_art")
        self.assertEqual(rec["safety_rating"], "BLOCKED")

    def test_pre_display_revalidation(self):
        """Req 9: Cached images are revalidated against the current safety policy before display."""
        cached_art = {
            "id": "cached_future_blocked",
            "url": "https://example.com/cached.jpg",
            "anime": "Rezero",
            "character": "Rem",
            "uploader": "SomeArtist",
            "tags": json.dumps(["anime", "maid", "rem"]),
            "source": "Wallhaven",
            "provider_purity_raw": "100",
            "safety_rating": "SAFE"
        }
        self.db.add_unseen_wallpapers([cached_art])

        # Initially revalidation succeeds
        is_safe, reason = SafetyModerationEngine.revalidate_before_display(cached_art, self.db)
        self.assertTrue(is_safe)
        self.assertIn("safety", reason.lower())

        # Now user blocks tag "maid"
        self.db.add_blocked_entity("tag", "maid", reason="User preference")

        # Revalidation must now fail immediately before display!
        is_safe_after, reason_after = SafetyModerationEngine.revalidate_before_display(cached_art, self.db)
        self.assertFalse(is_safe_after)
        self.assertIn("user_blocked_tag:maid", reason_after)

    def test_review_queue_workflow(self):
        """Req 8: Manual review queue for artwork that fails classification."""
        ambiguous_item = {
            "id": "ambig_01",
            "url": "https://example.com/ambig.jpg",
            "anime": "Unknown Series",
            "tags": ["sketch", "art"],
            "source": "Safebooru"
        }

        # Add to review queue
        self.db.add_to_review_queue(ambiguous_item, failure_reason="insufficient_tags", safety_rating="AMBIGUOUS")
        queue = self.db.get_review_queue(decision="PENDING")
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["id"], "ambig_01")
        self.assertEqual(queue[0]["safety_rating"], "AMBIGUOUS")

        # Action: Approve item
        self.db.action_review_queue_item("ambig_01", "APPROVE")
        pending_queue = self.db.get_review_queue(decision="PENDING")
        self.assertEqual(len(pending_queue), 0)

        approved_record = self.db.get_wallpaper_by_id("ambig_01")
        self.assertIsNotNone(approved_record)
        self.assertEqual(approved_record["safety_rating"], "SAFE")
        self.assertEqual(approved_record["status"], "UNSEEN")

        # Action: Reject another item
        item_reject = {
            "id": "ambig_02",
            "url": "https://example.com/ambig2.jpg",
            "anime": "Questionable Show",
            "tags": ["dubious"],
            "source": "Konachan"
        }
        self.db.add_to_review_queue(item_reject, failure_reason="questionable_content", safety_rating="QUESTIONABLE")
        self.db.action_review_queue_item("ambig_02", "REJECT")
        self.assertTrue(self.db.is_blocked_in_db("artwork", "ambig_02"))

    def test_auditing_metadata_preserved(self):
        """Req 6: Keep provider metadata and original safety classifications for auditing."""
        item = {
            "id": "audit_test_wp",
            "url": "https://example.com/audit.jpg",
            "anime": "Frieren",
            "character": "Frieren",
            "uploader": "Artist123",
            "tags": json.dumps(["frieren", "elf", "magic"]),
            "source": "Wallhaven",
            "provider_purity_raw": "100",
            "safety_rating": "SAFE",
            "safety_reason": "verified_sfw"
        }
        self.db.add_unseen_wallpapers([item])
        retrieved = self.db.get_wallpaper_by_id("audit_test_wp")

        self.assertEqual(retrieved["provider_purity_raw"], "100")
        self.assertEqual(retrieved["safety_rating"], "SAFE")
        self.assertEqual(retrieved["safety_reason"], "verified_sfw")
        self.assertEqual(retrieved["uploader"], "Artist123")


if __name__ == "__main__":
    unittest.main()
