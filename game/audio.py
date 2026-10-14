"""Procedural audio: every sound effect and the background music loop are
synthesised with numpy at startup - there are no audio files.

If there is no audio device (or numpy / the mixer is unavailable) the
``Audio`` object silently becomes a no-op, so the game always runs.
"""
from __future__ import annotations

import math
import sys
from typing import Dict, List, Optional

import pygame

from .settings import Settings

try:  # numpy is only needed for audio
    import numpy as np
except Exception:  # pragma: no cover - depends on the environment
    np = None

SAMPLE_RATE = 22050
MUSIC_CHANNEL = 0

# base volume per sound (before master volume)
VOLUMES = {
    "step": 0.18, "jump": 0.35, "land": 0.4, "hover": 0.3, "select": 0.5,
    "flamethrower": 0.35, "smg": 0.45, "machinegun": 0.45, "enemy_shot": 0.35,
    "enemy_hit": 0.5, "empty": 0.6, "bounce": 0.35, "door": 0.45,
}
# minimum time between two plays of the same sound (seconds)
THROTTLE = {"step": 0.12, "enemy_hit": 0.04, "flamethrower": 0.09, "bounce": 0.08, "explosion": 0.05,
            "hover": 0.03}


# ------------------------------------------------------------ synthesis
def _n(samples: float) -> int:
    return int(round(samples))


def _t(duration: float):
    return np.arange(_n(SAMPLE_RATE * duration)) / SAMPLE_RATE


def _env(n: int, attack: float = 0.004, decay: float = 10.0):
    t = np.arange(n) / SAMPLE_RATE
    e = np.exp(-t * decay)
    a = max(1, int(attack * SAMPLE_RATE))
    e[:a] *= np.linspace(0, 1, a)
    return e


def _sweep(f0: float, f1: float, duration: float, wave: str = "sine"):
    t = _t(duration)
    freq = f0 * (f1 / f0) ** (t / max(duration, 1e-6))  # exponential sweep
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    if wave == "square":
        return np.sign(np.sin(phase))
    if wave == "saw":
        return 2 * ((phase / (2 * np.pi)) % 1.0) - 1
    if wave == "triangle":
        return 2 * np.abs(2 * ((phase / (2 * np.pi)) % 1.0) - 1) - 1
    return np.sin(phase)


def _noise(duration: float, rng):
    return rng.uniform(-1, 1, _n(SAMPLE_RATE * duration))


def _lowpass(x, width: int):
    """Cheap low-pass filter: moving average via cumulative sum."""
    if width <= 1:
        return x
    c = np.cumsum(np.concatenate([np.zeros(width), x]))
    return (c[width:] - c[:-width]) / width


def _mix(*parts):
    n = max(len(p) for p in parts)
    out = np.zeros(n)
    for p in parts:
        out[: len(p)] += p
    return out


def _seq(*parts, gap: float = 0.0):
    g = np.zeros(int(gap * SAMPLE_RATE))
    out = []
    for p in parts:
        out += [p, g]
    return np.concatenate(out)


def _gun(rng, duration, decay, lp, body_f0, body_f1, body_amp=0.5):
    n = _noise(duration, rng)
    n = _lowpass(n, lp) * _env(len(n), 0.001, decay)
    b = _sweep(body_f0, body_f1, duration * 0.6) * _env(_n(SAMPLE_RATE * duration * 0.6), 0.001, decay * 1.5)
    return _mix(n * 1.4, b * body_amp)


def synthesize_sounds(seed: int = 7) -> Dict[str, "np.ndarray"]:
    """Return mono float arrays (-1..1) for every sound effect."""
    rng = np.random.default_rng(seed)
    s: Dict[str, np.ndarray] = {}
    s["pistol"] = _gun(rng, 0.16, 30, 3, 700, 160)
    s["dual_pistols"] = _gun(rng, 0.12, 38, 2, 900, 220)
    s["smg"] = _gun(rng, 0.08, 55, 2, 800, 300, 0.3)
    s["shotgun"] = _mix(_gun(rng, 0.45, 9, 7, 140, 45, 0.9), _seq(np.zeros(int(0.28 * SAMPLE_RATE)),
                        _sweep(1500, 1400, 0.02, "square") * 0.15, _sweep(1100, 1000, 0.03, "square") * 0.15, gap=0.06))
    s["machinegun"] = _gun(rng, 0.1, 45, 3, 500, 150, 0.4)
    s["sniper"] = _mix(_gun(rng, 0.7, 7, 2, 1400, 120, 0.6), _sweep(3000, 300, 0.25) * _env(_n(0.25 * SAMPLE_RATE), 0.001, 12) * 0.25)
    flame = _lowpass(_noise(0.18, rng), 10)
    s["flamethrower"] = flame * np.sin(np.linspace(0, np.pi, len(flame))) * 1.6
    s["grenade_launcher"] = _mix(_sweep(220, 60, 0.22) * _env(_n(0.22 * SAMPLE_RATE), 0.002, 14),
                                 _lowpass(_noise(0.15, rng), 6) * _env(_n(0.15 * SAMPLE_RATE), 0.001, 25) * 0.7)
    whoosh = _lowpass(_noise(0.6, rng), 5)
    s["rocket"] = _mix(whoosh * np.linspace(1, 0, len(whoosh)) ** 2 * 0.9,
                       _sweep(150, 70, 0.4) * _env(_n(0.4 * SAMPLE_RATE), 0.002, 6) * 0.6)
    charge = _sweep(300, 2400, 0.09, "saw") * 0.25
    zap = _mix(_sweep(2200, 90, 0.45, "square") * _env(_n(0.45 * SAMPLE_RATE), 0.001, 8) * 0.35,
               _lowpass(_noise(0.3, rng), 2) * _env(_n(0.3 * SAMPLE_RATE), 0.001, 14))
    s["railgun"] = np.concatenate([charge, zap])
    s["enemy_shot"] = _gun(rng, 0.14, 32, 4, 420, 110, 0.4)
    s["empty"] = _seq(_sweep(1800, 1700, 0.012, "square") * 0.3, _sweep(1200, 1100, 0.015, "square") * 0.25, gap=0.03)
    s["reload"] = _seq(_sweep(900, 700, 0.03, "square") * 0.25, _sweep(1400, 1200, 0.025, "square") * 0.25,
                       _sweep(500, 1000, 0.08, "triangle") * 0.3, gap=0.05)
    s["jump"] = _sweep(260, 620, 0.13, "square") * _env(_n(0.13 * SAMPLE_RATE), 0.002, 14) * 0.25
    s["land"] = _lowpass(_noise(0.1, rng), 14) * _env(_n(0.1 * SAMPLE_RATE), 0.001, 30) * 1.6
    s["step"] = _lowpass(_noise(0.04, rng), 10) * _env(_n(0.04 * SAMPLE_RATE), 0.001, 60) * 1.2
    s["pickup"] = _seq(*[_sweep(f, f, 0.06, "triangle") * _env(_n(0.06 * SAMPLE_RATE), 0.002, 20) * 0.45
                         for f in (660, 880, 1320)])
    s["weapon_pickup"] = np.concatenate([s["reload"], s["pickup"]])
    s["enemy_hit"] = _mix(_lowpass(_noise(0.07, rng), 3) * _env(_n(0.07 * SAMPLE_RATE), 0.001, 40),
                          _sweep(260, 140, 0.07) * _env(_n(0.07 * SAMPLE_RATE), 0.001, 30) * 0.5)
    s["enemy_death"] = _mix(_sweep(380, 70, 0.4, "saw") * _env(_n(0.4 * SAMPLE_RATE), 0.002, 7) * 0.35,
                            _lowpass(_noise(0.3, rng), 4) * _env(_n(0.3 * SAMPLE_RATE), 0.001, 14) * 0.8)
    s["hurt"] = _sweep(340, 140, 0.22, "saw") * _env(_n(0.22 * SAMPLE_RATE), 0.002, 10) * 0.45
    s["death"] = _sweep(600, 50, 0.9, "saw") * _env(_n(0.9 * SAMPLE_RATE), 0.005, 3) * 0.45
    boom = _lowpass(_noise(1.3, rng), 22) * _env(_n(1.3 * SAMPLE_RATE), 0.002, 3.5) * 2.2
    s["explosion"] = _mix(boom, _sweep(80, 28, 0.8) * _env(_n(0.8 * SAMPLE_RATE), 0.002, 4) * 0.9,
                          _lowpass(_noise(0.15, rng), 2) * _env(_n(0.15 * SAMPLE_RATE), 0.001, 25) * 0.6)
    s["bounce"] = _sweep(500, 380, 0.04, "triangle") * _env(_n(0.04 * SAMPLE_RATE), 0.001, 50) * 0.5
    s["checkpoint"] = _seq(*[_sweep(f, f, 0.1, "triangle") * _env(_n(0.1 * SAMPLE_RATE), 0.003, 9) * 0.45
                             for f in (523, 659, 784, 1047)])
    notes = [(523, 0.12), (659, 0.12), (784, 0.12), (1047, 0.5)]
    s["level_complete"] = _seq(*[_mix(_sweep(f, f, d, "square") * 0.18, _sweep(f / 2, f / 2, d, "triangle") * 0.3)
                                 * _env(_n(d * SAMPLE_RATE), 0.004, 3 if d > 0.3 else 6) for f, d in notes])
    s["hover"] = _sweep(900, 950, 0.035) * _env(_n(0.035 * SAMPLE_RATE), 0.001, 60) * 0.4
    s["select"] = _sweep(500, 1200, 0.11, "triangle") * _env(_n(0.11 * SAMPLE_RATE), 0.002, 15) * 0.5
    s["door"] = _mix(_sweep(180, 120, 0.18, "saw") * _env(_n(0.18 * SAMPLE_RATE), 0.01, 12) * 0.3,
                     _lowpass(_noise(0.08, rng), 8) * _env(_n(0.08 * SAMPLE_RATE), 0.001, 35))
    return {name: _normalize(data, 0.9) for name, data in s.items()}


def _normalize(x, peak: float):
    m = float(np.max(np.abs(x))) if len(x) else 0.0
    return x * (peak / m) if m > peak else x


def synthesize_music(seed: int = 3, bpm: float = 124.0):
    """A seamless 4-bar loop: bass, arpeggio, kick, snare and hi-hats."""
    rng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    bars = 4
    n = int(round(bars * 4 * beat * SAMPLE_RATE))
    out = np.zeros(n)

    def place(sig, start_s):
        i = int(start_s * SAMPLE_RATE)
        if i >= n:
            return
        end = min(n, i + len(sig))
        out[i:end] += sig[: end - i]

    chords = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)]  # Am F C G (MIDI)

    def hz(m):
        return 440.0 * 2 ** ((m - 69) / 12)

    eighth = beat / 2
    for bar, chord in enumerate(chords):
        t0 = bar * 4 * beat
        root = hz(chord[0] - 24)
        for i in range(8):  # bass on eighths
            f = root * (2 if i % 4 == 3 else 1)
            sig = _lowpass(_sweep(f, f, eighth * 0.9, "saw"), 6) * _env(_n(eighth * 0.9 * SAMPLE_RATE), 0.004, 5) * 0.32
            place(sig, t0 + i * eighth)
        for i in range(16):  # arpeggio on sixteenths
            m = chord[[0, 1, 2, 1][i % 4]] + (12 if i % 8 >= 4 else 0)
            d = beat / 4
            sig = _sweep(hz(m), hz(m), d * 0.8, "square") * _env(_n(d * 0.8 * SAMPLE_RATE), 0.002, 18) * 0.06
            place(sig, t0 + i * d)
        for b in range(4):
            kick = _sweep(150, 40, 0.18) * _env(_n(0.18 * SAMPLE_RATE), 0.001, 16) * 0.8
            place(kick, t0 + b * beat)
            hat = np.diff(_noise(0.04, rng), prepend=0) * _env(_n(0.04 * SAMPLE_RATE), 0.001, 90) * 0.12
            place(hat, t0 + b * beat + eighth)
            if b % 2 == 1:
                snare = _lowpass(_noise(0.18, rng), 2) * _env(_n(0.18 * SAMPLE_RATE), 0.001, 20) * 0.35
                place(snare, t0 + b * beat)
    return _normalize(out, 0.8)


def warn(message: str) -> None:
    """Audio problems are printed, never silently swallowed."""
    print(f"[jump-n-run audio] {message}", file=sys.stderr, flush=True)


def to_array(samples, mixer_format, volume: float = 1.0):
    """Convert mono float samples (-1..1, SAMPLE_RATE) into an array that
    matches the mixer exactly: frequency, sample format and channel count."""
    freq, size, channels = mixer_format
    samples = np.asarray(samples, dtype=np.float64)
    if freq != SAMPLE_RATE:  # resample by linear interpolation
        n = max(1, int(round(len(samples) * freq / SAMPLE_RATE)))
        samples = np.interp(np.linspace(0, len(samples) - 1, n), np.arange(len(samples)), samples)
    data = np.clip(samples * volume, -1.0, 1.0)
    if size == 8:
        arr = np.round(data * 127 + 128).astype(np.uint8)
    elif size == -8:
        arr = np.round(data * 127).astype(np.int8)
    elif size == 16:
        arr = np.round(data * 32767 + 32768).astype(np.uint16)
    elif size == -16:
        arr = np.round(data * 32767).astype(np.int16)
    elif abs(size) == 32:  # pygame reports 32-bit float output as 32 or -32
        arr = data.astype(np.float32)
    else:
        raise ValueError(f"unsupported mixer sample size {size}")
    if channels > 1:
        arr = np.repeat(arr[:, None], channels, axis=1)
    return np.ascontiguousarray(arr)


def to_sound(samples, volume: float = 1.0):
    """Convert a mono float array into a pygame Sound matching the mixer format."""
    fmt = pygame.mixer.get_init()
    if not fmt:
        raise RuntimeError("mixer is not initialised")
    return pygame.sndarray.make_sound(to_array(samples, fmt, volume))


def sound_peak(sound) -> float:
    """Peak amplitude of a Sound as a fraction of full scale (0 = silent)."""
    arr = pygame.sndarray.array(sound)
    if arr.size == 0:
        return 0.0
    fmt = pygame.mixer.get_init()
    size = fmt[1] if fmt else -16
    a = arr.astype(np.float64)
    if size == 8:
        a = (a - 128) / 127
    elif size == 16:
        a = (a - 32768) / 32767
    elif size == -8:
        a = a / 127
    elif size == -16:
        a = a / 32767
    return float(np.max(np.abs(a)))


def init_mixer() -> Optional[tuple]:
    """Initialise the mixer, trying the preferred format first and then the
    device default. Returns the actual format or None (with warnings)."""
    if pygame.mixer.get_init():
        return pygame.mixer.get_init()
    errors: List[str] = []
    for args in ((SAMPLE_RATE, -16, 2, 512), (44100, -16, 2, 1024), ()):
        try:
            pygame.mixer.init(*args)
            fmt = pygame.mixer.get_init()
            if fmt:
                return fmt
        except Exception as exc:
            errors.append(f"mixer.init{args}: {exc}")
    warn("could not initialise the mixer: " + "; ".join(errors or ["unknown error"]))
    return None


_CACHE: Dict[str, object] = {}


class Audio:
    """Plays procedural sounds; becomes silent when audio is unavailable."""

    def __init__(self, settings: Optional[Settings] = None, enable: bool = True) -> None:
        self.settings = settings or Settings()
        self.enabled = False
        self.sounds: Dict[str, "pygame.mixer.Sound"] = {}
        self.music: Optional["pygame.mixer.Sound"] = None
        self.music_channel = None
        self.error: Optional[str] = None
        self.format = None
        self.time = 0.0
        self._last_played: Dict[str, float] = {}
        if enable:
            self._init()

    def _init(self) -> None:
        if np is None:
            self._disable("numpy is not installed (pip install -r requirements.txt)")
            return
        try:
            fmt = init_mixer()
        except Exception as exc:
            fmt = None
            warn(f"mixer error: {exc}")
        if not fmt:
            self._disable("no audio device / mixer unavailable")
            return
        try:
            pygame.mixer.set_num_channels(32)
            pygame.mixer.set_reserved(1)
            if "sounds" not in _CACHE:
                _CACHE["sounds"] = synthesize_sounds()
                _CACHE["music"] = synthesize_music()
            key = ("converted", fmt)
            if key not in _CACHE:
                sounds = {}
                for name, data in _CACHE["sounds"].items():
                    try:
                        sounds[name] = to_sound(data)
                    except Exception as exc:  # one broken sound must not kill all audio
                        warn(f"could not build sound {name!r} for mixer format {fmt}: {exc}")
                music = None
                try:
                    music = to_sound(_CACHE["music"])
                except Exception as exc:
                    warn(f"could not build the music loop for mixer format {fmt}: {exc}")
                _CACHE[key] = (sounds, music)
            self.sounds, self.music = _CACHE[key]
            if not self.sounds:
                self._disable(f"no sound could be built for mixer format {fmt}")
                return
            if sound_peak(self.sounds["pistol"]) < 0.05:
                warn(f"generated sounds are silent for mixer format {fmt} - please report this")
            self.music_channel = pygame.mixer.Channel(MUSIC_CHANNEL)
            self.enabled = True
            self.format = fmt
        except Exception as exc:
            self._disable(f"{type(exc).__name__}: {exc}")

    def _disable(self, reason: str) -> None:
        self.enabled = False
        self.error = reason
        self.sounds = {}
        warn(f"audio disabled, the game runs without sound ({reason}). Run 'python main.py --audio-test' for details.")

    def info(self) -> str:
        fmt = pygame.mixer.get_init()
        driver = None
        try:
            import os
            driver = os.environ.get("SDL_AUDIODRIVER") or "default"
        except Exception:
            pass
        return (f"enabled={self.enabled} mixer={fmt} (frequency, size, channels) driver={driver} "
                f"channels={pygame.mixer.get_num_channels() if fmt else 0} sounds={len(self.sounds)} "
                f"music={'yes' if self.music else 'no'} error={self.error}")

    # ------------------------------------------------------------ control
    def update(self, dt: float) -> None:
        self.time += dt
        self.apply_settings()

    def apply_settings(self) -> None:
        if not self.enabled or self.music_channel is None:
            return
        vol = self.settings.music_volume * 0.6
        if vol > 0 and self.music is not None:
            if not self.music_channel.get_busy():
                self.music_channel.play(self.music, loops=-1)
            self.music_channel.set_volume(vol)
        elif self.music_channel.get_busy():
            self.music_channel.stop()

    def play(self, name: str, volume: float = 1.0) -> bool:
        """Play a sound effect. Returns True if a sound was started."""
        if not self.enabled:
            return False
        vol = self.settings.sfx_volume * VOLUMES.get(name, 0.6) * volume
        sound = self.sounds.get(name)
        if sound is None or vol <= 0:
            return False
        last = self._last_played.get(name, -1e9)
        if self.time - last < THROTTLE.get(name, 0.0):
            return False
        self._last_played[name] = self.time
        channel = pygame.mixer.find_channel(True)  # steal the oldest if all are busy
        if channel is None:
            return False
        channel.set_volume(vol)
        channel.play(sound)
        return True

    def stop_all(self) -> None:
        if self.enabled:
            pygame.mixer.stop()


def audio_test() -> int:
    """``python main.py --audio-test``: print mixer info and play test sounds."""
    import time
    try:
        pygame.mixer.pre_init(SAMPLE_RATE, -16, 2, 512)
    except Exception as exc:
        warn(f"pre_init failed: {exc}")
    pygame.init()
    print(f"pygame {pygame.version.ver}, SDL {'.'.join(map(str, pygame.get_sdl_version()))}, "
          f"numpy {getattr(np, '__version__', 'missing')}")
    settings = Settings(master_volume=1.0)
    a = Audio(settings)
    print(a.info())
    if not a.enabled:
        print("Audio is NOT working:", a.error)
        return 1
    for name in ("pistol", "explosion", "pickup"):
        print(f"  {name:10s} peak={sound_peak(a.sounds[name]):.2f} length={a.sounds[name].get_length():.2f}s")
    print("Playing a test beep, three effects and 3 s of music ...")
    beep = to_sound(0.5 * np.sin(2 * np.pi * 440 * np.arange(int(0.5 * SAMPLE_RATE)) / SAMPLE_RATE))
    print(f"  beep peak={sound_peak(beep):.2f}")
    beep.play()
    time.sleep(0.7)
    for name in ("pistol", "explosion", "pickup"):
        a.play(name)
        time.sleep(0.6)
    a.apply_settings()
    time.sleep(3.0)
    pygame.quit()
    print("Done. If you heard nothing, check your system volume and output device.")
    return 0
