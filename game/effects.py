"""Particles (with optional tile collision), blood and decals, shockwaves,
beams, floating texts and screen shake."""
from __future__ import annotations

import math
import random
from typing import List, Optional, Tuple

from .constants import TILE

MAX_PARTICLES = 1400
MAX_DECALS = 2500

# particle collision modes
NONE, BOUNCE, STICK = 0, 1, 2

BLOOD_COLORS = [(170, 10, 20), (200, 20, 30), (140, 0, 10), (220, 40, 40)]


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "size", "gravity", "drag", "glow",
                 "collide", "decal", "resting", "kind")

    def __init__(self, x, y, vx, vy, life, color, size, gravity=0.0, drag=0.0, glow=False,
                 collide=NONE, decal=False, kind="spark"):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.color = color
        self.size = size
        self.gravity = gravity
        self.drag = drag
        self.glow = glow
        self.collide = collide  # NONE, BOUNCE or STICK
        self.decal = decal      # leave a decal on the first contact
        self.resting = False
        self.kind = kind        # spark, blood, gib, casing, debris, smoke, fire

    @property
    def t(self) -> float:
        """Remaining life fraction, 1 -> 0."""
        return max(0.0, self.life / self.max_life)


class Decal:
    """A splat stuck to a floor, wall or ceiling (drawn permanently)."""

    __slots__ = ("x", "y", "radius", "color", "surface")

    def __init__(self, x, y, radius, color, surface):
        self.x, self.y, self.radius, self.color = x, y, radius, color
        self.surface = surface  # "floor", "ceiling", "left", "right"


class FloatingText:
    def __init__(self, text: str, x: float, y: float, color, life: float = 1.0) -> None:
        self.text, self.x, self.y, self.color = text, x, y, color
        self.life = self.max_life = life


class Flash:
    """A short bright circle (muzzle flash, explosion core)."""

    def __init__(self, x: float, y: float, radius: float, color, life: float) -> None:
        self.x, self.y, self.radius, self.color = x, y, radius, color
        self.life = self.max_life = life


class Ring:
    """An expanding shockwave ring."""

    def __init__(self, x: float, y: float, radius: float, life: float = 0.35, color=(255, 240, 200)) -> None:
        self.x, self.y, self.max_radius, self.color = x, y, radius, color
        self.life = self.max_life = life

    @property
    def radius(self) -> float:
        k = 1.0 - self.life / self.max_life
        return self.max_radius * (1 - (1 - k) ** 3)


class Beam:
    """A railgun beam from (x0, y0) to (x1, y1) that fades out."""

    def __init__(self, x0, y0, x1, y1, color, life: float = 0.3) -> None:
        self.x0, self.y0, self.x1, self.y1, self.color = x0, y0, x1, y1, color
        self.life = self.max_life = life


class Effects:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.particles: List[Particle] = []
        self.texts: List[FloatingText] = []
        self.flashes: List[Flash] = []
        self.rings: List[Ring] = []
        self.beams: List[Beam] = []
        self.decals: List[Decal] = []
        self.new_decals: List[Decal] = []  # not yet stamped by the renderer
        self.trauma = 0.0  # 0..1, screen shake amount (decays)
        self.time = 0.0

    # ------------------------------------------------------------ spawning
    def _add(self, p: Particle) -> None:
        self.particles.append(p)

    def _trim(self) -> None:
        if len(self.particles) > MAX_PARTICLES:
            del self.particles[: len(self.particles) - MAX_PARTICLES]

    def burst(self, x: float, y: float, color, count: int = 10, speed: float = 200.0,
              life: float = 0.5, size: float = 3.0, gravity: float = 600.0, angle: float = None,
              arc: float = math.tau, drag: float = 1.5, glow: bool = False, collide: int = NONE,
              decal: bool = False, kind: str = "spark") -> None:
        r = self.rng
        colors = color if isinstance(color, list) else [color]
        for _ in range(count):
            a = r.uniform(0, math.tau) if angle is None else angle + r.uniform(-arc / 2, arc / 2)
            s = speed * r.uniform(0.35, 1.0)
            self._add(Particle(x, y, math.cos(a) * s, math.sin(a) * s, life * r.uniform(0.6, 1.2),
                               r.choice(colors), size * r.uniform(0.6, 1.3), gravity, drag, glow,
                               collide, decal, kind))
        self._trim()

    def muzzle_flash(self, x: float, y: float, angle: float, color, big: bool = False) -> None:
        self.flashes.append(Flash(x, y, 16 if big else 10, (255, 240, 180), 0.06))
        self.burst(x, y, color, count=8 if big else 4, speed=380 if big else 260, life=0.12,
                   size=2.5, gravity=0, angle=angle, arc=0.7, glow=True)

    def casing(self, x: float, y: float, facing: int, color=(220, 180, 70)) -> None:
        r = self.rng
        self._add(Particle(x, y, -facing * r.uniform(60, 160), r.uniform(-320, -200), r.uniform(1.6, 2.4),
                           color, 2.2, 1500, 0.3, False, BOUNCE, False, "casing"))
        self._trim()

    def impact(self, x: float, y: float, color) -> None:
        self.burst(x, y, color, count=7, speed=220, life=0.25, size=2.2, gravity=500, glow=True)
        self.burst(x, y, (200, 200, 200), count=3, speed=60, life=0.4, size=3, gravity=-40)

    def blood(self, x: float, y: float, dir_x: float, dir_y: float, amount: int = 12, force: float = 1.0) -> None:
        """Spray blood in the hit direction; drops stick where they land."""
        angle = math.atan2(dir_y, dir_x) if (dir_x or dir_y) else -math.pi / 2
        self.burst(x, y, BLOOD_COLORS, count=amount, speed=380 * force, life=1.6, size=2.6, gravity=1200,
                   angle=angle, arc=1.1, drag=0.6, collide=STICK, decal=True, kind="blood")
        self.burst(x, y, BLOOD_COLORS, count=max(2, amount // 3), speed=120, life=0.6, size=2.0, gravity=900,
                   drag=1.0, collide=STICK, decal=True, kind="blood")

    def gibs(self, x: float, y: float, colors, count: int = 10) -> None:
        """Chunks flying out of an exploded enemy, leaving blood trails."""
        r = self.rng
        for _ in range(count):
            a = r.uniform(-math.pi * 0.95, -math.pi * 0.05)
            s = r.uniform(250, 650)
            self._add(Particle(x, y, math.cos(a) * s, math.sin(a) * s, r.uniform(2.5, 4.0), r.choice(colors),
                               r.uniform(3.5, 6.5), 1300, 0.3, False, BOUNCE, True, "gib"))
        self.blood(x, y, 0, -1, 30, 1.4)
        self._trim()

    def explosion(self, x: float, y: float, radius: float) -> None:
        r = self.rng
        self.flashes.append(Flash(x, y, radius * 1.1, (255, 230, 160), 0.22))
        self.rings.append(Ring(x, y, radius * 1.7, 0.4))
        self.rings.append(Ring(x, y, radius * 1.1, 0.25, (255, 180, 90)))
        self.burst(x, y, [(255, 160, 60), (255, 110, 40), (255, 210, 90)], count=55, speed=radius * 6,
                   life=0.55, size=4.5, gravity=200, glow=True, kind="fire")
        self.burst(x, y, (255, 240, 160), count=24, speed=radius * 9, life=0.25, size=2.5, gravity=0, glow=True)
        # rising smoke
        for _ in range(26):
            a = r.uniform(0, math.tau)
            s = r.uniform(20, radius * 1.6)
            self._add(Particle(x + math.cos(a) * radius * 0.3, y + math.sin(a) * radius * 0.3, math.cos(a) * s,
                               math.sin(a) * s - 40, r.uniform(1.0, 2.0), r.choice([(70, 70, 75), (95, 95, 100), (55, 55, 60)]),
                               r.uniform(8, 15), -90, 2.2, False, NONE, False, "smoke"))
        # debris chunks that bounce off the floor
        self.burst(x, y, [(80, 70, 60), (60, 55, 50), (120, 100, 80)], count=18, speed=radius * 6, life=2.2,
                   size=3.5, gravity=1400, angle=-math.pi / 2, arc=math.pi * 1.3, drag=0.3, collide=BOUNCE,
                   kind="debris")
        self.shake(0.9)
        self._trim()

    def smoke(self, x: float, y: float) -> None:
        r = self.rng
        self._add(Particle(x, y, r.uniform(-20, 20), r.uniform(-30, 0), r.uniform(0.3, 0.6),
                           (170, 170, 175), r.uniform(3, 5), -50, 2.0, kind="smoke"))

    def fire(self, x: float, y: float) -> None:
        r = self.rng
        self._add(Particle(x, y, r.uniform(-30, 30), r.uniform(-120, -40), r.uniform(0.2, 0.45),
                           r.choice([(255, 140, 40), (255, 90, 30), (255, 200, 80)]), r.uniform(3, 6), -200, 1.0,
                           True, kind="fire"))

    def dust(self, x: float, y: float, count: int = 6) -> None:
        self.burst(x, y, (220, 210, 190), count=count, speed=110, life=0.35, size=3, gravity=-80,
                   angle=-math.pi / 2, arc=math.pi * 1.2, drag=4.0)

    def beam(self, x0, y0, x1, y1, color) -> None:
        self.beams.append(Beam(x0, y0, x1, y1, color))
        n = int(math.hypot(x1 - x0, y1 - y0) / 24)
        for i in range(n):
            t = i / max(1, n)
            self.burst(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, color, count=1, speed=40, life=0.4, size=2,
                       gravity=0, glow=True)

    def text(self, text: str, x: float, y: float, color, life: float = 1.0) -> None:
        self.texts.append(FloatingText(text, x, y, color, life))

    def shake(self, amount: float) -> None:
        self.trauma = min(1.0, self.trauma + amount)

    def add_decal(self, x: float, y: float, radius: float, color, surface: str) -> None:
        d = Decal(x, y, radius, color, surface)
        self.decals.append(d)
        self.new_decals.append(d)
        if len(self.decals) > MAX_DECALS:
            del self.decals[: len(self.decals) - MAX_DECALS]
        if len(self.new_decals) > MAX_DECALS:  # nobody is drawing them (headless)
            del self.new_decals[: len(self.new_decals) - MAX_DECALS]

    # -------------------------------------------------------------- update
    def update(self, dt: float, level=None) -> None:
        self.time += dt
        self.trauma = max(0.0, self.trauma - dt * 1.6)
        alive = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0:
                continue
            if p.resting:
                alive.append(p)
                continue
            p.vy += p.gravity * dt
            damp = max(0.0, 1.0 - p.drag * dt)
            p.vx *= damp
            p.vy *= damp
            if p.collide and level is not None:
                if self._move_colliding(p, dt, level):
                    continue  # stuck and removed
            else:
                p.x += p.vx * dt
                p.y += p.vy * dt
            alive.append(p)
        self.particles = alive
        for t in self.texts:
            t.life -= dt
            t.y -= 40 * dt
        self.texts = [t for t in self.texts if t.life > 0]
        for group in (self.flashes, self.rings, self.beams):
            for f in group:
                f.life -= dt
        self.flashes = [f for f in self.flashes if f.life > 0]
        self.rings = [f for f in self.rings if f.life > 0]
        self.beams = [f for f in self.beams if f.life > 0]

    def _move_colliding(self, p: Particle, dt: float, level) -> bool:
        """Move a colliding particle. Returns True if it should be removed."""
        nx = p.x + p.vx * dt
        if level.solid_at(nx, p.y):
            if p.decal:
                edge = math.floor(nx / TILE) * TILE if p.vx > 0 else (math.floor(nx / TILE) + 1) * TILE
                self.add_decal(edge, p.y, p.size * 1.1, p.color, "left" if p.vx > 0 else "right")
            if p.collide == STICK:
                return True
            p.vx *= -0.4
            p.decal = False
        else:
            p.x = nx
        ny = p.y + p.vy * dt
        if level.solid_at(p.x, ny):
            if p.vy > 0:
                top = math.floor(ny / TILE) * TILE
                if p.decal:
                    self.add_decal(p.x, top, p.size * 1.3, p.color, "floor")
                if p.collide == STICK:
                    return True
                p.y = top - 0.5
                p.vy *= -0.35
                p.vx *= 0.6
                p.decal = False
                if abs(p.vy) < 50:
                    p.vy = 0.0
                    if abs(p.vx) < 20:
                        p.resting = True
            else:
                if p.decal:
                    self.add_decal(p.x, (math.floor(ny / TILE) + 1) * TILE, p.size, p.color, "ceiling")
                if p.collide == STICK:
                    return True
                p.vy = abs(p.vy) * 0.3
        else:
            p.y = ny
        return False

    def shake_offset(self, max_offset: float = 22.0) -> Tuple[float, float]:
        """Current camera offset. Uses trauma^2 so small hits barely shake."""
        s = self.trauma * self.trauma * max_offset
        if s <= 0.01:
            return 0.0, 0.0
        t = self.time
        ox = (math.sin(t * 71.0) + math.sin(t * 113.0 + 1.3)) * 0.5 * s
        oy = (math.sin(t * 89.0 + 2.1) + math.sin(t * 131.0 + 0.4)) * 0.5 * s
        return ox, oy
