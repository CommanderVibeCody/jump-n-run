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
