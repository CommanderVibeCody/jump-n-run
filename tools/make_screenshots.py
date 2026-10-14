"""Render the README screenshots headless into docs/.

Usage:  python tools/make_screenshots.py
"""
import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pygame  # noqa: E402

from game import constants as C  # noqa: E402
from game.app import App  # noqa: E402
from game.game import GameScene  # noqa: E402
from game.player import InputState  # noqa: E402
from game.constants import TILE  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "docs")


def autoplay_input(world, state):
    """A tiny bot: run right, jump over walls, gaps and enemies, shoot."""
    p = world.player
    b, level = p.body, world.level
    if p.alive and b.on_ground:
        tx = math.floor((b.right + 28) / TILE)
        ty = math.floor((b.bottom + 2) / TILE)
        wall = any(level.is_solid(tx, math.floor(y / TILE)) for y in (b.top + 2, b.bottom - 2))
        gap = not any(level.is_solid(tx, ty + k) or level.is_one_way(tx, ty + k) for k in range(4))
        enemy = any(0 < e.body.cx - b.cx < 70 and abs(e.body.cy - b.cy) < 40 for e in world.enemies)
        if wall or gap or enemy:
            state["hold"] = 40
    hold = state.get("hold", 0)
    state["hold"] = max(0, hold - 1)
    return InputState(right=True, jump_pressed=hold == 40, jump_held=hold > 0, shoot=True)


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((C.SCREEN_WIDTH, C.SCREEN_HEIGHT))
    os.makedirs(OUT, exist_ok=True)

    app = App(seed=2)
    for _ in range(150):
        app.update(1 / 60)
    app.draw(screen)
    pygame.image.save(screen, os.path.join(OUT, "menu.png"))

    app.go("controls")
    for _ in range(80):
        app.update(1 / 60)
    app.draw(screen)
    pygame.image.save(screen, os.path.join(OUT, "controls.png"))

    app.go("settings")
    for _ in range(80):
        app.update(1 / 60)
    app.draw(screen)
    pygame.image.save(screen, os.path.join(OUT, "settings.png"))

    # gameplay: the bot fights through the warzone level with the SMG
    scene = GameScene(seed=4)
    world = scene.world
    world.load_level(2)
    for key in ("smg", "shotgun", "grenade_launcher", "railgun", "flamethrower"):
        world.player.give_weapon(key)
    world.player.current = "smg"
    state = {}
    for i in range(120 * 60):
        world.step(autoplay_input(world, state))
        if i > 240 and len(world.effects.decals) > 25 and world.corpses and world.player.alive \
                and world.player.invulnerable <= 0 and any(abs(e.body.cx - world.player.body.cx) < 300 for e in world.enemies):
            break
    scene.banner_time = 10.0
    scene.flash = 0.0
    scene.draw(screen)
    pygame.image.save(screen, os.path.join(OUT, "gameplay.png"))

    # explosion: shoot a group of barrels with the grenade launcher
    scene3 = GameScene(seed=6)
    w3 = scene3.world
    w3.load_level(2)
    w3.player.give_weapon("grenade_launcher")
    w3.player.body.x = 58 * TILE
    w3.player.body.y = 16 * TILE
    w3.camera.snap(w3.player.body.cx, w3.player.body.cy, 1)
    for i in range(120 * 6):
        w3.step(InputState())
        if i == 30:
            for b in w3.barrels:
                if 60 * TILE < b.body.x < 70 * TILE:
                    b.take_damage(100)
                    break
        if "barrel_exploded" in w3.events and i > 40:
            for _ in range(10):
                w3.step(InputState())
            break
    scene3.banner_time = 10.0
    scene3.flash = 0.0
    scene3.draw(screen)
    pygame.image.save(screen, os.path.join(OUT, "explosion.png"))

    # pause menu on top of the same frame
    scene.paused = True
    for _ in range(30):
        scene.update(1 / 60)
    scene.draw(screen)
    pygame.image.save(screen, os.path.join(OUT, "pause.png"))

    # level 2 at night with the rocket launcher
    scene2 = GameScene(seed=5)
    w2 = scene2.world
    w2.load_level(1)
    w2.player.give_weapon("rocket")
    w2.player.give_weapon("machinegun")
    w2.player.current = "rocket"
    state = {}
    for i in range(120 * 30):
        w2.step(autoplay_input(w2, state))
        if "explosion" in w2.events and i > 200 and w2.player.alive and w2.player.invulnerable <= 0:
            for _ in range(4):
                w2.step(autoplay_input(w2, state))
            break
    scene2.banner_time = 10.0
    scene2.flash = 0.0
    scene2.draw(screen)
    pygame.image.save(screen, os.path.join(OUT, "night.png"))
    print("screenshots written to", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
