import pygame
import pytest

from game import constants as C
from game.app import App


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.init()
    pygame.display.set_mode((C.SCREEN_WIDTH, C.SCREEN_HEIGHT))


def key(k):
    return pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="", scancode=0)


def run(app, seconds, screen=None):
    for _ in range(int(seconds * 60)):
        app.update(1 / 60)
        if screen is not None:
            app.draw(screen)


def test_menu_navigation_wraps_around():
    app = App(seed=1)
    menu = app.menu.menu
    assert menu.items == ["Play", "Controls", "Settings", "Quit"]
    app.handle_event(key(pygame.K_UP))
    assert menu.selected == 3
    app.handle_event(key(pygame.K_DOWN))
    assert menu.selected == 0


def test_controls_screen_and_back():
    app = App(seed=1)
    run(app, 0.5)
    app.handle_event(key(pygame.K_DOWN))
    app.handle_event(key(pygame.K_RETURN))
    run(app, 1.0)
    assert app.scene_name == "controls"
    app.handle_event(key(pygame.K_ESCAPE))
    run(app, 1.0)
    assert app.scene_name == "menu"


def test_quit_entry_stops_app():
    app = App(seed=1)
    run(app, 0.5)
    app.handle_event(key(pygame.K_UP))
    app.handle_event(key(pygame.K_RETURN))
    assert not app.running


def test_mouse_click_on_play_starts_game():
    app = App(seed=1)
    run(app, 0.5)
    rect = app.menu.menu.item_rect(0)
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))
    run(app, 1.0)
    assert app.scene_name == "game"


def test_pause_menu_resume_and_back_to_main_menu():
    app = App(seed=1)
    screen = pygame.display.get_surface()
    run(app, 0.5)
    app.handle_event(key(pygame.K_RETURN))
    run(app, 1.0)
    game = app.game
    assert game is not None
    app.handle_event(key(pygame.K_ESCAPE))
    assert game.paused
    t = game.world.time
    run(app, 0.5, screen)
    assert game.world.time == t  # world frozen while paused
    app.handle_event(key(pygame.K_RETURN))  # Resume
    assert not game.paused
    run(app, 0.2, screen)
    assert game.world.time > t
    app.handle_event(key(pygame.K_ESCAPE))
    app.handle_event(key(pygame.K_DOWN))
    app.handle_event(key(pygame.K_DOWN))
    app.handle_event(key(pygame.K_RETURN))  # Main Menu
    run(app, 1.0, screen)
    assert app.scene_name == "menu"
    assert app.game is None


def test_transition_blocks_input_while_fading_out():
    app = App(seed=1)
    run(app, 0.5)
    app.handle_event(key(pygame.K_RETURN))
    assert app.transitioning
    app.handle_event(key(pygame.K_DOWN))
    assert app.menu.menu.selected == 0


def test_settings_screen_toggles_and_volume():
    app = App(seed=1)
    run(app, 0.5)
    app.handle_event(key(pygame.K_DOWN))
    app.handle_event(key(pygame.K_DOWN))
    app.handle_event(key(pygame.K_RETURN))
    run(app, 1.0)
    assert app.scene_name == "settings"
    s = app.settings
    v = s.master_volume
    app.handle_event(key(pygame.K_LEFT))
    assert s.master_volume == pytest.approx(v - 0.1)
    for flag in ("sfx", "music", "blood"):
        app.handle_event(key(pygame.K_DOWN))
        before = getattr(s, flag)
        app.handle_event(key(pygame.K_RETURN))
        assert getattr(s, flag) is (not before)
    assert "Blood: Off" in app.settings_screen.menu.items
    app.handle_event(key(pygame.K_ESCAPE))
    run(app, 1.0)
    assert app.scene_name == "menu"


def test_blood_setting_reaches_the_game():
    app = App(seed=1)
    app.settings.blood = False
    app.go("game")
    run(app, 1.0)
    assert app.game.world.blood is False


def test_m_key_toggles_mute():
    app = App(seed=1)
    assert not app.settings.muted
    app.handle_event(key(pygame.K_m))
    assert app.settings.muted
    app.handle_event(key(pygame.K_m))
    assert not app.settings.muted
