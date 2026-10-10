"""Hand-written 2D platformer physics: axis-aligned boxes against a tile grid.

There is no physics library. Bodies are integrated with a fixed timestep
(see ``constants.FIXED_DT``) using the constant-acceleration update

    x(t + dt) = x(t) + (v(t) + v(t + dt)) / 2 * dt

which is exact for piecewise-constant acceleration (gravity, run
acceleration, friction) and identical to velocity Verlet in that case.

Collisions are resolved one axis at a time ("move X, resolve, move Y,
resolve"). Because every body is clamped to ``MAX_SPEED`` the motion per step
is always smaller than one tile, so only the tiles at the leading edge have
to be checked.
"""
from __future__ import annotations

import math
from typing import Iterator, Protocol

from .constants import MAX_SPEED, TILE

EPS = 1e-6
ONE_WAY_TOLERANCE = 0.5  # px; how far below a platform top the feet may start


class TileGrid(Protocol):
    """The part of a level that the physics needs."""

    def is_solid(self, tx: int, ty: int) -> bool: ...

    def is_one_way(self, tx: int, ty: int) -> bool: ...


class Body:
    """An axis-aligned box with position (top-left corner) and velocity."""

    def __init__(self, x: float, y: float, w: float, h: float) -> None:
        self.x = float(x)
        self.y = float(y)
        self.w = float(w)
        self.h = float(h)
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.hit_left = False
        self.hit_right = False
        self.hit_ceiling = False

    # convenience accessors
    @property
    def left(self) -> float:
        return self.x

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def top(self) -> float:
        return self.y

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w * 0.5

    @property
    def cy(self) -> float:
        return self.y + self.h * 0.5

    def overlaps(self, other: "Body") -> bool:
        return aabb_overlap(self.x, self.y, self.w, self.h, other.x, other.y, other.w, other.h)

    def contains_point(self, px: float, py: float, margin: float = 0.0) -> bool:
        return (self.x - margin <= px <= self.x + self.w + margin
                and self.y - margin <= py <= self.y + self.h + margin)


def aabb_overlap(ax: float, ay: float, aw: float, ah: float,
                 bx: float, by: float, bw: float, bh: float) -> bool:
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def tile_range(start: float, size: float) -> Iterator[int]:
    """Indices of all tiles overlapped by the interval [start, start + size)."""
    first = math.floor(start / TILE)
    last = math.floor((start + size - EPS) / TILE)
    return iter(range(first, last + 1))


def clamp_velocity(body: Body) -> None:
    body.vx = max(-MAX_SPEED, min(MAX_SPEED, body.vx))
    body.vy = max(-MAX_SPEED, min(MAX_SPEED, body.vy))


def move_x(body: Body, grid: TileGrid, dx: float) -> None:
    """Move horizontally and push the body out of any solid tile it entered."""
    if dx == 0.0:
        return
    body.x += dx
    if dx > 0:
        tx = math.floor((body.right - EPS) / TILE)
        for ty in tile_range(body.y, body.h):
            if grid.is_solid(tx, ty):
                body.x = tx * TILE - body.w
                body.vx = min(body.vx, 0.0)
                body.hit_right = True
                return
    else:
        tx = math.floor(body.x / TILE)
        for ty in tile_range(body.y, body.h):
            if grid.is_solid(tx, ty):
                body.x = (tx + 1) * TILE
                body.vx = max(body.vx, 0.0)
                body.hit_left = True
                return


def move_y(body: Body, grid: TileGrid, dy: float, drop_through: bool = False) -> None:
    """Move vertically. Solid tiles block from every side, one-way platforms
    only block bodies that were completely above them before the move."""
    if dy == 0.0:
        return
    old_bottom = body.bottom
    body.y += dy
    if dy > 0:
        ty = math.floor((body.bottom - EPS) / TILE)
        platform_top = ty * TILE
        for tx in tile_range(body.x, body.w):
            solid = grid.is_solid(tx, ty)
            one_way = (not drop_through and grid.is_one_way(tx, ty)
                       and old_bottom <= platform_top + ONE_WAY_TOLERANCE)
            if solid or one_way:
                body.y = platform_top - body.h
                body.vy = min(body.vy, 0.0)
                body.on_ground = True
                return
    else:
        ty = math.floor(body.y / TILE)
        for tx in tile_range(body.x, body.w):
            if grid.is_solid(tx, ty):
                body.y = (ty + 1) * TILE
                body.vy = max(body.vy, 0.0)
                body.hit_ceiling = True
                return


def move_and_collide(body: Body, grid: TileGrid, dx: float, dy: float,
                     drop_through: bool = False) -> None:
    """Move ``body`` by (dx, dy) against ``grid``, updating its contact flags."""
    body.on_ground = False
    body.hit_left = body.hit_right = body.hit_ceiling = False
    move_x(body, grid, dx)
    move_y(body, grid, dy, drop_through)


def integrate(body: Body, grid: TileGrid, ax: float, ay: float, dt: float,
              max_fall: float = float("inf"), drop_through: bool = False) -> None:
    """Advance ``body`` by one step with constant acceleration (ax, ay)."""
    vx0, vy0 = body.vx, body.vy
    body.vx = vx0 + ax * dt
    body.vy = min(vy0 + ay * dt, max_fall)
    clamp_velocity(body)
    dx = (vx0 + body.vx) * 0.5 * dt
    dy = (vy0 + body.vy) * 0.5 * dt
    move_and_collide(body, grid, dx, dy, drop_through)


def approach(value: float, target: float, delta: float) -> float:
    """Move ``value`` towards ``target`` by at most ``delta``."""
    if value < target:
        return min(value + delta, target)
    return max(value - delta, target)


def is_standing_on_one_way(body: Body, grid: TileGrid) -> bool:
    """True if the body rests on a one-way platform and on nothing solid."""
    ty = math.floor((body.bottom + 1.0) / TILE)
    if abs(body.bottom - ty * TILE) > 1.0:
        return False
    cols = list(tile_range(body.x, body.w))
    if any(grid.is_solid(tx, ty) for tx in cols):
        return False
    return any(grid.is_one_way(tx, ty) for tx in cols)
