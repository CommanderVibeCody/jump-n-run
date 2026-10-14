"""Minimap and house rendering (headless)."""
import pygame
import pytest

from game import constants as C
from game.app import App
from game.game import GameScene
from game.level import Level
from game.levels import LEVELS
from game.render import (MINIMAP_SCALE, WorldRenderer, draw_minimap, render_facade, render_level_surface,
                         render_minimap_surface)
from game.settings import Settings
from game.world import World


@pytest.fixture(scope="module")
def screen():
    pygame.init()
    return pygame.display.set_mode((C.SCREEN_WIDTH, C.SCREEN_HEIGHT))


def key(k):
    return pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="", scancode=0)


def test_minimap_surface_matches_level_and_marks_tiles(screen):
    lv = Level(LEVELS[0])
    mm = render_minimap_surface(lv)
    assert mm.get_size() == (lv.width * MINIMAP_SCALE, lv.height * MINIMAP_SCALE)
    s = MINIMAP_SCALE
    ground = mm.get_at((5 * s + 1, (lv.height - 1) * s + 1))
    air = mm.get_at((5 * s + 1, 1))
    assert ground != air
    h = lv.houses[0]
    back = next(iter(c for c in h.cells))
    assert mm.get_at((back[0] * s + 1, back[1] * s + 1)) not in (ground, air)


def test_minimap_draws_dots_in_the_corner(screen):
    w = World(seed=1)
    screen.fill((0, 0, 0))
    rect = draw_minimap(screen, w, render_minimap_surface(w.level))
    assert rect.right <= C.SCREEN_WIDTH and rect.bottom <= C.SCREEN_HEIGHT
    assert rect.right > C.SCREEN_WIDTH - 40 and rect.bottom > C.SCREEN_HEIGHT - 40
    colours = {tuple(screen.get_at((x, y)))[:3] for x in range(rect.left, rect.right) for y in range(rect.top, rect.bottom)}
    assert len(colours) > 5
    reds = [c for c in colours if c[0] > 150 and c[1] < 90 and c[2] < 90]
    assert reds, "enemies are drawn as red dots"
    # semi-transparent: the black background darkens the panel
    assert all(max(c) < 250 for c in colours if c != (230, 235, 245))


def test_minimap_toggle_with_tab_n_and_settings(screen):
    settings = Settings()
    assert settings.minimap
    scene = GameScene(seed=1, settings=settings)
    scene.handle_event(key(pygame.K_TAB))
    assert not settings.minimap
    scene.handle_event(key(pygame.K_n))
    assert settings.minimap
    scene.update(1 / 60)
    scene.draw(screen)


def test_settings_menu_has_minimap_option(screen):
    app = App(seed=1)
    app.settings.minimap = True
    from game.menu import SettingsScreen
    sc = SettingsScreen(app.menu.background if hasattr(app.menu, "background") else None, app.settings)
    labels = sc.labels()
    idx = next(i for i, l in enumerate(labels) if l.startswith("Minimap"))
    sc.menu.selected = idx
    sc.handle_event(key(pygame.K_RETURN))
    assert not app.settings.minimap and "Off" in sc.labels()[idx]


def test_e_key_opens_doors_in_game(screen):
    scene = GameScene(seed=1)
    w = scene.world
    d = w.level.doors[0]
    b = w.player.body
    b.x, b.y = d.tx * C.TILE - 40, (d.ty + d.height) * C.TILE - b.h
    scene.handle_event(key(pygame.K_e))
    for _ in range(3):
        scene.update(1 / 60)
    assert d.open


def test_houses_render_backwalls_and_facade_fades(screen):
    w = World(seed=1)
    lv = w.level
    surf = render_level_surface(lv)
    h = lv.houses[0]
    tx, ty = next(iter(h.cells))
    assert surf.get_at((tx * C.TILE + 8, ty * C.TILE + 20)).a == 255   # back wall is opaque
    facade = render_facade(lv, h)
    assert facade.get_width() == (h.x1 - h.x0 + 1) * C.TILE
    r = WorldRenderer()
    b = w.player.body
    d = lv.doors[0]
    b.x, b.y = (d.tx + 2) * C.TILE, (d.ty + d.height) * C.TILE - b.h
    h = lv.house_map[(d.tx + 1, d.ty)]
    assert h.reveal == 0.0          # facade fully shown while outside
    r.draw(screen, w)
    for _ in range(120):
        w.step()
    assert w.inside_house is h and h.reveal > 0.95
    r.draw(screen, w)
    r.draw_minimap(screen, w)
