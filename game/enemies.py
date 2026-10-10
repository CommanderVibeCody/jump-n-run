"""Enemies: walkers that patrol, shooters that fire at the player and
flying drones that chase the player."""
from __future__ import annotations

import math
import random
from typing import List

from .constants import FIXED_DT, GRAVITY, MAX_FALL_SPEED, TILE
from .physics import Body, approach, integrate
from .weapons import Projectile


class Enemy:
    kind = "enemy"
    W, H = 26, 30
    MAX_HEALTH = 50
    CONTACT_DAMAGE = 20
    SCORE = 100

    def __init__(self, tx: int, ty: int) -> None:
        x = tx * TILE + (TILE - self.W) / 2
        y = (ty + 1) * TILE - self.H
        self.body = Body(x, y, self.W, self.H)
        self.health = float(self.MAX_HEALTH)
        self.alive = True
        self.facing = -1
        self.hurt_flash = 0.0
        self.stun = 0.0
        self.anim = random.Random(tx * 31 + ty).uniform(0, 10)

    def take_damage(self, amount: float, knock_x: float = 0.0, knock_y: float = 0.0) -> bool:
        """Apply damage and knockback. Returns True if this killed the enemy."""
        if not self.alive:
            return False
        self.health -= amount
        self.hurt_flash = 0.12
        self.body.vx += knock_x
        self.body.vy += knock_y
        self.stun = 0.15
        if self.health <= 0:
            self.health = 0
            self.alive = False
            return True
        return False

    def update(self, dt: float, level, player, rng: random.Random) -> List[Projectile]:
        self.hurt_flash = max(0.0, self.hurt_flash - dt)
        self.stun = max(0.0, self.stun - dt)
        self.anim += dt
        return []

    def _fall(self, dt: float, level, target_vx: float, accel: float) -> None:
        vx = approach(self.body.vx, target_vx, accel * dt)
        integrate(self.body, level, (vx - self.body.vx) / dt, GRAVITY * 1.3, dt, max_fall=MAX_FALL_SPEED)
        if self.body.y > level.pixel_height + 200:
            self.alive = False


class Walker(Enemy):
    """Patrols back and forth, turning at walls and ledges."""

    kind = "walker"
    W, H = 28, 28
    MAX_HEALTH = 50
    CONTACT_DAMAGE = 20
    SPEED = 75.0
    SCORE = 100

    def update(self, dt, level, player, rng):
        super().update(dt, level, player, rng)
        b = self.body
        if b.on_ground and self.stun <= 0.0:
            # ledge check: is there floor under the front foot?
            front_x = b.right + 2 if self.facing > 0 else b.left - 2
            tx = math.floor(front_x / TILE)
            ty = math.floor((b.bottom + 2) / TILE)
            if not (level.is_solid(tx, ty) or level.is_one_way(tx, ty)):
                self.facing *= -1
        target = 0.0 if self.stun > 0 else self.facing * self.SPEED
        self._fall(dt, level, target, 900.0 if self.stun <= 0 else 600.0)
        if (b.hit_left and self.facing < 0) or (b.hit_right and self.facing > 0):
            self.facing *= -1
        return []


class Shooter(Enemy):
    """Stands guard and fires at the player when it can see them."""

    kind = "shooter"
    W, H = 26, 36
    MAX_HEALTH = 70
    CONTACT_DAMAGE = 15
    SCORE = 150
    RANGE = 460.0
    COOLDOWN = 1.5
    WINDUP = 0.35
    BULLET_SPEED = 430.0
    BULLET_DAMAGE = 12

    def __init__(self, tx: int, ty: int) -> None:
        super().__init__(tx, ty)
        self.cooldown = 1.0
        self.windup = 0.0
        self.sees_player = False

    def can_see(self, level, player) -> bool:
        b, p = self.body, player.body
        dx, dy = p.cx - b.cx, p.cy - b.cy
        if abs(dx) > self.RANGE or abs(dy) > 220 or not player.alive:
            return False
        return level.line_of_sight(b.cx, b.y + 12, p.cx, p.cy)

    def update(self, dt, level, player, rng):
        super().update(dt, level, player, rng)
        self._fall(dt, level, 0.0, 1200.0)
        self.sees_player = self.can_see(level, player)
        self.cooldown = max(0.0, self.cooldown - dt)
        shots: List[Projectile] = []
        if self.sees_player:
            self.facing = 1 if player.body.cx > self.body.cx else -1
            if self.cooldown <= 0.0 and self.windup <= 0.0:
                self.windup = self.WINDUP
        if self.windup > 0.0:
            self.windup -= dt
            if self.windup <= 0.0:
                self.cooldown = self.COOLDOWN
                if self.sees_player:
                    gx, gy = self.gun_pos()
                    angle = math.atan2(player.body.cy - gy, player.body.cx - gx) + rng.uniform(-0.05, 0.05)
                    shots.append(Projectile(gx, gy, angle, self.BULLET_SPEED, self.BULLET_DAMAGE, "enemy",
                                            2.0, (255, 90, 120), radius=4, knockback=180))
        return shots

    def gun_pos(self):
        return self.body.cx + self.facing * 18, self.body.y + 14


class Drone(Enemy):
    """Hovers around its home point and chases the player when close."""

    kind = "drone"
    W, H = 30, 20
    MAX_HEALTH = 35
    CONTACT_DAMAGE = 15
    SCORE = 120
    SPEED = 120.0
    RANGE = 380.0

    def __init__(self, tx: int, ty: int) -> None:
        super().__init__(tx, ty)
        self.body.y = ty * TILE + (TILE - self.H) / 2
        self.home = (self.body.x, self.body.y)
        self.chasing = False

    def update(self, dt, level, player, rng):
        super().update(dt, level, player, rng)
        b, p = self.body, player.body
        dist = math.hypot(p.cx - b.cx, p.cy - b.cy)
        self.chasing = (player.alive and dist < self.RANGE
                        and level.line_of_sight(b.cx, b.cy, p.cx, p.cy))
        if self.chasing:
            tx, ty = p.cx - b.w / 2, p.y - 50
        else:
            tx = self.home[0] + math.sin(self.anim * 0.8) * 40
            ty = self.home[1] + math.sin(self.anim * 2.1) * 10
        dx, dy = tx - b.x, ty - b.y
        d = math.hypot(dx, dy)
        if d > 1:
            speed = self.SPEED if self.chasing else 70.0
            want_vx, want_vy = dx / d * min(speed, d * 3), dy / d * min(speed, d * 3)
        else:
            want_vx = want_vy = 0.0
        rate = 300.0 if self.stun <= 0 else 150.0
        vx = approach(b.vx, want_vx, rate * dt)
        vy = approach(b.vy, want_vy, rate * dt)
        integrate(b, level, (vx - b.vx) / dt, (vy - b.vy) / dt, dt)
        if abs(b.vx) > 5:
            self.facing = 1 if b.vx > 0 else -1
        return []


ENEMY_TYPES = {"w": Walker, "s": Shooter, "d": Drone}


def make_enemy(kind: str, tx: int, ty: int) -> Enemy:
    return ENEMY_TYPES[kind](tx, ty)
