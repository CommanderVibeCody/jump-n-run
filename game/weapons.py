"""Weapons, projectiles and pickups."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Optional

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


PISTOL = WeaponSpec("pistol", "Pistol", (250, 230, 120), damage=25, cooldown=0.28, speed=950,
                    spread=0.02, lifetime=1.0, shake=0.12, recoil=20)
SHOTGUN = WeaponSpec("shotgun", "Shotgun", (255, 170, 80), damage=14, cooldown=0.75, speed=820,
                     spread=0.05, pellets=6, pellet_arc=0.42, lifetime=0.38, max_ammo=24,
                     pickup_ammo=12, shake=0.35, recoil=260, knockback=200, radius=2.5)
MACHINE_GUN = WeaponSpec("machinegun", "Machine Gun", (120, 230, 255), damage=11, cooldown=0.075,
                         speed=1050, spread=0.07, lifetime=0.9, max_ammo=180, pickup_ammo=90,
                         shake=0.1, recoil=35, knockback=60, radius=2.5)
ROCKET = WeaponSpec("rocket", "Rocket Launcher", (255, 100, 90), damage=90, cooldown=0.9, speed=320,
                    accel=1100, lifetime=2.5, max_ammo=10, pickup_ammo=5, shake=0.3, recoil=120,
                    knockback=450, explosion_radius=90, radius=5)

WEAPONS = {spec.key: spec for spec in (PISTOL, SHOTGUN, MACHINE_GUN, ROCKET)}
WEAPON_ORDER = ["pistol", "shotgun", "machinegun", "rocket"]
PICKUP_WEAPON = {"S": "shotgun", "M": "machinegun", "R": "rocket"}


class Projectile:
    def __init__(self, x: float, y: float, angle: float, speed: float, damage: float, owner: str,
                 lifetime: float, color: tuple, radius: float = 3.0, knockback: float = 100.0,
                 explosion_radius: float = 0.0, accel: float = 0.0, kind: str = "bullet") -> None:
        self.x = x
        self.y = y
        self.dir_x = math.cos(angle)
        self.dir_y = math.sin(angle)
        self.speed = speed
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
        self.alive = True
        self.hit_wall = False
        self.prev_x = x
        self.prev_y = y

    @property
    def vx(self) -> float:
        return self.dir_x * self.speed

    @property
    def vy(self) -> float:
        return self.dir_y * self.speed

    @property
    def explosive(self) -> bool:
        return self.explosion_radius > 0.0

    def update(self, dt: float, level) -> None:
        """Move the projectile; it dies when it hits a solid tile or expires.

        The path is sub-sampled so that even fast bullets cannot tunnel
        through a tile."""
        self.prev_x, self.prev_y = self.x, self.y
        v0 = self.speed
        self.speed = min(v0 + self.accel * dt, 1600.0)
        dist = (v0 + self.speed) * 0.5 * dt
        steps = max(1, int(math.ceil(dist / (TILE * 0.25))))
        for _ in range(steps):
            self.x += self.dir_x * dist / steps
            self.y += self.dir_y * dist / steps
            if level.solid_at(self.x, self.y):
                self.alive = False
                self.hit_wall = True
                return
        self.age += dt
        if self.age >= self.lifetime:
            self.alive = False
        if self.y > level.pixel_height + 200 or self.y < -400:
            self.alive = False


class Weapon:
    """A weapon in the player's inventory: spec + ammo + cooldown."""

    def __init__(self, spec: WeaponSpec, ammo: Optional[int] = None) -> None:
        self.spec = spec
        if spec.max_ammo is None:
            self.ammo: Optional[int] = None
        else:
            self.ammo = min(spec.max_ammo, spec.pickup_ammo if ammo is None else ammo)
        self.cooldown = 0.0

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

    def fire(self, x: float, y: float, angle: float, rng: random.Random,
             owner: str = "player") -> List[Projectile]:
        """Fire one shot if possible; returns the spawned projectiles."""
        if not self.can_fire():
            return []
        spec = self.spec
        self.cooldown = spec.cooldown
        if self.ammo is not None:
            self.ammo -= 1
        shots = []
        for i in range(spec.pellets):
            a = angle
            if spec.pellets > 1:
                a += -spec.pellet_arc / 2 + spec.pellet_arc * i / (spec.pellets - 1)
            a += rng.uniform(-spec.spread, spec.spread)
            speed = spec.speed * (rng.uniform(0.9, 1.1) if spec.pellets > 1 else 1.0)
            shots.append(Projectile(x, y, a, speed, spec.damage, owner, spec.lifetime, spec.color,
                                    spec.radius, spec.knockback, spec.explosion_radius, spec.accel,
                                    kind="rocket" if spec.explosion_radius else "bullet"))
        return shots


class Pickup:
    """An item floating in the level: a weapon, health pack or ammo crate."""

    W = 26
    H = 20

    def __init__(self, kind: str, tx: int, ty: int) -> None:
        self.kind = kind  # "shotgun", "machinegun", "rocket", "health" or "ammo"
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
