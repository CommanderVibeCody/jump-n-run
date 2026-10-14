"""Tests for the extended arsenal: piercing, bouncing grenades, flames,
hitscan railgun and dual pistols."""
import math
import random

import pytest

from game import constants as C
from game.level import Level
from game.player import InputState
from game.weapons import (DUAL_PISTOLS, FLAMETHROWER, GRENADE_LAUNCHER, PICKUP_WEAPON, RAILGUN, SMG, SNIPER,
                          WEAPONS, Projectile, Weapon, make_projectile)
from helpers import make_world, settle, steps

LINE = ["                              ", "  P     e  e  e     #         ", "##############################"]


def fire_once(w, key):
    w.player.give_weapon(key)
    w.player.current = key
    w.step(InputState(shoot=True))


@pytest.mark.parametrize("char,key", sorted(PICKUP_WEAPON.items()))
def test_every_weapon_pickup_char_spawns_its_weapon(char, key):
    w = make_world(["          ", f" P {char}      ", "##########"])
    settle(w)
    steps(w, 60, InputState(right=True))
    assert key in w.player.weapons
    assert w.player.current == key


def test_sniper_pierces_several_enemies():
    w = make_world(LINE)
    settle(w)
    fire_once(w, "sniper")
    steps(w, 60)
    assert w.kills == 3  # 120 damage kills each 40 HP recruit in one line


def test_railgun_is_instant_and_pierces_until_wall():
    w = make_world(LINE)
    settle(w)
    fire_once(w, "railgun")
    assert w.kills == 3  # same step, no projectile needed
    assert not w.projectiles
    beam = w.effects.beams[0]
    assert beam.x1 == pytest.approx(20 * C.TILE, abs=6)  # stopped by the wall


def test_grenade_bounces_then_explodes_after_fuse():
    level = Level.from_ascii(["P          ", "           ", "###########"])
    pr = make_projectile(GRENADE_LAUNCHER, 40, 20, 0.3, "player")
    bounced = False
    for _ in range(int(GRENADE_LAUNCHER.lifetime / C.FIXED_DT) + 2):
        pr.update(C.FIXED_DT, level)
        bounced |= pr.bounced
        assert pr.y < 2 * C.TILE  # never inside the floor
        if not pr.alive:
            break
    assert bounced
    assert not pr.alive and pr.expired and not pr.hit_wall


def test_grenade_explodes_in_world():
    w = make_world(["                    ", "  P     e           ", "####################"])
    settle(w)
    fire_once(w, "grenade_launcher")
    exploded = False
    for _ in range(400):
        w.step()
        exploded |= "explosion" in w.events
    assert exploded and w.kills == 1


def test_flamethrower_sets_enemies_on_fire():
    w = make_world(["                    ", "  P   s             ", "####################"])
    settle(w)
    e = w.enemies[0]
    w.player.give_weapon("flamethrower")
    w.player.current = "flamethrower"
    steps(w, 10, InputState(shoot=True))
    steps(w, 30)
    assert e.burn > 0 or not e.alive
    hp = e.health
    steps(w, 30)
    assert e.health < hp or not e.alive  # burning keeps hurting


def test_flames_pass_through_several_enemies():
    pr = make_projectile(FLAMETHROWER, 0, 0, 0, "player")
    assert pr.pierce >= 10 and pr.burn > 0


def test_dual_pistols_alternate_muzzles():
    weapon = Weapon(DUAL_PISTOLS)
    rng = random.Random(1)
    a = weapon.fire(0, 0, 0.0, rng)[0]
    weapon.cooldown = 0
    b = weapon.fire(0, 0, 0.0, rng)[0]
    assert a.y != b.y


def test_smg_is_fastest_bullet_weapon():
    assert SMG.cooldown < WEAPONS["machinegun"].cooldown


def test_casings_are_ejected_and_land():
    w = make_world()
    settle(w)
    w.step(InputState(shoot=True))
    casings = [p for p in w.effects.particles if p.kind == "casing"]
    assert casings
    steps(w, 120)
    floor = 9 * C.TILE
    for c in [p for p in w.effects.particles if p.kind == "casing"]:
        assert c.y <= floor + 1


def test_hitstop_freezes_world_on_kill():
    w = make_world(LINE)
    settle(w)
    fire_once(w, "railgun")
    assert w.hitstop > 0
    t = w.time
    w.step()
    assert w.time == t  # frozen
    steps(w, 20)
    assert w.time > t
