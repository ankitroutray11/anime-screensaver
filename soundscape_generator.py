"""
Procedural Ambient Soundscape Audio Generator for Kuro Screensaver.
Uses Python standard library only (math, struct, wave, random).
Generates seamless 16-bit PCM stereo WAV ambient audio loops for 8 categories:
- Rain
- Thunderstorm
- Japanese Forest
- Night City Ambience
- Ocean Waves
- Wind
- Fireplace
- Space Ambience

Includes automated boundary crossfading for perfect zero-click seamless looping.
"""

import math
import random
import struct
import wave
from pathlib import Path
from typing import List, Tuple

SAMPLE_RATE = 22050
DURATION = 8.0  # 8-second seamless loop
NUM_SAMPLES = int(SAMPLE_RATE * DURATION)
CROSSFADE_SAMPLES = int(SAMPLE_RATE * 0.5)  # 0.5s loop-boundary blend


def apply_seamless_loop(samples_l: List[float], samples_r: List[float], total_len: int, fade_len: int) -> Tuple[List[float], List[float]]:
    """Crossfades the tail into the head to eliminate boundary pops on repeat."""
    out_l = samples_l[:total_len]
    out_r = samples_r[:total_len]

    for i in range(fade_len):
        t = i / float(fade_len)
        tail_idx = total_len + i
        if tail_idx < len(samples_l):
            out_l[i] = out_l[i] * t + samples_l[tail_idx] * (1.0 - t)
            out_r[i] = out_r[i] * t + samples_r[tail_idx] * (1.0 - t)

    # Normalize peak to ~0.82 to avoid clipping
    max_peak = max(max(abs(s) for s in out_l), max(abs(s) for s in out_r), 0.001)
    scale = min(0.82 / max_peak, 1.0)
    out_l = [s * scale for s in out_l]
    out_r = [s * scale for s in out_r]
    return out_l, out_r


def write_wav(file_path: Path, samples_l: List[float], samples_r: List[float]):
    """Writes 16-bit stereo PCM WAV file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(file_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for sl, sr in zip(samples_l, samples_r):
            # Clamp to -1.0 .. +1.0
            cl = max(-1.0, min(1.0, sl))
            cr = max(-1.0, min(1.0, sr))
            il = int(cl * 32767.0)
            ir = int(cr * 32767.0)
            frames.extend(struct.pack("<hh", il, ir))
        wf.writeframes(frames)


def generate_rain() -> Tuple[List[float], List[float]]:
    """Synthesizes steady rain with filtered noise and randomized droplet impacts."""
    count = NUM_SAMPLES + CROSSFADE_SAMPLES
    l, r = [0.0] * count, [0.0] * count
    
    # 1. Pink noise bed (rain background)
    b0_l, b1_l, b2_l = 0.0, 0.0, 0.0
    b0_r, b1_r, b2_r = 0.0, 0.0, 0.0
    for i in range(count):
        w_l = (random.random() * 2.0 - 1.0)
        w_r = (random.random() * 2.0 - 1.0)
        b0_l = 0.99886 * b0_l + w_l * 0.0555179
        b1_l = 0.99332 * b1_l + w_l * 0.0750759
        b2_l = 0.96900 * b2_l + w_l * 0.1538520
        b0_r = 0.99886 * b0_r + w_r * 0.0555179
        b1_r = 0.99332 * b1_r + w_r * 0.0750759
        b2_r = 0.96900 * b2_r + w_r * 0.1538520
        l[i] = (b0_l + b1_l + b2_l) * 0.25
        r[i] = (b0_r + b1_r + b2_r) * 0.25

    # 2. Intermittent rain droplets
    drop_count = int(DURATION * 90)
    for _ in range(drop_count):
        pos = random.randint(0, count - 400)
        pan = random.random()
        freq = random.uniform(1800, 3600)
        decay = random.uniform(0.005, 0.015)
        decay_samples = int(decay * SAMPLE_RATE)
        for d in range(min(decay_samples, count - pos)):
            env = math.exp(-d / (decay_samples * 0.25))
            wave_val = math.sin(2.0 * math.pi * freq * (d / SAMPLE_RATE)) * env * 0.4
            l[pos + d] += wave_val * (1.0 - pan)
            r[pos + d] += wave_val * pan

    return apply_seamless_loop(l, r, NUM_SAMPLES, CROSSFADE_SAMPLES)


def generate_thunderstorm() -> Tuple[List[float], List[float]]:
    """Synthesizes rain ambience with deep, rolling low-frequency thunder."""
    l, r = generate_rain()
    count = NUM_SAMPLES
    
    # Add deep low-frequency rumble swells (40-90Hz)
    rumble = [0.0] * count
    brown = 0.0
    for i in range(count):
        white = random.random() * 2.0 - 1.0
        brown = (brown + (0.02 * white)) / 1.02
        rumble[i] = brown * 3.5

    # Thunder strike peaks around t=2.5s and t=6.0s
    for strike_time in [2.5, 6.0]:
        strike_idx = int(strike_time * SAMPLE_RATE)
        for i in range(int(1.8 * SAMPLE_RATE)):
            idx = strike_idx + i
            if idx < count:
                env = math.sin((i / (1.8 * SAMPLE_RATE)) * math.pi) ** 2
                l[idx] += rumble[idx] * env * 0.7
                r[idx] += rumble[idx] * env * 0.75

    return apply_seamless_loop(l, r, NUM_SAMPLES, CROSSFADE_SAMPLES)


def generate_japanese_forest() -> Tuple[List[float], List[float]]:
    """Synthesizes gentle bamboo leaf rustle, subtle bird chirp, and serene wind chimes."""
    count = NUM_SAMPLES + CROSSFADE_SAMPLES
    l, r = [0.0] * count, [0.0] * count

    # 1. Soft leaf rustle (gentle high-frequency noise)
    hp = 0.0
    for i in range(count):
        white = random.random() * 2.0 - 1.0
        hp = white - (0.95 * hp)
        l[i] = hp * 0.08
        r[i] = (random.random() * 2.0 - 1.0 - (0.95 * hp)) * 0.08

    # 2. Pentatonic Japanese Wind Chimes (Insen scale notes: 1175Hz, 1318Hz, 1568Hz, 1760Hz, 2093Hz)
    chime_freqs = [1174.66, 1318.51, 1567.98, 1760.00, 2093.00]
    chime_times = [1.2, 3.4, 5.1, 7.0]
    for ct in chime_times:
        c_idx = int(ct * SAMPLE_RATE)
        freq = random.choice(chime_freqs)
        pan = random.uniform(0.2, 0.8)
        chime_dur = int(1.2 * SAMPLE_RATE)
        for ci in range(min(chime_dur, count - c_idx)):
            t = ci / SAMPLE_RATE
            env = math.exp(-ci / (SAMPLE_RATE * 0.35))
            val = math.sin(2.0 * math.pi * freq * t) * env * 0.35
            # Harmonic overtone
            val += math.sin(2.0 * math.pi * (freq * 2.76) * t) * (env * 0.15)
            l[c_idx + ci] += val * (1.0 - pan)
            r[c_idx + ci] += val * pan

    return apply_seamless_loop(l, r, NUM_SAMPLES, CROSSFADE_SAMPLES)


def generate_night_city() -> Tuple[List[float], List[float]]:
    """Synthesizes low urban rumble, distant traffic hum, and subtle neon atmospheric buzz."""
    count = NUM_SAMPLES + CROSSFADE_SAMPLES
    l, r = [0.0] * count, [0.0] * count

    # Sub-bass traffic drone (55Hz + 110Hz)
    for i in range(count):
        t = i / SAMPLE_RATE
        drone = (
            math.sin(2.0 * math.pi * 55.0 * t) * 0.25 +
            math.sin(2.0 * math.pi * 110.0 * t) * 0.12 +
            math.sin(2.0 * math.pi * 165.0 * t) * 0.06
        )
        # Add subtle filtered street noise
        noise_l = (random.random() * 2.0 - 1.0) * 0.06
        noise_r = (random.random() * 2.0 - 1.0) * 0.06
        l[i] = drone + noise_l
        r[i] = drone + noise_r

    return apply_seamless_loop(l, r, NUM_SAMPLES, CROSSFADE_SAMPLES)


def generate_ocean_waves() -> Tuple[List[float], List[float]]:
    """Synthesizes rhythmic low swells and foamy surf crests."""
    count = NUM_SAMPLES + CROSSFADE_SAMPLES
    l, r = [0.0] * count, [0.0] * count

    wave_period = 4.0  # 4 seconds per wave swell
    brown_l, brown_r = 0.0, 0.0

    for i in range(count):
        t = i / SAMPLE_RATE
        # Swell envelope
        swell = (math.sin(2.0 * math.pi * (1.0 / wave_period) * t - (math.pi / 2)) + 1.0) * 0.5
        surf_env = swell ** 2.2

        w_l = random.random() * 2.0 - 1.0
        w_r = random.random() * 2.0 - 1.0
        brown_l = (brown_l + (0.05 * w_l)) / 1.05
        brown_r = (brown_r + (0.05 * w_r)) / 1.05

        l[i] = (brown_l * 1.5 + w_l * 0.15) * surf_env
        r[i] = (brown_r * 1.5 + w_r * 0.15) * surf_env

    return apply_seamless_loop(l, r, NUM_SAMPLES, CROSSFADE_SAMPLES)


def generate_wind() -> Tuple[List[float], List[float]]:
    """Synthesizes dynamic howling gusts and gentle breezy fluctuations."""
    count = NUM_SAMPLES + CROSSFADE_SAMPLES
    l, r = [0.0] * count, [0.0] * count

    band_l, band_r = 0.0, 0.0
    for i in range(count):
        t = i / SAMPLE_RATE
        # Wind gust LFO (0.25 Hz)
        gust = (math.sin(2.0 * math.pi * 0.25 * t) + math.sin(2.0 * math.pi * 0.12 * t)) * 0.35 + 0.65
        
        w_l = random.random() * 2.0 - 1.0
        w_r = random.random() * 2.0 - 1.0
        band_l = band_l * 0.96 + w_l * 0.12
        band_r = band_r * 0.96 + w_r * 0.12

        l[i] = band_l * gust * 1.8
        r[i] = band_r * gust * 1.8

    return apply_seamless_loop(l, r, NUM_SAMPLES, CROSSFADE_SAMPLES)


def generate_fireplace() -> Tuple[List[float], List[float]]:
    """Synthesizes warm hearth roar with crisp, randomized crackling wood pops."""
    count = NUM_SAMPLES + CROSSFADE_SAMPLES
    l, r = [0.0] * count, [0.0] * count

    # Warm low roar
    roar = 0.0
    for i in range(count):
        w = random.random() * 2.0 - 1.0
        roar = (roar + (0.04 * w)) / 1.04
        l[i] = roar * 0.4
        r[i] = roar * 0.4

    # Frequent wood crackles
    crackle_count = int(DURATION * 40)
    for _ in range(crackle_count):
        pos = random.randint(0, count - 100)
        pan = random.random()
        intensity = random.uniform(0.3, 0.9)
        decay_samples = random.randint(15, 60)
        for ci in range(decay_samples):
            if pos + ci < count:
                env = (1.0 - (ci / decay_samples)) ** 3
                val = (random.random() * 2.0 - 1.0) * env * intensity
                l[pos + ci] += val * (1.0 - pan)
                r[pos + ci] += val * pan

    return apply_seamless_loop(l, r, NUM_SAMPLES, CROSSFADE_SAMPLES)


def generate_space_ambience() -> Tuple[List[float], List[float]]:
    """Synthesizes deep celestial drone and ethereal choir pad harmonics."""
    count = NUM_SAMPLES + CROSSFADE_SAMPLES
    l, r = [0.0] * count, [0.0] * count

    # Chord harmonics: C1 (65.4Hz), G1 (98Hz), Eb2 (155.6Hz), Bb2 (233.1Hz), D3 (293.7Hz)
    chord = [65.41, 98.00, 155.56, 233.08, 293.66]
    for i in range(count):
        t = i / SAMPLE_RATE
        val_l, val_r = 0.0, 0.0
        for idx, freq in enumerate(chord):
            # Subtle detuning / chorusing between L and R
            phase_l = 2.0 * math.pi * freq * t
            phase_r = 2.0 * math.pi * (freq * 1.003) * t
            amp = 0.22 / (idx + 1)
            val_l += math.sin(phase_l) * amp
            val_r += math.sin(phase_r) * amp

        l[i] = val_l
        r[i] = val_r

    return apply_seamless_loop(l, r, NUM_SAMPLES, CROSSFADE_SAMPLES)


SOUNDSCAPES_CATALOG = {
    "rain": ("Rain", "Gentle rhythmic rainfall and droplets", generate_rain),
    "thunderstorm": ("Thunderstorm", "Distant rolling thunder and heavy rain", generate_thunderstorm),
    "japanese_forest": ("Japanese Forest", "Bamboo leaf rustle and serene wind chimes", generate_japanese_forest),
    "night_city": ("Night City Ambience", "Low metropolitan drone and distant neon hum", generate_night_city),
    "ocean_waves": ("Ocean Waves", "Rolling surf swells and foamy coastlines", generate_ocean_waves),
    "wind": ("Wind", "Atmospheric mountain gusts and breezy currents", generate_wind),
    "fireplace": ("Fireplace", "Warm glowing hearth and crackling wood sparks", generate_fireplace),
    "space_ambience": ("Space Ambience", "Deep celestial drone and ethereal nebula pads", generate_space_ambience),
}


def build_all_soundscapes(target_dir: Path) -> List[dict]:
    """Generates all 8 soundscape WAV files if not already present."""
    target_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for key, (name, desc, gen_func) in SOUNDSCAPES_CATALOG.items():
        file_path = target_dir / f"{key}.wav"
        if not file_path.is_file() or file_path.stat().st_size < 1000:
            print(f"[KuroSound] Synthesizing ambient soundscape: {name} -> {file_path.name}")
            samples_l, samples_r = gen_func()
            write_wav(file_path, samples_l, samples_r)

        results.append({
            "id": key,
            "name": name,
            "description": desc,
            "filename": file_path.name,
            "size": file_path.stat().st_size if file_path.is_file() else 0,
            "duration": DURATION
        })

    return results


if __name__ == "__main__":
    out_dir = Path(__file__).resolve().parent / "soundscapes"
    build_all_soundscapes(out_dir)
    print(f"Generated {len(SOUNDSCAPES_CATALOG)} soundscapes in {out_dir}")
