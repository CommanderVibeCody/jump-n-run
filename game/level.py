"""Levels are described as ASCII maps (see ``levels.py``).

Legend::

    #   solid block             =   one-way platform (jump through from below)
    ^   spikes (hurt)           P   player start
    G   goal flag               C   checkpoint
    w   walker enemy            s   shooter enemy          d   drone enemy
    S   shotgun pickup          M   machine gun pickup     R   rocket launcher
    +   health pack             a   ammo crate

Everything outside the map to the left and right counts as solid wall,
everything below the map is a bottomless pit.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .constants import TILE

SOLID = "#"
ONE_WAY = "="
SPIKE = "^"
ENTITY_CHARS = set("PGCwsdSMR+a")


@dataclass(frozen=True)
class Theme:
    """Colours of a level (sky, parallax layers and tiles)."""

    sky_top: Tuple[int, int, int] = (64, 140, 220)
    sky_bottom: Tuple[int, int, int] = (190, 225, 250)
    far: Tuple[int, int, int] = (120, 150, 200)
    mid: Tuple[int, int, int] = (80, 130, 120)
    near: Tuple[int, int, int] = (50, 100, 80)
    ground: Tuple[int, int, int] = (120, 82, 56)
    ground_dark: Tuple[int, int, int] = (88, 58, 40)
    grass: Tuple[int, int, int] = (96, 200, 90)
    platform: Tuple[int, int, int] = (170, 120, 70)
    night: bool = False


@dataclass
class LevelDef:
    name: str
    rows: Sequence[str]
    theme: Theme = field(default_factory=Theme)


@dataclass
class Spawn:
    kind: str
    tx: int
    ty: int


class Level:
    """A parsed level: the tile grid plus the list of entity spawns."""

    def __init__(self, definition: LevelDef) -> None:
        self.name = definition.name
        self.theme = definition.theme
        rows = [r.rstrip("\n") for r in definition.rows]
        self.height = len(rows)
        self.width = max((len(r) for r in rows), default=0)
        self.tiles: List[List[str]] = []
        self.spawns: List[Spawn] = []
        for ty, row in enumerate(rows):
            line = []
            for tx in range(self.width):
                ch = row[tx] if tx < len(row) else " "
                if ch in ENTITY_CHARS:
                    self.spawns.append(Spawn(ch, tx, ty))
                    ch = " "
                elif ch not in (SOLID, ONE_WAY, SPIKE):
                    ch = " "
                line.append(ch)
            self.tiles.append(line)
        players = [s for s in self.spawns if s.kind == "P"]
        if len(players) != 1:
            raise ValueError(f"level {self.name!r} needs exactly one 'P', found {len(players)}")
        self.player_spawn = players[0]

    @classmethod
    def from_ascii(cls, rows: Sequence[str], name: str = "Custom", theme: Optional[Theme] = None) -> "Level":
        return cls(LevelDef(name, rows, theme or Theme()))

    # ------------------------------------------------------------ geometry
    @property
    def pixel_width(self) -> int:
        return self.width * TILE

    @property
    def pixel_height(self) -> int:
        return self.height * TILE

    def tile(self, tx: int, ty: int) -> str:
        if tx < 0 or tx >= self.width:
            return SOLID  # side walls
        if ty < 0 or ty >= self.height:
            return " "  # open sky above, pit below
        return self.tiles[ty][tx]

    def is_solid(self, tx: int, ty: int) -> bool:
        return self.tile(tx, ty) == SOLID

    def is_one_way(self, tx: int, ty: int) -> bool:
        return self.tile(tx, ty) == ONE_WAY

    def is_spike(self, tx: int, ty: int) -> bool:
        return self.tile(tx, ty) == SPIKE

    def solid_at(self, x: float, y: float) -> bool:
        return self.is_solid(math.floor(x / TILE), math.floor(y / TILE))

    def spawns_of(self, kinds: str) -> List[Spawn]:
        return [s for s in self.spawns if s.kind in kinds]

    def line_of_sight(self, x0: float, y0: float, x1: float, y1: float, step: float = 8.0) -> bool:
        """True if no solid tile lies on the segment between the two points."""
        dist = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(dist / step))
        for i in range(1, n):
            t = i / n
            if self.solid_at(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t):
                return False
        return True

    def touches_spikes(self, x: float, y: float, w: float, h: float) -> bool:
        """True if the box overlaps the dangerous lower half of a spike tile."""
        for ty in range(math.floor(y / TILE), math.floor((y + h - 1e-6) / TILE) + 1):
            for tx in range(math.floor(x / TILE), math.floor((x + w - 1e-6) / TILE) + 1):
                if self.is_spike(tx, ty) and y + h > ty * TILE + TILE * 0.45:
                    return True
        return False
