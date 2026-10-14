"""Enterable houses: back walls, doors, ladders, windows and decoration."""
import math

import pytest

from game import constants as C
from game.level import Level, LevelDef
from game.levels import LEVELS, add_house
from game.player import InputState
from game.weapons import Projectile
from helpers import make_world, settle, steps

# a one storey house with a door in each wall
HOUSE = [
    "                         ",
    "        =#######=        ",
    "         #::O::#         ",
    "         #:t:l:#         ",
    "  P      |:::::|         ",
    "         |:x:e:|         ",
    "#########################",
]

# a two storey house built with the level helper
def two_storey():
    rows = [" " * 30 for _ in range(10)] + ["#" * 30]
    add_house(rows, 8, 10, 10, 2, {(2, 0): "x", (2, 1): "t"}, ladder=5, windows=(3,))
    rows[9] = rows[9][:2] + "P" + rows[9][3:]
    return rows


def test_backwall_layer_and_house_regions():
    lv = Level(LevelDef("t", HOUSE))
    assert len(lv.houses) == 1
    h = lv.houses[0]
    assert (h.x0, h.x1, h.y0, h.y1) == (9, 15, 1, 6)
    assert lv.is_back(11, 2) and lv.is_back(12, 2)        # ':' and window 'O'
    assert lv.tile(12, 2) == "O"
    assert lv.is_back(11, 3)                              # decor cell gets a back wall
    assert lv.is_back(13, 5)                              # enemy cell inside gets one too
    assert not lv.is_back(3, 4)                           # outside
    assert not lv.is_solid(11, 2)                         # back walls never block
    assert {d.kind for d in lv.decor} == {"t", "l", "x"}
    assert lv.house_at_point(12.5 * C.TILE, 4.5 * C.TILE) is h


def test_door_runs_are_grouped_and_block_while_closed():
    lv = Level(LevelDef("t", HOUSE))
    assert len(lv.doors) == 2
    d = lv.doors[0]
    assert (d.tx, d.ty, d.height) == (9, 4, 2)
    assert lv.is_solid(9, 4) and lv.is_solid(9, 5)
    d.open = True
    assert not lv.is_solid(9, 4)


def test_walking_into_a_door_opens_it_and_you_can_enter():
    w = make_world(HOUSE)
    settle(w)
    steps(w, 150, InputState(right=True))
    assert w.level.doors[0].open
    assert w.player.body.cx > 10 * C.TILE
    assert w.inside_house is w.level.houses[0]
    steps(w, 60)
    assert w.level.houses[0].reveal > 0.9   # exterior faded out


def test_interact_key_toggles_door_but_not_while_someone_stands_in_it():
    w = make_world(HOUSE)
    settle(w)
    d = w.level.doors[0]
    w.player.body.x = 7.6 * C.TILE
    steps(w, 10)
    w.step(InputState(interact=True))
    assert d.open
    w.step(InputState(interact=True))
    assert not d.open
    w.step(InputState(interact=True))
    assert d.open
    w.player.body.x = d.tx * C.TILE + 4   # standing in the doorway
    w.step(InputState(interact=True))
    assert d.open                          # cannot close on the player


def test_closed_doors_block_bullets_and_line_of_sight():
    w = make_world(HOUSE)
    settle(w)
    lv = w.level
    y = 5.5 * C.TILE
    assert not lv.line_of_sight(5 * C.TILE, y, 13 * C.TILE, y)
    lv.doors[0].open = True
    assert lv.line_of_sight(5 * C.TILE, y, 13 * C.TILE, y)
    lv.doors[0].open = False
    w.projectiles.append(Projectile(6 * C.TILE, y, 0.0, 600, 10, "player", 2.0, (255, 255, 0)))
    enemy = w.enemies[0]
    steps(w, 60)
    assert enemy.health == enemy.MAX_HEALTH


def test_explosions_break_doors_open():
    w = make_world(HOUSE)
    settle(w)
    d = w.level.doors[0]
    w.explode_at(d.tx * C.TILE - 20, (d.ty + 1) * C.TILE, 80, 10, 100, "player")
    assert d.open and d.broken
    w.step(InputState(interact=True))
    assert d.open  # broken doors stay open


def test_enemies_do_not_open_doors():
    w = make_world(HOUSE)
    settle(w)
    steps(w, 600)
    assert not any(d.open for d in w.level.doors)
    assert w.enemies[0].body.cx < 15 * C.TILE  # still inside


def test_ladder_top_is_standable_and_ladders_are_climbable():
    rows = two_storey()
    lv = Level(LevelDef("t", rows))
    lx = 8 + 5
    assert lv.is_ladder(lx, 6) and lv.is_one_way(lx, 6)      # slab hole: top rung
    assert lv.is_ladder(lx, 9) and not lv.is_one_way(lx, 9)
    w = make_world(rows)
    settle(w)
    p = w.player
    p.body.x = lx * C.TILE + (C.TILE - p.body.w) / 2
    steps(w, 30)
    assert p.on_ground and p.body.bottom == pytest.approx(10 * C.TILE)
    for _ in range(240):
        w.step(InputState(up=True))
        if p.body.bottom <= 6 * C.TILE + 0.5 and not p.climbing:
            break
    assert p.body.bottom <= 6 * C.TILE + 0.5       # reached the upper floor
    steps(w, 30)
    assert p.on_ground                             # standing on the ladder top
    floor_y = p.body.bottom
    for _ in range(240):
        w.step(InputState(down=True))
    assert p.body.bottom == pytest.approx(10 * C.TILE)   # climbed back down
    assert p.body.bottom > floor_y


def test_climbing_ignores_gravity_and_jumping_lets_go():
    rows = two_storey()
    w = make_world(rows)
    settle(w)
    p = w.player
    p.body.x = 13 * C.TILE + 5
    steps(w, 20)
    steps(w, 20, InputState(up=True))
    assert p.climbing
    y = p.body.y
    steps(w, 30)                                    # hold nothing: hang on the ladder
    assert p.climbing and p.body.y == pytest.approx(y)
    w.step(InputState(jump_pressed=True, jump_held=True))
    assert not p.climbing and p.body.vy < 0


def test_every_level_has_several_houses_with_doors_and_ladders():
    for d in LEVELS:
        lv = Level(d)
        assert len(lv.houses) >= 3, d.name
        assert len(lv.doors) >= 2 * len(lv.houses) - 1, d.name
        assert any(lv.is_ladder(x, y) for y in range(lv.height) for x in range(lv.width)), d.name
        inside = [s for s in lv.spawns if s.kind in "erkgnhoqs" and lv.is_back(s.tx, s.ty)]
        assert len(inside) >= 3, d.name   # interior enemies
        assert any(s.kind in "+aDUSMNFLRZ" and lv.is_back(s.tx, s.ty) for s in lv.spawns), d.name  # loot
