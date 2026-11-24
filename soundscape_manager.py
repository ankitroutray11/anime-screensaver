"""
Ambient Soundscape Manager for Kuro Screensaver.
Manages local soundscape tracks in the soundscapes/ directory.
Supports .wav, .mp3, .ogg, .flac, .m4a.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import soundscape_generator

SOUNDSCAPES_DIR = Path(__file__).resolve().parent / "soundscapes"


class SoundscapeManager:
    def __init__(self, soundscapes_dir: Optional[Path] = None):
        self.soundscapes_dir = soundscapes_dir or SOUNDSCAPES_DIR
        self.soundscapes_dir.mkdir(parents=True, exist_ok=True)
        # Ensure default tracks exist
        soundscape_generator.build_all_soundscapes(self.soundscapes_dir)

    def list_soundscapes(self) -> List[Dict[str, Any]]:
        """Returns catalog of all local audio files in soundscapes/ directory."""
        tracks = []
        # Official catalog entries
        for key, (name, desc, _) in soundscape_generator.SOUNDSCAPES_CATALOG.items():
            path = self.soundscapes_dir / f"{key}.wav"
            size = path.stat().st_size if path.is_file() else 0
            tracks.append({
                "id": key,
                "name": name,
                "description": desc,
                "filename": f"{key}.wav",
                "exists": path.is_file(),
                "size": size,
                "is_custom": False
            })

        # Also discover user custom added audio files
        allowed_exts = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
        catalog_files = {f"{k}.wav" for k in soundscape_generator.SOUNDSCAPES_CATALOG}
        for f in self.soundscapes_dir.iterdir():
            if f.is_file() and f.suffix.lower() in allowed_exts and f.name not in catalog_files:
                track_id = f.stem.lower().replace(" ", "_")
                clean_name = f.stem.replace("_", " ").title()
                tracks.append({
                    "id": track_id,
                    "name": f"{clean_name} (Custom)",
                    "description": f"Custom user audio ({f.suffix.upper()})",
                    "filename": f.name,
                    "exists": True,
                    "size": f.stat().st_size,
                    "is_custom": True
                })

        return tracks

    def get_track_file(self, track_id: str) -> Optional[Path]:
        """Resolves file path for a track ID safely within soundscapes directory."""
        clean_id = track_id.lower().replace("-", "_")
        for f in self.soundscapes_dir.iterdir():
            if f.is_file() and f.stem.lower().replace("-", "_") == clean_id:
                try:
                    resolved = f.resolve()
                    if resolved.is_relative_to(self.soundscapes_dir.resolve()):
                        return resolved
                except AttributeError:
                    return f.resolve()
        return None
