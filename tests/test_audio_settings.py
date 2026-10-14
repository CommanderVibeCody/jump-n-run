import pygame
import pytest

from game import audio as audio_mod
from game.audio import Audio, synthesize_music, synthesize_sounds
from game.settings import Settings

REQUIRED = ["pistol", "dual_pistols", "smg", "shotgun", "machinegun", "sniper", "flamethrower",
            "grenade_launcher", "rocket", "railgun", "empty", "reload", "jump", "land", "pickup", "weapon_pickup",
            "enemy_hit", "enemy_death", "hurt", "explosion", "checkpoint", "level_complete", "hover", "select",
            "step"]


def test_all_sounds_are_synthesized_and_in_range():
    sounds = synthesize_sounds()
    for name in REQUIRED:
        assert name in sounds, name
        data = sounds[name]
        assert len(data) > 100
        assert abs(data).max() <= 1.0


def test_music_loop_is_a_few_seconds_long():
    music = synthesize_music()
    assert 4 * audio_mod.SAMPLE_RATE < len(music) < 20 * audio_mod.SAMPLE_RATE
    assert abs(music).max() <= 1.0


def test_audio_falls_back_silently_when_mixer_fails(monkeypatch):
    def broken(*args, **kwargs):
        raise pygame.error("No available audio device")

    monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)
    monkeypatch.setattr(pygame.mixer, "init", broken)
    a = Audio(Settings())
    assert not a.enabled
    assert "audio device" in a.error
    assert a.play("pistol") is False
    a.update(0.1)  # no crash
    a.stop_all()


def test_audio_disabled_without_numpy(monkeypatch):
    monkeypatch.setattr(audio_mod, "np", None)
    a = Audio(Settings())
    assert not a.enabled


def test_audio_respects_settings():
    s = Settings()
    a = Audio(s)
    if not a.enabled:
        pytest.skip("no mixer available")
    assert a.play("explosion")
    s.sfx = False
    assert not a.play("jump")
    s.sfx = True
    s.toggle_mute()
    assert not a.play("jump")


def test_settings_volume_is_clamped_and_mute_silences_everything():
    s = Settings(master_volume=0.95)
    s.change_volume(0.1)
    assert s.master_volume == 1.0
    s.change_volume(-5)
    assert s.master_volume == 0.0
    s = Settings()
    s.toggle_mute()
    assert s.sfx_volume == 0.0 and s.music_volume == 0.0
    s.toggle_mute()
    s.music = False
    assert s.music_volume == 0.0 and s.sfx_volume > 0


import numpy as np
from game.audio import sound_peak, to_array


@pytest.mark.parametrize("fmt", [(22050, -16, 2), (44100, -16, 2), (48000, -16, 1), (44100, 16, 2),
                                 (22050, 8, 1), (44100, 32, 2), (44100, -32, 2), (22050, -8, 2)])
def test_arrays_match_every_mixer_format(fmt):
    freq, size, channels = fmt
    data = np.sin(np.linspace(0, 200, 22050))
    arr = to_array(data, fmt)
    assert arr.shape[0] == pytest.approx(len(data) * freq / 22050, abs=1)
    if channels > 1:
        assert arr.ndim == 2 and arr.shape[1] == channels
    else:
        assert arr.ndim == 1
    expected = {8: np.uint8, -8: np.int8, 16: np.uint16, -16: np.int16, 32: np.float32, -32: np.float32}[size]
    assert arr.dtype == expected
    centred = arr.astype(np.float64) - {8: 128, 16: 32768}.get(size, 0)
    assert np.abs(centred).max() > 0.5 * np.abs(centred).max(initial=1)  # not silent
    assert np.abs(centred).max() > 0


def test_built_sounds_are_not_silent():
    a = Audio(Settings())
    if not a.enabled:
        pytest.skip("no mixer available")
    for name, snd in a.sounds.items():
        assert sound_peak(snd) > 0.05, name
    assert sound_peak(a.music) > 0.05


def test_disabled_audio_prints_a_warning(monkeypatch, capsys):
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)
    monkeypatch.setattr(pygame.mixer, "init", lambda *a, **k: (_ for _ in ()).throw(pygame.error("boom")))
    Audio(Settings())
    err = capsys.readouterr().err
    assert "audio disabled" in err and "boom" in err


def test_audio_test_cli_runs_headless():
    import subprocess
    import sys
    import os
    env = dict(os.environ, SDL_AUDIODRIVER="dummy", SDL_VIDEODRIVER="dummy")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run([sys.executable, "main.py", "--audio-test"], cwd=root, env=env,
                         capture_output=True, text=True, timeout=60)
    assert "mixer=" in out.stdout
    assert out.returncode in (0, 1)
