"""Headless smoke tests: run the real app loop with rendering on the dummy
video driver and feed it keyboard/mouse events."""
import pygame
import pytest

from game import constants as C
from game.app import App
from game.levels import LEVELS
from game.render import WorldRenderer, draw_hud
from game.world import World
from game.player import InputState


@pytest.fixture(scope="module")
def screen():
    pygame.init()
    s = pygame.display.set_mode((C.SCREEN_WIDTH, C.SCREEN_HEIGHT))
    return s


def key(t, k):
    return pygame.event.Event(t, key=k, mod=0, unicode="", scancode=0)


def test_play_session_runs_without_errors(screen):
    app = App(seed=3)
    for _ in range(30):
        app.update(1 / 60)
        app.draw(screen)
    app.handle_event(key(pygame.KEYDOWN, pygame.K_RETURN))
    for _ in range(60):
        app.update(1 / 60)
        app.draw(screen)
    assert app.scene_name == "game"
    game = app.game
    app.handle_event(key(pygame.KEYDOWN, pygame.K_d))
    app.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(800, 300), rel=(1, 1), buttons=(0, 0, 0)))
    for i in range(600):
        if i % 50 == 0:
            app.handle_event(key(pygame.KEYDOWN, pygame.K_SPACE))
        if i % 50 == 30:
            app.handle_event(key(pygame.KEYUP, pygame.K_SPACE))
        if i % 100 == 0:
            app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(800, 300)))
        if i % 100 == 60:
            app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(800, 300)))
        if i % 120 == 0:
            app.handle_event(key(pygame.KEYDOWN, pygame.K_e))
        app.update(1 / 60)
        app.draw(screen)
    assert app.running
    assert game.world.player.body.x > 200  # moved right
    assert game.world.time > 9.0


def test_render_every_level_with_all_effects(screen):
    renderer = WorldRenderer()
    for index in range(len(LEVELS)):
        w = World(LEVELS, seed=1, start_level=index)
        for key_ in ("shotgun", "machinegun", "rocket"):
            w.player.give_weapon(key_)
        for i in range(240):
            w.step(InputState(right=True, shoot=True, jump_pressed=i % 60 == 0, jump_held=True, switch=1 if i % 40 == 0 else 0))
            if i % 20 == 0:
                renderer.draw(screen, w)
                draw_hud(screen, w)
        w.effects.explosion(w.player.body.cx, w.player.body.cy, 90)
        renderer.draw(screen, w)
        draw_hud(screen, w)


def test_game_over_screen_and_play_again(screen):
    app = App(seed=1)
    app.go("game")
    for _ in range(60):
        app.update(1 / 60)
    game = app.game
    game.world.lives = 1
    game.world.kill_player()
    for _ in range(180):
        app.update(1 / 60)
        app.draw(screen)
    assert game.world.state == "game_over"
    app.handle_event(key(pygame.KEYDOWN, pygame.K_RETURN))  # Play Again
    assert game.world.state == "playing"
    assert game.world.lives == C.PLAYER_LIVES
