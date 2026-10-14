"""Explosive barrels, soldiers, corpses and blood."""
import math
import random

import pytest

from game import constants as C
from game.effects import Effects, STICK
from game.enemies import Barrel, Grenadier, Heavy, Rifleman, Shotgunner, Soldier
from game.level import Level
from game.player import InputState
from helpers import make_world, settle, steps

BARRELS = ["                              ", "  P     bbb      b     b       ", "##############################"]


def test_shooting_a_barrel_makes_it_explode():
    w = make_world(BARRELS)
    settle(w)
    n = len(w.barrels)
    exploded = 0
    for _ in range(200):
        w.step(InputState(shoot=True))
        exploded += w.events.count("barrel_exploded")
    assert exploded >= 1
    assert len(w.barrels) < n


def test_barrels_chain_react_with_delay():
    w = make_world(BARRELS)
    settle(w)
    first = w.barrels[0]
    first.take_damage(Barrel.MAX_HEALTH)
    times = []
    for i in range(120):
        w.step()
        times += [i] * w.events.count("barrel_exploded")
    # the group of three goes up as a chain (after a short fuse), the far ones survive
    assert len(times) == 3
    assert times[0] < times[-1]
    assert len(w.barrels) == 2


def test_barrel_explosion_hurts_the_player():
    w = make_world(["          ", " Pb       ", "##########"])
    settle(w)
    w.barrels[0].take_damage(100)
    steps(w, 30)
    assert w.player.health < C.PLAYER_MAX_HEALTH


def test_player_rockets_do_not_hurt_the_player():
    w = make_world(["          ", " P   #    ", "##########"])
    settle(w)
    fire = InputState(shoot=True)
    w.player.give_weapon("rocket")
    w.step(fire)
    steps(w, 60)
    assert w.player.health == C.PLAYER_MAX_HEALTH


@pytest.mark.parametrize("char,cls", [("r", Rifleman), ("k", Shotgunner), ("g", Grenadier), ("h", Heavy)])
def test_soldier_variants_attack_visible_player(char, cls):
    w = make_world(["                    ", f"  P     {char}           ", "####################"])
    e = w.enemies[0]
    assert isinstance(e, cls) and e.human
    hurt = False
    for _ in range(int(5 / C.FIXED_DT)):
        w.step()
        if w.player.health < C.PLAYER_MAX_HEALTH:
            hurt = True
            break
    assert hurt


def test_soldier_aims_at_player():
    w = make_world(["                    ", "  P     r           ", "####################"])
    steps(w, 60)
    e = w.enemies[0]
    assert e.sees_player
    assert math.cos(e.aim_angle) < -0.9  # aiming left at the player


def test_soldier_patrols_when_alone():
    w = make_world(["#                  #", "#   r            P #", "####################"])
    w.player.body.y = -500  # out of sight
    w.player.alive = False
    e = w.enemies[0]
    x0 = e.body.x
    steps(w, 120)
    assert abs(e.body.x - x0) > 20


def test_killed_soldier_leaves_a_flying_corpse():
    w = make_world(["                    ", "  P     r           ", "####################"])
    settle(w)
    e = w.enemies[0]
    w.damage_enemy(e, 999, 300, -100)
    assert len(w.corpses) == 1
    c = w.corpses[0]
    assert c.body.vx > 0 and c.body.vy < 0
    steps(w, 240)
    assert c.body.on_ground
    assert abs(math.sin(c.angle)) > 0.9  # lying down


def test_explosion_kill_gibs_the_soldier():
    w = make_world(["                    ", "  P     r           ", "####################"])
    settle(w)
    e = w.enemies[0]
    w.explode_at(e.body.cx, e.body.cy, 100, 200, 400, "player")
    assert "gibbed" in w.events
    assert not w.corpses
    assert any(p.kind == "gib" for p in w.effects.particles)


def test_without_blood_there_are_no_blood_particles_or_gibs():
    w = make_world(["                    ", "  P     r           ", "####################"], blood=False)
    settle(w)
    e = w.enemies[0]
    w.explode_at(e.body.cx, e.body.cy, 100, 200, 400, "player")
    assert not any(p.kind in ("blood", "gib") for p in w.effects.particles)
    assert len(w.corpses) == 1


def test_blood_flies_in_hit_direction_falls_and_sticks_to_floor():
    level = Level.from_ascii(["P         ", "          ", "          ", "##########"])
    fx = Effects(random.Random(1))
    fx.blood(100, 40, 1.0, 0.0, amount=20)
    drops = [p for p in fx.particles if p.kind == "blood"]
    assert drops and all(p.collide == STICK for p in drops)
    assert sum(p.vx for p in drops) > 0  # sprays to the right
    vy0 = sum(p.vy for p in drops)
    fx.update(0.05, level)
    assert sum(p.vy for p in fx.particles) > vy0  # gravity pulls down
    for _ in range(200):
        fx.update(C.FIXED_DT, level)
    assert not [p for p in fx.particles if p.kind == "blood"]  # all landed
    floor = [d for d in fx.decals if d.surface == "floor"]
    assert floor
    for d in floor:
        assert d.y == pytest.approx(3 * C.TILE)


def test_blood_sticks_to_walls():
    level = Level.from_ascii(["P   #", "    #", "#####"])
    fx = Effects(random.Random(2))
    fx.blood(100, 20, 1.0, -0.2, amount=30, force=1.5)
    for _ in range(200):
        fx.update(C.FIXED_DT, level)
    walls = [d for d in fx.decals if d.surface in ("left", "right")]
    assert walls
    assert all(d.x == pytest.approx(4 * C.TILE) for d in walls)


def test_explosion_spawns_shockwave_smoke_and_debris():
    fx = Effects(random.Random(1))
    fx.explosion(100, 100, 100)
    kinds = {p.kind for p in fx.particles}
    assert {"smoke", "debris", "fire"} <= kinds
    assert fx.rings and fx.trauma > 0.8
