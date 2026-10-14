"""Weapons, projectiles and pickups."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Optional, Set

from .constants import TILE


@dataclass(frozen=True)
class WeaponSpec:
    key: str
    name: str
    color: tuple
    damage: float
    cooldown: float           # seconds between shots
    speed: float              # projectile speed in px/s
    spread: float = 0.0       # random angle jitter (radians, +-)
    pellets: int = 1          # projectiles per shot
    pellet_arc: float = 0.0   # total fan angle for multi-pellet weapons
    lifetime: float = 1.2     # projectile lifetime (seconds)
    max_ammo: Optional[int] = None  # None = infinite
    pickup_ammo: int = 0
    shake: float = 0.1        # screen shake trauma per shot
    recoil: float = 0.0       # push-back on the shooter (px/s)
    knockback: float = 120.0  # push on the target (px/s)
    explosion_radius: float = 0.0
    accel: float = 0.0        # projectile acceleration along its direction
    radius: float = 3.0
    pierce: int = 0           # how many extra enemies a projectile passes through
    gravity: float = 0.0      # projectile gravity (grenades)
    bounce: float = 0.0       # restitution when hitting walls (0 = destroyed)
    burn: float = 0.0         # seconds of burning applied to hit enemies
    hitscan: bool = False     # instant beam instead of a projectile
    kind: str = "bullet"      # projectile kind: bullet, rocket, grenade, flame
    casing: Optional[tuple] = (220, 180, 70)  # colour of ejected casings (None = no casing)
    dual: bool = False        # alternate between two muzzles


PISTOL = WeaponSpec("pistol", "Pistol", (250, 230, 120), damage=25, cooldown=0.28, speed=950,
                    spread=0.02, lifetime=1.0, shake=0.14, recoil=20)
DUAL_PISTOLS = WeaponSpec("dual_pistols", "Dual Pistols", (255, 240, 160), damage=20, cooldown=0.13, speed=980,
                          spread=0.05, lifetime=1.0, max_ammo=160, pickup_ammo=80, shake=0.12, recoil=15, dual=True)
SMG = WeaponSpec("smg", "SMG", (170, 255, 170), damage=9, cooldown=0.055, speed=1000, spread=0.13,
                 lifetime=0.7, max_ammo=240, pickup_ammo=120, shake=0.08, recoil=25, knockback=50, radius=2.5)
SHOTGUN = WeaponSpec("shotgun", "Shotgun", (255, 170, 80), damage=14, cooldown=0.75, speed=820,
                     spread=0.05, pellets=6, pellet_arc=0.42, lifetime=0.38, max_ammo=24,
                     pickup_ammo=12, shake=0.45, recoil=260, knockback=220, radius=2.5, casing=(200, 50, 40))
MACHINE_GUN = WeaponSpec("machinegun", "Machine Gun", (120, 230, 255), damage=11, cooldown=0.075,
                         speed=1050, spread=0.07, lifetime=0.9, max_ammo=180, pickup_ammo=90,
                         shake=0.12, recoil=35, knockback=70, radius=2.5)
SNIPER = WeaponSpec("sniper", "Sniper Rifle", (255, 255, 255), damage=120, cooldown=1.1, speed=1600,
                    lifetime=1.2, max_ammo=20, pickup_ammo=10, shake=0.5, recoil=180, knockback=380,
                    radius=3, pierce=3)
FLAMETHROWER = WeaponSpec("flamethrower", "Flamethrower", (255, 140, 40), damage=3, cooldown=0.03, speed=430,
                          spread=0.14, lifetime=0.5, max_ammo=300, pickup_ammo=150, shake=0.03, recoil=6,
                          knockback=10, radius=8, pierce=99, burn=1.8, kind="flame", casing=None)
GRENADE_LAUNCHER = WeaponSpec("grenade_launcher", "Grenade Launcher", (140, 220, 90), damage=100, cooldown=0.7,
                              speed=620, lifetime=1.6, max_ammo=12, pickup_ammo=6, shake=0.25, recoil=90,
                              knockback=480, explosion_radius=100, radius=5, gravity=1400, bounce=0.5,
                              kind="grenade", casing=(150, 150, 150))
ROCKET = WeaponSpec("rocket", "Rocket Launcher", (255, 100, 90), damage=110, cooldown=0.9, speed=320,
                    accel=1100, lifetime=2.5, max_ammo=10, pickup_ammo=5, shake=0.4, recoil=120,
                    knockback=520, explosion_radius=110, radius=5, kind="rocket", casing=None)
RAILGUN = WeaponSpec("railgun", "Railgun", (120, 200, 255), damage=150, cooldown=1.3, speed=0,
                     max_ammo=10, pickup_ammo=5, shake=0.7, recoil=320, knockback=500, pierce=99,
                     hitscan=True, casing=None)

WEAPON_LIST = [PISTOL, DUAL_PISTOLS, SMG, SHOTGUN, MACHINE_GUN, SNIPER, FLAMETHROWER, GRENADE_LAUNCHER,
               ROCKET, RAILGUN]
WEAPONS = {spec.key: spec for spec in WEAPON_LIST}
WEAPON_ORDER = [spec.key for spec in WEAPON_LIST]
# level map character -> weapon key
PICKUP_WEAPON = {"D": "dual_pistols", "U": "smg", "S": "shotgun", "M": "machinegun", "N": "sniper",
                 "F": "flamethrower", "L": "grenade_launcher", "R": "rocket", "Z": "railgun"}


class Projectile:
    def __init__(self, x: float, y: float, angle: float, speed: float, damage: float, owner: str,
                 lifetime: float, color: tuple, radius: float = 3.0, knockback: float = 100.0,
                 explosion_radius: float = 0.0, accel: float = 0.0, kind: str = "bullet",
                 pierce: int = 0, gravity: float = 0.0, bounce: float = 0.0, burn: float = 0.0) -> None:
        self.x = x
        self.y = y
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.damage = damage
        self.owner = owner  # "player" or "enemy"
        self.lifetime = lifetime
        self.age = 0.0
        self.color = color
        self.radius = radius
        self.knockback = knockback
        self.explosion_radius = explosion_radius
        self.accel = accel
        self.kind = kind
        self.pierce = pierce
        self.gravity = gravity
        self.bounce = bounce
        self.burn = burn
        self.hit_ids: Set[int] = set()
        self.alive = True
        self.hit_wall = False
        self.expired = False
        self.bounced = False  # true for the step in which it bounced
        self.prev_x = x
        self.prev_y = y
        self.spin = 0.0

    @property
    def speed(self) -> float:
        return math.hypot(self.vx, self.vy)

    @property
    def dir_x(self) -> float:
        s = self.speed
        return self.vx / s if s > 1e-9 else 1.0

    @property
    def dir_y(self) -> float:
        s = self.speed
        return self.vy / s if s > 1e-9 else 0.0

    @property
    def explosive(self) -> bool:
        return self.explosion_radius > 0.0

    def update(self, dt: float, level) -> None:
        """Move the projectile. Bullets die when they hit a solid tile,
        bouncing projectiles reflect. The path is sub-sampled so fast
        bullets cannot tunnel through a tile."""
        self.prev_x, self.prev_y = self.x, self.y
        self.bounced = False
        if self.accel:
            s0 = self.speed
            s1 = min(s0 + self.accel * dt, 1600.0)
            if s0 > 1e-9:
                self.vx *= s1 / s0
                self.vy *= s1 / s0
        self.vy += self.gravity * dt
        self.spin += self.vx * dt * 0.05
        dx, dy = self.vx * dt, self.vy * dt
        steps = max(1, int(math.ceil(max(abs(dx), abs(dy)) / (TILE * 0.25))))
        sx, sy = dx / steps, dy / steps
        for _ in range(steps):
            self.x += sx
            if level.solid_at(self.x, self.y):
                if self.bounce <= 0:
                    self.alive = False
                    self.hit_wall = True
                    return
                self.x -= sx
                sx *= -self.bounce
                self.vx *= -self.bounce
                self.vy *= 0.85
                self.bounced = True
            self.y += sy
            if level.solid_at(self.x, self.y):
                if self.bounce <= 0:
                    self.alive = False
                    self.hit_wall = True
                    return
                self.y -= sy
                sy *= -self.bounce
                self.vy *= -self.bounce
                self.vx *= 0.75
                if abs(self.vy) < 60:
                    self.vy = 0.0
                    sy = 0.0
                self.bounced = abs(self.vy) > 40 or self.bounced
        self.age += dt
        if self.age >= self.lifetime:
            self.alive = False
            self.expired = True
        if self.y > level.pixel_height + 200 or self.y < -600:
            self.alive = False


def make_projectile(spec: WeaponSpec, x: float, y: float, angle: float, owner: str, speed: float = None,
                    damage_scale: float = 1.0) -> Projectile:
    return Projectile(x, y, angle, spec.speed if speed is None else speed, spec.damage * damage_scale, owner,
                      spec.lifetime, spec.color, spec.radius, spec.knockback, spec.explosion_radius, spec.accel,
                      spec.kind, spec.pierce, spec.gravity, spec.bounce, spec.burn)


class Weapon:
    """A weapon in the player's inventory: spec + ammo + cooldown."""

    def __init__(self, spec: WeaponSpec, ammo: Optional[int] = None) -> None:
        self.spec = spec
        if spec.max_ammo is None:
            self.ammo: Optional[int] = None
        else:
            self.ammo = min(spec.max_ammo, spec.pickup_ammo if ammo is None else ammo)
        self.cooldown = 0.0
        self.shots_fired = 0

    @property
    def infinite(self) -> bool:
        return self.ammo is None

    @property
    def has_ammo(self) -> bool:
        return self.ammo is None or self.ammo > 0

    @property
    def full(self) -> bool:
        return self.ammo is None or self.ammo >= (self.spec.max_ammo or 0)

    def add_ammo(self, amount: int) -> int:
        """Add ammo up to the maximum; returns how much was actually added."""
        if self.ammo is None or self.spec.max_ammo is None:
            return 0
        before = self.ammo
        self.ammo = min(self.spec.max_ammo, self.ammo + amount)
        return self.ammo - before

    def tick(self, dt: float) -> None:
        self.cooldown = max(0.0, self.cooldown - dt)

    def can_fire(self) -> bool:
        return self.cooldown <= 0.0 and self.has_ammo

    def consume(self) -> bool:
        """Use one shot (cooldown + ammo). Returns False if it cannot fire."""
        if not self.can_fire():
            return False
        self.cooldown = self.spec.cooldown
        if self.ammo is not None:
            self.ammo -= 1
        self.shots_fired += 1
        return True

    def fire(self, x: float, y: float, angle: float, rng: random.Random,
             owner: str = "player") -> List[Projectile]:
        """Fire one shot if possible; returns the spawned projectiles
        (empty for hitscan weapons, which the world resolves itself)."""
        if not self.consume():
            return []
        spec = self.spec
        if spec.hitscan:
            return []
        if spec.dual:  # alternate between the two guns
            off = 4 if self.shots_fired % 2 else -4
            x += -math.sin(angle) * off
            y += math.cos(angle) * off
        shots = []
        for i in range(spec.pellets):
            a = angle
            if spec.pellets > 1:
                a += -spec.pellet_arc / 2 + spec.pellet_arc * i / (spec.pellets - 1)
            a += rng.uniform(-spec.spread, spec.spread)
            speed = spec.speed * (rng.uniform(0.9, 1.1) if spec.pellets > 1 or spec.kind == "flame" else 1.0)
            shots.append(make_projectile(spec, x, y, a, owner, speed))
        return shots


class Pickup:
    """An item floating in the level: a weapon, health pack or ammo crate."""

    W = 30
    H = 20

    def __init__(self, kind: str, tx: int, ty: int) -> None:
        self.kind = kind  # a weapon key, "health" or "ammo"
        self.x = tx * TILE + (TILE - self.W) / 2
        self.y = ty * TILE + TILE - self.H - 4
        self.alive = True
        self.phase = (tx * 0.73) % (2 * math.pi)

    @property
    def is_weapon(self) -> bool:
        return self.kind in WEAPONS

    @property
    def cx(self) -> float:
        return self.x + self.W / 2

    @property
    def cy(self) -> float:
        return self.y + self.H / 2
