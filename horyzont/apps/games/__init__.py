"""Gry: Saper i Pasjans."""
import math
import os
import struct
import wave

from ... import config


def tone_file(name, notes, rate=22050, volume=0.35):
    """Krótki dźwięk WAV (lista (częstotliwość Hz, czas s, kształt)) zapisany w pamięci podręcznej. Zwraca ścieżkę."""
    d = os.path.join(config.CACHE_DIR, "game-sounds")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name + ".wav")
    if os.path.exists(path):
        return path
    frames = bytearray()
    for freq, dur, shape in notes:
        n = int(rate * dur)
        for i in range(n):
            t = i / rate
            env = min(1.0, i / (rate * 0.004)) * max(0.0, 1 - i / n) ** 1.5
            if shape == "noise":
                import random
                v = random.uniform(-1, 1)
            elif shape == "square":
                v = 1.0 if math.sin(2 * math.pi * freq * t) >= 0 else -1.0
            else:
                v = math.sin(2 * math.pi * freq * t)
            frames += struct.pack("<h", int(v * env * volume * 32767))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return path


def play_tone(name, notes):
    try:
        from ...common import sounds
        sounds.play_file(tone_file(name, notes))
    except Exception:
        pass
