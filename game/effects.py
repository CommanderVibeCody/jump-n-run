"""Particles, floating texts and screen shake."""
from __future__ import annotations

import math
import random
from typing import List, Tuple

MAX_PARTICLES = 900


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "size", "gravity", "drag", "glow")

    def __init__(self, x, y, vx, vy, life, color, size, gravity=0.0, drag=0.0, glow=False):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.color = color
        self.size = size
        self.gravity = gravity
        self.drag = drag
        self.glow = glow

    @property
    def t(self) -> float:
        """Remaining life fraction, 1 -> 0."""
        return max(0.0, self.life / self.max_life)


class FloatingText:
    def __init__(self, text: str, x: float, y: float, color, life: float = 1.0) -> None:
        self.text, self.x, self.y, self.color = text, x, y, color
        self.life = self.max_life = life


class Flash:
    """A short bright circle (muzzle flash, explosion core)."""

    def __init__(self, x: float, y: float, radius: float, color, life: float) -> None:
        self.x, self.y, self.radius, self.color = x, y, radius, color
        self.life = self.max_life = life


class Effects:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.particles: List[Particle] = []
        self.texts: List[FloatingText] = []
        self.flashes: List[Flash] = []
        self.trauma = 0.0  # 0..1, screen shake amount (decays)
        self.time = 0.0

    # ------------------------------------------------------------ spawning
    def burst(self, x: float, y: float, color, count: int = 10, speed: float = 200.0,
              life: float = 0.5, size: float = 3.0, gravity: float = 600.0, angle: float = None,
              arc: float = math.tau, drag: float = 1.5, glow: bool = False) -> None:
        r = self.rng
        for _ in range(count):
            if angle is None:
                a = r.uniform(0, math.tau)
            else:
                a = angle + r.uniform(-arc / 2, arc / 2)
            s = speed * r.uniform(0.35, 1.0)
            self.particles.append(Particle(x, y, math.cos(a) * s, math.sin(a) * s,
                                           life * r.uniform(0.6, 1.2), color,
                                           size * r.uniform(0.6, 1.3), gravity, drag, glow))
        if len(self.particles) > MAX_PARTICLES:
            del self.particles[: len(self.particles) - MAX_PARTICLES]

    def muzzle_flash(self, x: float, y: float, angle: float, color, big: bool = False) -> None:
        self.flashes.append(Flash(x, y, 14 if big else 9, (255, 240, 180), 0.06))
        self.burst(x, y, color, count=8 if big else 4, speed=380 if big else 260, life=0.12,
                   size=2.5, gravity=0, angle=angle, arc=0.7, glow=True)

    def impact(self, x: float, y: float, color) -> None:
        self.burst(x, y, color, count=7, speed=220, life=0.25, size=2.2, gravity=500, glow=True)
        self.burst(x, y, (200, 200, 200), count=3, speed=60, life=0.4, size=3, gravity=-40)

    def explosion(self, x: float, y: float, radius: float) -> None:
        self.flashes.append(Flash(x, y, radius * 0.9, (255, 230, 160), 0.18))
        self.burst(x, y, (255, 160, 60), count=40, speed=radius * 5, life=0.5, size=4, gravity=200, glow=True)
        self.burst(x, y, (255, 230, 120), count=20, speed=radius * 3, life=0.3, size=3, gravity=0, glow=True)
        self.burst(x, y, (90, 90, 95), count=18, speed=radius * 1.2, life=1.1, size=7, gravity=-60, drag=2.5)
        self.shake(0.6)

    def smoke(self, x: float, y: float) -> None:
        r = self.rng
        self.particles.append(Particle(x, y, r.uniform(-20, 20), r.uniform(-30, 0), r.uniform(0.3, 0.6),
                                       (170, 170, 175), r.uniform(3, 5), -50, 2.0))

    def dust(self, x: float, y: float, count: int = 6) -> None:
        self.burst(x, y, (220, 210, 190), count=count, speed=110, life=0.35, size=3, gravity=-80,
                   angle=-math.pi / 2, arc=math.pi * 1.2, drag=4.0)

    def text(self, text: str, x: float, y: float, color, life: float = 1.0) -> None:
        self.texts.append(FloatingText(text, x, y, color, life))

    def shake(self, amount: float) -> None:
        self.trauma = min(1.0, self.trauma + amount)

    # -------------------------------------------------------------- update
    def update(self, dt: float) -> None:
        self.time += dt
        self.trauma = max(0.0, self.trauma - dt * 1.8)
        alive = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0:
                continue
            p.vy += p.gravity * dt
            damp = max(0.0, 1.0 - p.drag * dt)
            p.vx *= damp
            p.vy *= damp
            p.x += p.vx * dt
            p.y += p.vy * dt
            alive.append(p)
        self.particles = alive
        for t in self.texts:
            t.life -= dt
            t.y -= 40 * dt
        self.texts = [t for t in self.texts if t.life > 0]
        for f in self.flashes:
            f.life -= dt
        self.flashes = [f for f in self.flashes if f.life > 0]

    def shake_offset(self, max_offset: float = 14.0) -> Tuple[float, float]:
        """Current camera offset. Uses trauma^2 so small hits barely shake."""
        s = self.trauma * self.trauma * max_offset
        if s <= 0.01:
            return 0.0, 0.0
        t = self.time
        ox = (math.sin(t * 71.0) + math.sin(t * 113.0 + 1.3)) * 0.5 * s
        oy = (math.sin(t * 89.0 + 2.1) + math.sin(t * 131.0 + 0.4)) * 0.5 * s
        return ox, oy
