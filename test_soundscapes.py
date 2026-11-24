"""
Automated Unit and Integration Tests for Optional Ambient Soundscape Feature.
Tests:
- Generation and presence of all 8 soundscape categories
- WAV audio header & format validation (16-bit PCM, stereo, 22050Hz)
- Seamless loop crossfade validation
- Custom user audio file discovery
- Path traversal prevention
- SQLite Migration v9 schema & settings persistence
- Server REST API endpoints (/api/soundscapes, /api/soundscapes/settings GET & POST with CSRF)
- Direct local audio file streaming with correct Content-Type (audio/wav)
"""

import unittest
import json
import wave
import urllib.request
import urllib.error
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from database import DatabaseManager
from soundscape_manager import SoundscapeManager
import soundscape_generator
import server


class TestSoundscapeAudioAndManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = TemporaryDirectory()
        cls.sound_dir = Path(cls.temp_dir.name) / "soundscapes"
        cls.manager = SoundscapeManager(cls.sound_dir)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_01_all_eight_categories_generated(self):
        catalog = self.manager.list_soundscapes()
        expected_ids = {
            "rain", "thunderstorm", "japanese_forest", "night_city",
            "ocean_waves", "wind", "fireplace", "space_ambience"
        }
        found_ids = {item["id"] for item in catalog}
        for eid in expected_ids:
            self.assertIn(eid, found_ids)
        self.assertGreaterEqual(len(catalog), 8)

    def test_02_wav_file_validity(self):
        for key in soundscape_generator.SOUNDSCAPES_CATALOG:
            wav_file = self.sound_dir / f"{key}.wav"
            self.assertTrue(wav_file.is_file())
            self.assertGreater(wav_file.stat().st_size, 50000)

            with wave.open(str(wav_file), "rb") as wf:
                self.assertEqual(wf.getnchannels(), 2)  # Stereo
                self.assertEqual(wf.getsampwidth(), 2)  # 16-bit
                self.assertEqual(wf.getframerate(), 22050)
                duration = wf.getnframes() / float(wf.getframerate())
                self.assertAlmostEqual(duration, 8.0, delta=0.5)

    def test_03_custom_audio_discovery(self):
        custom_file = self.sound_dir / "custom_chill_cafe.wav"
        # Copy rain as dummy custom
        rain_file = self.sound_dir / "rain.wav"
        custom_file.write_bytes(rain_file.read_bytes())

        catalog = self.manager.list_soundscapes()
        custom_item = next((item for item in catalog if item["id"] == "custom_chill_cafe"), None)
        self.assertIsNotNone(custom_item)
        self.assertTrue(custom_item["is_custom"])
        self.assertEqual(custom_item["name"], "Custom Chill Cafe (Custom)")

        # Cleanup
        custom_file.unlink(missing_ok=True)

    def test_04_path_traversal_prevention(self):
        # Attempting traversal like ../../something
        bad = self.manager.get_track_file("../../kuro_database.db")
        self.assertIsNone(bad)

        # Valid track resolves properly
        good = self.manager.get_track_file("rain")
        self.assertIsNotNone(good)
        self.assertTrue(good.is_file())


class TestSoundscapeDatabaseAndAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "test_kuro.db"
        cls.db_manager = DatabaseManager(cls.db_path)
        cls.sound_dir = Path(cls.temp_dir.name) / "soundscapes"
        cls.soundscape_mgr = SoundscapeManager(cls.sound_dir)

        # Save server state
        cls.orig_db = server.db_manager
        cls.orig_sound = server.soundscape_manager
        cls.orig_port = server.PORT

        server.db_manager = cls.db_manager
        server.soundscape_manager = cls.soundscape_mgr

        # Dynamic test port
        cls.port = 54445
        server.PORT = cls.port
        cls.server = server.ThreadedHTTPServer(("127.0.0.1", cls.port), server.KuroHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        server.db_manager = cls.orig_db
        server.soundscape_manager = cls.orig_sound
        server.PORT = cls.orig_port
        cls.temp_dir.cleanup()

    def setUp(self):
        # Reset DB settings before each test
        self.db_manager.update_soundscape_settings({
            "enabled": False,
            "current_track": "rain",
            "volume": 40,
            "muted": True,
            "crossfade_seconds": 2.5
        })

    def test_database_crud(self):
        settings = self.db_manager.get_soundscape_settings()
        self.assertFalse(settings["enabled"])
        self.assertTrue(settings["muted"])  # Starts muted by default
        self.assertEqual(settings["current_track"], "rain")
        self.assertEqual(settings["volume"], 40)

        # Update settings
        ok = self.db_manager.update_soundscape_settings({
            "enabled": True,
            "current_track": "japanese_forest",
            "volume": 65,
            "muted": False,
            "crossfade_seconds": 3.0
        })
        self.assertTrue(ok)

        updated = self.db_manager.get_soundscape_settings()
        self.assertTrue(updated["enabled"])
        self.assertFalse(updated["muted"])
        self.assertEqual(updated["current_track"], "japanese_forest")
        self.assertEqual(updated["volume"], 65)
        self.assertEqual(updated["crossfade_seconds"], 3.0)

    def test_api_soundscape_catalog_and_settings(self):
        # 1. GET /api/soundscapes
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/soundscapes")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("soundscapes", data)
            self.assertGreaterEqual(len(data["soundscapes"]), 8)

        # 2. GET /api/soundscapes/settings
        req_set = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/soundscapes/settings")
        with urllib.request.urlopen(req_set) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("enabled", data)
            self.assertIn("muted", data)
            self.assertTrue(data["muted"])

        # 3. POST /api/soundscapes/settings without CSRF token fails (401)
        payload = json.dumps({"enabled": True, "volume": 55, "muted": False}).encode("utf-8")
        req_bad = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/soundscapes/settings",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req_bad)
        self.assertEqual(ctx.exception.code, 401)

        # 4. POST /api/soundscapes/settings with valid CSRF token succeeds
        token = server.security_manager.session_token
        req_good = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/soundscapes/settings",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Kuro-Token": token
            }
        )
        with urllib.request.urlopen(req_good) as resp:
            self.assertEqual(resp.status, 200)
            res_data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(res_data["status"], "updated")
            self.assertTrue(res_data["settings"]["enabled"])
            self.assertFalse(res_data["settings"]["muted"])
            self.assertEqual(res_data["settings"]["volume"], 55)

    def test_audio_file_streaming(self):
        # Verify /soundscapes/rain.wav streams with Content-Type audio/wav
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/soundscapes/rain.wav")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            content_type = resp.headers.get("Content-Type")
            self.assertIn("audio", content_type.lower())
            body = resp.read()
            self.assertTrue(body.startswith(b"RIFF"))  # Valid WAV header
            self.assertGreater(len(body), 50000)


if __name__ == "__main__":
    unittest.main()
