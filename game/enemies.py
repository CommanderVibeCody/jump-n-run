"""Enemies: blob walkers, human soldiers (rifleman, shotgunner, grenadier,
heavy and stationary guards) and flying drones. Also explosive barrels and
ragdoll-style corpses."""
from __future__ import annotations

import math
import random
from typing import List, Optional

from .constants import GRAVITY, MAX_FALL_SPEED, TILE
from .physics import Body, approach, integrate
from .weapons import Projectile

BULLET_COLOR = (255, 90, 120)


class Enemy:
    kind = "enemy"
    human = False
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
        self.burn = 0.0
        self.anim = random.Random(tx * 31 + ty).uniform(0, 10)
        self.aim_angle = math.pi
        self.last_knock = (0.0, 0.0)

    def take_damage(self, amount: float, knock_x: float = 0.0, knock_y: float = 0.0) -> bool:
        """Apply damage and knockback. Returns True if this killed the enemy."""
        if not self.alive:
            return False
        self.health -= amount
        self.hurt_flash = 0.12
        self.body.vx += knock_x
        self.body.vy += knock_y
        self.last_knock = (knock_x, knock_y)
        if abs(knock_x) > 20:
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

    def ledge_ahead(self, level) -> bool:
        b = self.body
        front_x = b.right + 2 if self.facing > 0 else b.left - 2
        tx = math.floor(front_x / TILE)
        ty = math.floor((b.bottom + 2) / TILE)
        return not (level.is_solid(tx, ty) or level.is_one_way(tx, ty))


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
        if b.on_ground and self.stun <= 0.0 and self.ledge_ahead(level):
            self.facing *= -1
        target = 0.0 if self.stun > 0 else self.facing * self.SPEED
        self._fall(dt, level, target, 900.0 if self.stun <= 0 else 600.0)
        if (b.hit_left and self.facing < 0) or (b.hit_right and self.facing > 0):
            self.facing *= -1
        return []


class Soldier(Enemy):
    """A human soldier: patrols, and when it spots the player it stops, aims
    its gun arm and attacks with its variant's weapon."""

    kind = "soldier"
    human = True
    W, H = 22, 42
    MAX_HEALTH = 60
    CONTACT_DAMAGE = 10
    SCORE = 150
    PATROL_SPEED = 60.0
    RANGE = 460.0
    COOLDOWN = 1.6
    WINDUP = 0.35
    BULLET_SPEED = 520.0
    BULLET_DAMAGE = 9
    BURST = 3             # shots per attack
    BURST_INTERVAL = 0.11
    SPREAD = 0.06
    PELLETS = 1
    GUN = "machinegun"
    PALETTE = {"uniform": (80, 110, 60), "dark": (55, 75, 40), "helmet": (70, 95, 50), "skin": (230, 190, 150)}
    SCALE = 1.0

    def __init__(self, tx: int, ty: int) -> None:
        super().__init__(tx, ty)
        self.cooldown = 0.8 + random.Random(tx * 7 + ty).uniform(0, 0.8)
        self.windup = 0.0
        self.burst_left = 0
        self.burst_timer = 0.0
        self.sees_player = False
        self.walk_phase = 0.0
        self.muzzle_flash = 0.0

    def can_see(self, level, player) -> bool:
        b, p = self.body, player.body
        dx, dy = p.cx - b.cx, p.cy - b.cy
        if abs(dx) > self.RANGE or abs(dy) > 240 or not player.alive:
            return False
        if self.PATROL_SPEED > 0 and dx * self.facing < -40 and abs(dx) > 160:
            return False  # patrolling soldiers only see what is in front of them
        return level.line_of_sight(b.cx, b.y + 12, p.cx, p.cy)

    def gun_pos(self):
        sx, sy = self.shoulder()
        return sx + math.cos(self.aim_angle) * 22 * self.SCALE, sy + math.sin(self.aim_angle) * 22 * self.SCALE

    def shoulder(self):
        return self.body.cx, self.body.y + 14 * self.SCALE

    def update(self, dt, level, player, rng):
        super().update(dt, level, player, rng)
        b = self.body
        self.muzzle_flash = max(0.0, self.muzzle_flash - dt)
        was_seeing = self.sees_player
        self.sees_player = self.can_see(level, player)
        self.cooldown = max(0.0, self.cooldown - dt)
        attacking = self.sees_player or self.windup > 0 or self.burst_left > 0
        target_vx = 0.0
        if not attacking and self.stun <= 0 and self.PATROL_SPEED > 0:
            if b.on_ground and self.ledge_ahead(level):
                self.facing *= -1
            target_vx = self.facing * self.PATROL_SPEED
        self._fall(dt, level, target_vx, 700.0)
        if (b.hit_left and self.facing < 0) or (b.hit_right and self.facing > 0):
            self.facing *= -1
        if b.on_ground and abs(b.vx) > 5:
            self.walk_phase += abs(b.vx) * dt * 0.09
        # aim
        if self.sees_player:
            self.facing = 1 if player.body.cx > b.cx else -1
            sx, sy = self.shoulder()
            target = math.atan2(player.body.cy - sy, player.body.cx - sx)
        else:
            target = 0.25 if self.facing > 0 else math.pi - 0.25  # gun lowered
        diff = (target - self.aim_angle + math.pi) % math.tau - math.pi
        self.aim_angle += diff * min(1.0, dt * 10)
        if not was_seeing and self.sees_player and self.cooldown < 0.4:
            self.cooldown = 0.4  # short reaction time
        shots: List[Projectile] = []
        if self.sees_player and self.cooldown <= 0.0 and self.windup <= 0.0 and self.burst_left == 0:
            self.windup = self.WINDUP
        if self.windup > 0.0:
            self.windup -= dt
            if self.windup <= 0.0:
                self.burst_left = self.BURST
                self.burst_timer = 0.0
        if self.burst_left > 0:
            self.burst_timer -= dt
            if self.burst_timer <= 0.0:
                self.burst_timer = self.BURST_INTERVAL
                self.burst_left -= 1
                if self.burst_left == 0:
                    self.cooldown = self.COOLDOWN
                shots += self.fire(player, rng)
                if shots:
                    self.muzzle_flash = 0.06
        return shots

    def fire(self, player, rng) -> List[Projectile]:
        gx, gy = self.gun_pos()
        angle = self.aim_angle
        out = []
        for i in range(self.PELLETS):
            a = angle + rng.uniform(-self.SPREAD, self.SPREAD)
            if self.PELLETS > 1:
                a += -0.25 + 0.5 * i / (self.PELLETS - 1)
            out.append(Projectile(gx, gy, a, self.BULLET_SPEED, self.BULLET_DAMAGE, "enemy",
                                  2.0 if self.PELLETS == 1 else 0.5, BULLET_COLOR, radius=4, knockback=160))
        return out


class Rifleman(Soldier):
    kind = "rifleman"


class Shotgunner(Soldier):
    kind = "shotgunner"
    MAX_HEALTH = 80
    RANGE = 300.0
    COOLDOWN = 1.7
    BURST = 1
    PELLETS = 5
    BULLET_DAMAGE = 8
    BULLET_SPEED = 560.0
    GUN = "shotgun"
    PALETTE = {"uniform": (150, 120, 80), "dark": (110, 85, 55), "helmet": (120, 95, 60), "skin": (210, 160, 120)}


class Grenadier(Soldier):
    kind = "grenadier"
    MAX_HEALTH = 70
    RANGE = 520.0
    COOLDOWN = 2.2
    BURST = 1
    WINDUP = 0.5
    GUN = "grenade_launcher"
    SCORE = 180
    PALETTE = {"uniform": (60, 70, 85), "dark": (40, 48, 60), "helmet": (150, 40, 40), "skin": (235, 200, 160)}

    def fire(self, player, rng) -> List[Projectile]:
        gx, gy = self.gun_pos()
        dx = player.body.cx - gx
        dy = player.body.cy - gy
        g = 1300.0
        t = max(0.6, min(1.3, abs(dx) / 380))
        vx = dx / t
        vy = (dy - 0.5 * g * t * t) / t
        speed = math.hypot(vx, vy)
        self.aim_angle = math.atan2(vy, vx)
        return [Projectile(gx, gy, self.aim_angle, speed, 40, "enemy", t + 0.25, (120, 200, 80), radius=5,
                           knockback=400, explosion_radius=80, kind="grenade", gravity=g, bounce=0.45)]


class Heavy(Soldier):
    """Big soldier with a minigun: spins up, then sprays bullets."""

    kind = "heavy"
    W, H = 30, 52
    SCALE = 1.25
    MAX_HEALTH = 240
    CONTACT_DAMAGE = 20
    SCORE = 400
    PATROL_SPEED = 30.0
    RANGE = 480.0
    COOLDOWN = 2.0
    WINDUP = 0.7
    BURST = 18
    BURST_INTERVAL = 0.07
    SPREAD = 0.14
    BULLET_DAMAGE = 6
    BULLET_SPEED = 600.0
    GUN = "minigun"
    PALETTE = {"uniform": (90, 90, 100), "dark": (60, 60, 70), "helmet": (50, 50, 55), "skin": (200, 150, 110)}

    def take_damage(self, amount, knock_x=0.0, knock_y=0.0):
        return super().take_damage(amount, knock_x * 0.3, knock_y * 0.3)


class Shooter(Soldier):
    """A stationary guard that fires single shots when it sees the player."""

    kind = "shooter"
    W, H = 22, 42
    MAX_HEALTH = 70
    CONTACT_DAMAGE = 15
    SCORE = 150
    PATROL_SPEED = 0.0
    RANGE = 460.0
    COOLDOWN = 1.5
    WINDUP = 0.35
    BURST = 1
    BULLET_SPEED = 430.0
    BULLET_DAMAGE = 12
    SPREAD = 0.05
    GUN = "pistol"
    PALETTE = {"uniform": (70, 60, 120), "dark": (50, 40, 90), "helmet": (40, 40, 60), "skin": (230, 190, 150)}

    def __init__(self, tx: int, ty: int) -> None:
        super().__init__(tx, ty)
        self.cooldown = 1.0


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


ENEMY_TYPES = {"w": Walker, "s": Shooter, "d": Drone, "r": Rifleman, "k": Shotgunner, "g": Grenadier,
               "h": Heavy}


def make_enemy(kind: str, tx: int, ty: int) -> Enemy:
    return ENEMY_TYPES[kind](tx, ty)


class Barrel:
    """An explosive barrel. When destroyed it explodes after a short fuse,
    which lets explosions chain through groups of barrels."""

    W, H = 24, 30
    MAX_HEALTH = 30
    FUSE = 0.14
    RADIUS = 120.0
    DAMAGE = 110.0

    def __init__(self, tx: int, ty: int) -> None:
        self.body = Body(tx * TILE + (TILE - self.W) / 2, (ty + 1) * TILE - self.H, self.W, self.H)
        self.health = float(self.MAX_HEALTH)
        self.fuse = -1.0   # < 0: not triggered
        self.alive = True
        self.hurt_flash = 0.0

    @property
    def triggered(self) -> bool:
        return self.fuse >= 0

    def take_damage(self, amount: float) -> None:
        if not self.alive:
            return
        self.health -= amount
        self.hurt_flash = 0.1
        if self.health <= 0 and not self.triggered:
            self.fuse = self.FUSE

    def update(self, dt: float, level) -> bool:
        """Returns True when the barrel explodes this step."""
        self.hurt_flash = max(0.0, self.hurt_flash - dt)
        integrate(self.body, level, 0.0, GRAVITY, dt, max_fall=MAX_FALL_SPEED)
        self.body.vx *= 0.9
        if self.triggered:
            self.fuse -= dt
            if self.fuse <= 0:
                self.alive = False
                return True
        return False


class Corpse:
    """A dead soldier: flies back from the hit, tumbles and comes to rest."""

    def __init__(self, enemy: Enemy, vx: float, vy: float, spin: float) -> None:
        b = enemy.body
        self.body = Body(b.x, b.y + b.h - 14, b.w, 14)
        self.body.vx = vx
        self.body.vy = vy
        self.kind = enemy.kind
        self.palette = getattr(enemy, "PALETTE", None)
        self.gun = getattr(enemy, "GUN", "pistol")
        self.scale = getattr(enemy, "SCALE", 1.0)
        self.facing = enemy.facing
        self.angle = 0.0
        self.spin = spin
        self.life = 9.0
        self.burning = enemy.burn > 0

    def update(self, dt: float, level) -> None:
        self.life -= dt
        b = self.body
        if b.on_ground:
            b.vx = approach(b.vx, 0.0, 1400 * dt)
            # settle flat on the back or the belly
            target = math.pi / 2 if (self.angle % math.tau) < math.pi else 3 * math.pi / 2
            base = self.angle - (self.angle % math.tau)
            self.angle += ((base + target) - self.angle) * min(1.0, dt * 12)
            self.spin = 0.0
        else:
            self.angle += self.spin * dt
        integrate(b, level, 0.0, GRAVITY * 1.2, dt, max_fall=MAX_FALL_SPEED)
