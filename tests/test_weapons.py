import math
import random

import pytest

from game import constants as C
from game.player import InputState
from game.weapons import MACHINE_GUN, PISTOL, ROCKET, SHOTGUN, WEAPON_ORDER, WEAPONS, Projectile, Weapon
from game.level import Level
from helpers import make_world, settle, steps

PICKUP_ARENA = [
    "                              ",
    "                              ",
    "                              ",
    "  P S M R                     ",
    "##############################",
]


def test_player_starts_with_infinite_pistol():
    w = make_world()
    assert list(w.player.weapons) == ["pistol"]
    assert w.player.weapon.infinite


def test_walking_over_weapons_picks_them_up_and_switches():
    w = make_world(PICKUP_ARENA)
    settle(w)
    seen = []
    for _ in range(200):
        w.step(InputState(right=True))
        if w.player.current not in seen:
            seen.append(w.player.current)
    assert set(w.player.weapons) == {"pistol", "shotgun", "machinegun", "rocket"}
    assert seen == ["pistol", "shotgun", "machinegun", "rocket"]
    assert w.player.weapons["shotgun"].ammo == SHOTGUN.pickup_ammo
    assert not any(p.is_weapon for p in w.pickups)


def test_picking_up_owned_weapon_adds_ammo_up_to_max():
    w = make_world()
    p = w.player
    assert p.give_weapon("rocket") == "new"
    assert p.weapons["rocket"].ammo == ROCKET.pickup_ammo
    assert p.give_weapon("rocket") == "ammo"
    assert p.weapons["rocket"].ammo == ROCKET.max_ammo
    assert p.give_weapon("rocket") == "full"


def test_full_weapon_pickup_stays_in_level():
    w = make_world(["          ", " P S      ", "##########"])
    w.player.give_weapon("shotgun")
    w.player.weapons["shotgun"].ammo = SHOTGUN.max_ammo
    settle(w)
    steps(w, 60, InputState(right=True))
    assert len(w.pickups) == 1


def test_ammo_crate_refills_owned_weapons():
    w = make_world(["          ", " P a      ", "##########"])
    w.player.give_weapon("shotgun")
    w.player.weapons["shotgun"].ammo = 2
    settle(w)
    steps(w, 40, InputState(right=True))
    assert w.player.weapons["shotgun"].ammo == 2 + SHOTGUN.pickup_ammo // 2
    assert not w.pickups


def test_health_pack_heals_only_when_hurt():
    w = make_world(["          ", " P +      ", "##########"])
    settle(w)
    steps(w, 40, InputState(right=True))
    assert len(w.pickups) == 1  # full health: not taken
    w.player.health = 30
    steps(w, 5)
    assert w.player.health == 70
    assert not w.pickups


def test_shooting_consumes_ammo_and_spawns_projectiles():
    w = make_world()
    settle(w)
    p = w.player
    p.give_weapon("machinegun")
    ammo = p.weapon.ammo
    w.step(InputState(shoot=True))
    assert p.weapon.ammo == ammo - 1
    assert len([pr for pr in w.projectiles if pr.owner == "player"]) == 1
    assert "shoot" in w.events


def test_cooldown_limits_fire_rate():
    w = make_world()
    settle(w)
    p = w.player  # pistol
    shots = 0
    for _ in range(int(1.0 / C.FIXED_DT)):
        w.step(InputState(shoot=True))
        shots += "shoot" in w.events
    assert shots == math.ceil(1.0 / PISTOL.cooldown)


def test_shotgun_fires_a_spread_of_pellets():
    weapon = Weapon(SHOTGUN)
    shots = weapon.fire(0, 0, 0.0, random.Random(1))
    assert len(shots) == SHOTGUN.pellets
    angles = [math.atan2(s.dir_y, s.dir_x) for s in shots]
    assert max(angles) - min(angles) > SHOTGUN.pellet_arc * 0.7
    assert weapon.ammo == SHOTGUN.pickup_ammo - 1


def test_empty_weapon_cannot_fire_and_player_falls_back_to_pistol():
    w = make_world()
    settle(w)
    p = w.player
    p.give_weapon("rocket")
    p.weapons["rocket"].ammo = 1
    w.step(InputState(shoot=True))
    assert p.weapons["rocket"].ammo == 0
    assert p.current == "pistol"
    assert not p.weapons["rocket"].can_fire()
    assert not p.select_slot(WEAPON_ORDER.index("rocket"))  # cannot select an empty weapon


def test_weapon_switching_cycles_owned_weapons():
    w = make_world()
    p = w.player
    for key in ("shotgun", "rocket"):
        p.give_weapon(key)
    p.current = "pistol"
    w.step(InputState(switch=1))
    assert p.current == "shotgun"
    w.step(InputState(switch=1))
    assert p.current == "rocket"
    w.step(InputState(switch=1))
    assert p.current == "pistol"
    w.step(InputState(switch=-1))
    assert p.current == "rocket"
    w.step(InputState(select_slot=WEAPON_ORDER.index("shotgun")))
    assert p.current == "shotgun"


def test_projectile_stops_at_wall():
    level = Level.from_ascii(["P       #", "#########"])
    pr = Projectile(10, 10, 0.0, 900, 10, "player", 5.0, (255, 255, 255))
    for _ in range(200):
        pr.update(C.FIXED_DT, level)
        if not pr.alive:
            break
    assert not pr.alive and pr.hit_wall
    assert 8 * C.TILE - 1 <= pr.x <= 8 * C.TILE + 8


def test_projectile_expires_after_lifetime():
    level = Level.from_ascii(["P" + " " * 200])
    pr = Projectile(10, 10, 0.0, 100, 10, "player", 0.5, (255, 255, 255))
    for _ in range(int(0.6 / C.FIXED_DT)):
        pr.update(C.FIXED_DT, level)
    assert not pr.alive and not pr.hit_wall


def test_mouse_aim_sets_shot_direction():
    w = make_world()
    settle(w)
    p = w.player
    sx, sy = p.shoulder()
    w.step(InputState(shoot=True, aim=(sx - 100, sy - 100)))
    pr = w.projectiles[0]
    assert pr.dir_x < 0 and pr.dir_y < 0
    assert p.facing == -1


def test_all_weapons_are_defined():
    assert set(WEAPONS) == {"pistol", "dual_pistols", "smg", "shotgun", "machinegun", "sniper",
                            "flamethrower", "grenade_launcher", "rocket", "railgun"}
    assert WEAPON_ORDER[0] == "pistol" and len(WEAPON_ORDER) == 10
    assert MACHINE_GUN.cooldown < PISTOL.cooldown < SHOTGUN.cooldown
