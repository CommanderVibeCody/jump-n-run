"""The soldier roster: every type has its own stats and behaviour."""
import math
import os

import pytest

from game import constants as C
from game.enemies import (ENEMY_TYPES, SOLDIER_TYPES, Grenadier, Heavy, Officer, Recruit, Rifleman, Rocketeer,
                          Shooter, Shotgunner, Sniper, Soldier)
from game.level import Level
from game.levels import LEVELS
from game.player import InputState
from game.weapons import Projectile
from helpers import make_world, settle, steps

ROSTER = {"e": Recruit, "r": Rifleman, "k": Shotgunner, "g": Grenadier, "n": Sniper, "h": Heavy,
          "o": Officer, "q": Rocketeer, "s": Shooter}


def stats(cls):
    return (cls.MAX_HEALTH, cls.PATROL_SPEED, cls.GUN, cls.BULLET_DAMAGE, cls.COOLDOWN, cls.RANGE)


def test_roster_is_exactly_the_soldiers():
    assert ENEMY_TYPES == ROSTER
    assert all(issubclass(c, Soldier) and c.human for c in SOLDIER_TYPES)


def test_no_blob_walkers_or_drones_remain():
    import game.enemies as en
    assert not hasattr(en, "Walker") and not hasattr(en, "Drone")
    for d in LEVELS:
        lv = Level(d)
        assert not lv.spawns_of("wd"), d.name
    root = os.path.join(os.path.dirname(__file__), "..", "game")
    for name in os.listdir(root):
        if name.endswith(".py"):
            text = open(os.path.join(root, name)).read().lower()
            assert "drone" not in text and "walker" not in text, name


def test_every_soldier_type_has_distinct_stats_and_uniform():
    assert len({stats(c) for c in SOLDIER_TYPES}) == len(SOLDIER_TYPES)
    assert len({c.PALETTE["uniform"] for c in SOLDIER_TYPES}) == len(SOLDIER_TYPES)


def test_stat_relationships():
    assert Recruit.MAX_HEALTH == min(c.MAX_HEALTH for c in SOLDIER_TYPES)
    assert Heavy.MAX_HEALTH == max(c.MAX_HEALTH for c in SOLDIER_TYPES)
    assert Sniper.RANGE == max(c.RANGE for c in SOLDIER_TYPES)
    assert Sniper.BULLET_DAMAGE == max(c.BULLET_DAMAGE for c in SOLDIER_TYPES if c not in (Rocketeer, Grenadier))  # splash weapons aside
    assert Officer.PATROL_SPEED == max(c.PATROL_SPEED for c in SOLDIER_TYPES)
    assert Shooter.PATROL_SPEED == 0


@pytest.mark.parametrize("char", sorted(ROSTER))
def test_every_soldier_shoots_at_a_visible_player(char):
    w = make_world(["                         ", f"  P       {char}              ", "#########################"])
    w.enemies[0].facing = -1
    for _ in range(int(5 / C.FIXED_DT)):
        w.step()
        if any(p.owner == "enemy" for p in w.projectiles):
            break
    assert any(p.owner == "enemy" for p in w.projectiles)


@pytest.mark.parametrize("char", sorted(ROSTER))
def test_stomping_works_on_every_soldier(char):
    w = make_world(["          "] * 2 + ["    P     ", "          ", f"    {char}     ", "##########"])
    e = w.enemies[0]
    for _ in range(60):
        w.step()
        if "stomp" in w.events:
            break
    assert "stomp" in w.events
    assert e.health == e.MAX_HEALTH - C.STOMP_DAMAGE or not e.alive
    assert w.player.body.vy < 0


def test_sniper_aims_long_and_hits_hard():
    w = make_world(["                              ", "  P                      n    ", "##############################"])
    e = w.enemies[0]
    e.facing = -1
    saw_windup = False
    for _ in range(int(4 / C.FIXED_DT)):
        w.step()
        saw_windup |= e.windup > 0
        shots = [p for p in w.projectiles if p.owner == "enemy"]
        if shots:
            assert shots[0].damage == Sniper.BULLET_DAMAGE and shots[0].speed == Sniper.BULLET_SPEED
            break
    assert saw_windup and shots


def test_rocketeer_fires_explosive_rockets():
    w = make_world(["                         ", "  P          q           ", "#########################"])
    w.enemies[0].facing = -1
    for _ in range(int(5 / C.FIXED_DT)):
        w.step()
        rockets = [p for p in w.projectiles if p.owner == "enemy"]
        if rockets:
            break
    assert rockets[0].kind == "rocket" and rockets[0].explosion_radius > 0


def test_officer_dodges_incoming_bullets():
    w = make_world(["                         ", "  P          o           ", "#########################"])
    settle(w)
    o = w.enemies[0]
    o.dodge_cooldown = 0
    w.projectiles.append(Projectile(o.body.cx - 120, o.body.cy, 0.0, 700, 10, "player", 2.0, (255, 255, 0)))
    steps(w, 10)
    assert o.dodges == 1 and not o.body.on_ground


def test_officer_keeps_its_distance():
    w = make_world(["                              ", "  P  o                        ", "##############################"])
    o = w.enemies[0]
    o.facing = -1
    x0 = o.body.cx
    steps(w, 120)
    assert o.body.cx > x0 + 64  # backs away from a close player
    assert o.body.cx - w.player.body.cx >= 190
