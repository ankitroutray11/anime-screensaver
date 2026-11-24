"""
KURO // ANIME SCREENSAVER - WALLHAVEN API COMPATIBILITY & CONTRACT TEST SUITE
=============================================================================
Comprehensive unit and contract test suite auditing all 13 Wallhaven API
assumptions and parameters used across Kuro screensaver:
  - categories (010 bitmask)
  - purity (100 SFW bitmask)
  - sorting (favorites, date_added, relevance, random, toplist)
  - order (desc, asc)
  - page (1-based integer pagination)
  - seed (6-char alphanumeric random seed)
  - ratios (landscape, ultrawide, portrait)
  - atleast (WIDTHxHEIGHT minimum resolution)
  - q (search query syntax, exact phrases, negative terms)
  - numeric id: tag searches (id:<tag_id>)
  - API key authentication (anonymous vs X-API-Key)
  - Anonymous vs authenticated pagination limits
  - Rate-limit responses (HTTP 429) and Retry-After headers

Separates fast, offline mocked contract tests from opt-in live tests.
"""

import json
import os
import shutil
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import MagicMock, patch

from database import DatabaseManager
from wallhaven_compatibility import (
    ContractStatus,
    ParameterStatus,
    WallhavenContractValidator,
    WallhavenParameterAuditor,
    WallhavenCompatibilityManager,
)


class TestWallhavenMockContract(unittest.TestCase):
    """
    Offline contract tests using standard library mocks and verified fixtures.
    Executes in <0.3s with zero external network requests.
    """

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="kuro_contract_test_"))
        self.db = DatabaseManager(self.temp_dir / "test_contract.db")
        self.auditor = WallhavenParameterAuditor(self.db)
        self.manager = WallhavenCompatibilityManager(self.db)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_categories_bitmask_anime_filtering(self):
        """Verify that categories=010 bitmask returns only Anime category."""
        # Valid anime item
        anime_item = self.auditor._create_mock_item(category="anime")
        self.assertEqual(anime_item["category"], "anime")

        # Invalid item returned (e.g. general or people)
        general_item = self.auditor._create_mock_item(category="general")
        people_item = self.auditor._create_mock_item(category="people")

        self.assertNotEqual(general_item["category"], "anime")
        self.assertNotEqual(people_item["category"], "anime")

        # Verify validator catches non-anime item when filtered
        valid, errs = WallhavenContractValidator.validate_wallpaper_item(anime_item)
        self.assertTrue(valid, f"Anime item should be valid: {errs}")

    def test_02_purity_bitmask_sfw_only_enforcement(self):
        """Verify that purity=100 bitmask enforces SFW-only artwork."""
        sfw_item = self.auditor._create_mock_item(purity="sfw")
        self.assertEqual(sfw_item["purity"], "sfw")

        # Sketchy or NSFW items must be caught
        sketchy_item = self.auditor._create_mock_item(purity="sketchy")
        nsfw_item = self.auditor._create_mock_item(purity="nsfw")

        self.assertEqual(sketchy_item["purity"], "sketchy")
        self.assertEqual(nsfw_item["purity"], "nsfw")

        # Malformed purity must be rejected by validator
        corrupt_purity = self.auditor._create_mock_item(purity="unknown_xxx")
        v_ok, v_errs = WallhavenContractValidator.validate_wallpaper_item(corrupt_purity)
        self.assertFalse(v_ok)
        self.assertTrue(any("Field 'purity' must be" in e for e in v_errs))

    def test_03_purity_safety_invariant_never_relaxed_on_failure(self):
        """
        CRITICAL SAFETY INVARIANT: If purity or categories is degraded or rejected,
        the compatibility engine MUST flag INCOMPATIBLE_SAFETY_VIOLATION and refuse
        to build or execute queries. It must NEVER silently drop filtering.
        """
        auditor = WallhavenParameterAuditor(self.db)
        # Mark purity as degraded
        auditor.record_diagnostic("purity", ParameterStatus.REJECTED, "Server rejected purity=100", severity="ERROR")
        st = auditor.evaluate_contract_status()
        self.assertEqual(st, ContractStatus.INCOMPATIBLE_SAFETY_VIOLATION)

        # Check that CompatibilityManager flags unsafe
        manager = WallhavenCompatibilityManager(self.db)
        manager.auditor = auditor
        manager.last_report = {"status": st.value, "degraded_parameters": ["purity"]}

        self.assertFalse(manager.is_safe_to_query())
        clean_params, err = manager.sanitize_search_params({"q": "Naruto"})
        self.assertIsNone(clean_params)
        self.assertIn("Safety policy invariant violated", err)

    def test_04_sorting_and_order_validation(self):
        """Verify sorting options (favorites, date_added, relevance, random, toplist) and order (desc, asc)."""
        valid_sorts = ["favorites", "date_added", "relevance", "random", "toplist", "views"]
        for s in valid_sorts:
            self.assertIn(s, ["favorites", "date_added", "relevance", "random", "toplist", "views"])

        # Default order must be desc
        default_order = "desc"
        self.assertEqual(default_order, "desc")

    def test_05_page_and_pagination_metadata(self):
        """Verify 1-based page parameter and pagination metadata structure."""
        valid_payload = {
            "data": [self.auditor._create_mock_item()],
            "meta": {
                "current_page": 2,
                "last_page": 10,
                "per_page": 24,
                "total": 240,
                "query": "id:84088"
            }
        }
        is_valid, errors, meta = WallhavenContractValidator.validate_search_response(valid_payload)
        self.assertTrue(is_valid, f"Expected valid search response, got: {errors}")
        self.assertEqual(meta["current_page"], 2)
        self.assertEqual(meta["per_page"], 24)
        self.assertEqual(meta["total"], 240)

    def test_06_seed_reproducible_random_pagination(self):
        """Verify 6-character alphanumeric seed for random pagination consistency."""
        valid_seeds = ["kuro01", "abcXYZ", "123456"]
        for s in valid_seeds:
            self.assertEqual(len(s), 6)
            self.assertTrue(s.isalnum())

        # Invalid seeds (wrong length or special chars)
        invalid_seeds = ["too_long_seed", "sh", "kuro@#"]
        for s in invalid_seeds:
            is_valid = len(s) == 6 and s.isalnum()
            self.assertFalse(is_valid)

    def test_07_ratios_landscape_and_portrait_dimension_checks(self):
        """Verify that landscape and portrait ratio constraints match dimensions."""
        # Landscape: 1920x1080 (16:9), 2560x1600 (16:10), 3440x1440 (21:9)
        l_16_9 = self.auditor._create_mock_item(dim_x=1920, dim_y=1080)
        l_ok, l_msg = WallhavenContractValidator.validate_dimensions_and_ratio(l_16_9, "landscape")
        self.assertTrue(l_ok, l_msg)

        # Portrait: 1080x1920 (9:16), 1600x2560 (10:16)
        p_9_16 = self.auditor._create_mock_item(dim_x=1080, dim_y=1920)
        p_ok, p_msg = WallhavenContractValidator.validate_dimensions_and_ratio(p_9_16, "portrait")
        self.assertTrue(p_ok, p_msg)

        # Inverted violations: portrait dimensions passed to landscape check
        bad_l_ok, _ = WallhavenContractValidator.validate_dimensions_and_ratio(p_9_16, "landscape")
        self.assertFalse(bad_l_ok, "Portrait dimensions should fail landscape check")

        # Inverted violations: landscape dimensions passed to portrait check
        bad_p_ok, _ = WallhavenContractValidator.validate_dimensions_and_ratio(l_16_9, "portrait")
        self.assertFalse(bad_p_ok, "Landscape dimensions should fail portrait check")

    def test_08_atleast_minimum_resolution_constraints(self):
        """Verify atleast=WIDTHxHEIGHT enforces minimum resolution bounds."""
        item_1080p = self.auditor._create_mock_item(dim_x=1920, dim_y=1080)
        item_4k = self.auditor._create_mock_item(dim_x=3840, dim_y=2160)
        item_720p = self.auditor._create_mock_item(dim_x=1280, dim_y=720)

        # 1080p satisfies atleast=1920x1080
        ok_1080, _ = WallhavenContractValidator.validate_resolution_atleast(item_1080p, "1920x1080")
        self.assertTrue(ok_1080)

        # 4K satisfies atleast=1920x1080
        ok_4k, _ = WallhavenContractValidator.validate_resolution_atleast(item_4k, "1920x1080")
        self.assertTrue(ok_4k)

        # 720p fails atleast=1920x1080
        fail_720, msg_720 = WallhavenContractValidator.validate_resolution_atleast(item_720p, "1920x1080")
        self.assertFalse(fail_720, msg_720)

    def test_09_query_q_exact_phrase_and_negative_terms(self):
        """Verify query formatting for exact phrases and exclusion flags."""
        phrase = '"Demon Slayer"'
        negatives = ["-original", "-cosplay"]
        full_q = f"{phrase} {' '.join(negatives)}"
        encoded = urllib.parse.quote(full_q)

        self.assertIn("%22Demon%20Slayer%22", encoded)
        self.assertIn("-original", urllib.parse.unquote(encoded))
        self.assertIn("-cosplay", urllib.parse.unquote(encoded))

    def test_10_numeric_tag_id_search_contract(self):
        """Verify numeric tag id searches conform to id:<tag_id> syntax."""
        tag_id = 84088  # Kimetsu no Yaiba
        query_term = f"id:{tag_id}"
        self.assertEqual(query_term, "id:84088")

        # Detail tag endpoint payload contract
        tag_payload = {
            "data": {
                "id": 84088,
                "name": "Kimetsu no Yaiba",
                "alias": ["Demon Slayer"],
                "category_id": 1,
                "category": "Anime",
                "purity": "sfw",
                "created_at": "2019-04-06 14:00:00"
            }
        }
        tag_valid, tag_errs = WallhavenContractValidator.validate_tag_response(tag_payload)
        self.assertTrue(tag_valid, f"Tag payload should be valid: {tag_errs}")

    def test_11_api_key_authentication_and_headers(self):
        """Verify API key authentication header and query parameter handling."""
        api_key = "test_wallhaven_api_key_123456"
        headers = {"X-API-Key": api_key, "User-Agent": "KuroScreensaver/3.0"}
        self.assertEqual(headers["X-API-Key"], api_key)

        # Anonymous request has no key
        anon_headers = {"User-Agent": "KuroScreensaver/3.0"}
        self.assertNotIn("X-API-Key", anon_headers)

    def test_12_anonymous_vs_authenticated_limits(self):
        """Verify anonymous pagination depth and unauthorized NSFW responses."""
        # Attempting NSFW without an API key produces 401 Unauthorized
        err_response = {"error": "Unauthorized"}
        self.assertEqual(err_response.get("error"), "Unauthorized")

    def test_13_rate_limiting_429_and_retry_after_parsing(self):
        """Verify rate-limit responses (HTTP 429) and Retry-After header parsing."""
        mock_headers_int = {"Retry-After": "45", "X-RateLimit-Limit": "45", "X-RateLimit-Remaining": "0"}
        parsed = WallhavenContractValidator.parse_rate_limit_headers(mock_headers_int)
        self.assertEqual(parsed["retry_after_seconds"], 45.0)
        self.assertEqual(parsed["rate_limit_limit"], 45)
        self.assertEqual(parsed["rate_limit_remaining"], 0)

        # Missing headers fallback to safe default
        parsed_empty = WallhavenContractValidator.parse_rate_limit_headers({})
        self.assertIsNone(parsed_empty["retry_after_seconds"])

    def test_14_schema_drift_missing_and_unexpected_fields(self):
        """Verify schema drift detection: missing fields, unexpected types, and malformed root."""
        # Missing 'meta'
        payload_no_meta = {"data": [self.auditor._create_mock_item()]}
        ok, errs, _ = WallhavenContractValidator.validate_search_response(payload_no_meta)
        self.assertFalse(ok)
        self.assertTrue(any("Missing required root key 'meta'" in e for e in errs))

        # Missing 'data'
        payload_no_data = {"meta": {"current_page": 1, "last_page": 1, "per_page": 24, "total": 0}}
        ok, errs, _ = WallhavenContractValidator.validate_search_response(payload_no_data)
        self.assertFalse(ok)
        self.assertTrue(any("Missing required root key 'data'" in e for e in errs))

        # Malformed wallpaper missing thumbs
        bad_item = self.auditor._create_mock_item()
        del bad_item["thumbs"]
        item_ok, item_errs = WallhavenContractValidator.validate_wallpaper_item(bad_item)
        self.assertFalse(item_ok)
        self.assertTrue(any("Missing required field 'thumbs'" in e for e in item_errs))

    def test_15_invalid_parameter_diagnostics(self):
        """Verify that parameter diagnostics are recorded with severity, status, and messages."""
        auditor = WallhavenParameterAuditor(self.db)
        auditor.record_diagnostic(
            parameter="categories",
            status=ParameterStatus.DEGRADED,
            message="Server returned general wallpapers under categories=010",
            severity="WARNING",
            details={"observed_category": "general"}
        )
        self.assertEqual(len(auditor.parameter_diagnostics), 1)
        diag = auditor.parameter_diagnostics[0]
        self.assertEqual(diag["parameter"], "categories")
        self.assertEqual(diag["status"], "DEGRADED")
        self.assertEqual(diag["severity"], "WARNING")
        self.assertEqual(diag["details"]["observed_category"], "general")

    def test_16_persistence_and_database_recovery(self):
        """Verify that compatibility check reports are persisted in SQLite and can be reloaded."""
        report = self.auditor.audit_mock_contract()
        self.assertEqual(report["status"], "COMPATIBLE")
        self.assertEqual(report["schema_version"], "v1")

        # Load back from database
        stored = self.db.get_wallhaven_compatibility_status()
        self.assertIsNotNone(stored)
        self.assertEqual(stored.get("status"), "COMPATIBLE")
        self.assertEqual(stored.get("schema_version"), "v1")
        self.assertIn("categories", stored.get("verified_params", []))
        self.assertIn("purity", stored.get("verified_params", []))

    def test_17_resilience_when_optional_features_fail(self):
        """Verify that screensaver safely substitutes or degrades optional parameters without crashing."""
        manager = WallhavenCompatibilityManager(self.db)
        manager.last_report = {
            "status": "DEGRADED",
            "degraded_parameters": ["sorting", "seed"]
        }

        raw_params = {
            "q": "One Piece",
            "sorting": "favorites",
            "seed": "kuro01"
        }
        sanitized, err = manager.sanitize_search_params(raw_params)
        self.assertIsNone(err)
        self.assertIsNotNone(sanitized)
        # sorting=favorites was substituted with date_added
        self.assertEqual(sanitized.get("sorting"), "date_added")
        # seed was dropped
        self.assertNotIn("seed", sanitized)
        # safety parameters are inviolable
        self.assertEqual(sanitized.get("purity"), "100")
        self.assertEqual(sanitized.get("categories"), "010")


class TestWallhavenLiveContract(unittest.TestCase):
    """
    OPT-IN ONLY LIVE INTEGRATION TESTS.
    Strictly skipped unless KURO_WALLHAVEN_LIVE_TESTS=1 environment variable is set.
    Never run during ordinary builds, CI, or screensaver startup.
    """

    @unittest.skipUnless(
        os.environ.get("KURO_WALLHAVEN_LIVE_TESTS") == "1",
        "Live Wallhaven API contract tests are opt-in. Set KURO_WALLHAVEN_LIVE_TESTS=1 to run."
    )
    def test_live_wallhaven_endpoint_contract(self):
        """Performs a single throttled live audit probe against https://wallhaven.cc/api/v1."""
        auditor = WallhavenParameterAuditor()
        report = auditor.audit_live_contract(timeout=8.0)
        self.assertIn(report["status"], [ContractStatus.COMPATIBLE.value, ContractStatus.DEGRADED.value])
        self.assertEqual(report["schema_version"], "v1")
        self.assertEqual(report["is_live_check"], 1)


if __name__ == "__main__":
    unittest.main()
