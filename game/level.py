"""Levels are described as ASCII maps (see ``levels.py``).

Legend::

    #   solid block             =   one-way platform (jump through from below)
    ^   spikes (hurt)           P   player start
    G   goal flag               C   checkpoint
    e   recruit                 r   rifleman               k   shotgunner
    g   grenadier               n   sniper                 h   heavy (minigun)
    o   officer                 q   rocketeer              s   guard (stationary)
    b   explosive barrel
    :   back wall (house interior)   O   window (back wall with glass)
    |   door (a vertical run of | is one door)   H   ladder (climb with W/S)
    t   table   x   crate   l   lamp   (decoration, drawn on the back wall)
    D   dual pistols            U   SMG                    S   shotgun
    M   machine gun             N   sniper rifle           F   flamethrower
    L   grenade launcher        R   rocket launcher        Z   railgun
    +   health pack             a   ammo crate

Everything outside the map to the left and right counts as solid wall,
everything below the map is a bottomless pit. Entities and decorations next
to back-wall tiles automatically get a back wall behind them, so houses can
be furnished and populated directly in the map.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .constants import TILE

SOLID = "#"
ONE_WAY = "="
SPIKE = "^"
BACKWALL = ":"
WINDOW = "O"
DOOR = "|"
LADDER = "H"
ENTITY_CHARS = set("PGCserkgnhoqb+aDUSMNFLRZ")
DECOR_CHARS = set("txl")
TILE_CHARS = (SOLID, ONE_WAY, SPIKE, BACKWALL, WINDOW, LADDER)


class Door:
    """A door made of a vertical run of ``|`` tiles. Closed doors are solid."""

    def __init__(self, tx: int, ty: int, height: int) -> None:
        self.tx, self.ty, self.height = tx, ty, height
        self.open = False
        self.broken = False
        self.anim = 0.0     # 0 closed .. 1 open (for drawing)
        self.side = 1       # which way it swung open

    @property
    def rect(self) -> Tuple[float, float, float, float]:
        return self.tx * TILE, self.ty * TILE, TILE, self.height * TILE

    def cells(self):
        return [(self.tx, self.ty + i) for i in range(self.height)]


class House:
    """A connected region of back-wall tiles (one building interior)."""

    def __init__(self, index: int, cells) -> None:
        self.index = index
        self.cells = set(cells)
        xs = [c[0] for c in cells]
        ys = [c[1] for c in cells]
        # bounding box including the outer walls and roof (in tiles)
        self.x0, self.x1 = min(xs) - 1, max(xs) + 1
        self.y0, self.y1 = min(ys) - 1, max(ys) + 1
        self.reveal = 0.0   # 0 = facade shown, 1 = interior revealed

    def contains_tile(self, tx: int, ty: int) -> bool:
        return self.x0 <= tx <= self.x1 and self.y0 <= ty <= self.y1


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
        self.decor: List[Spawn] = []
        door_cells = set()
        infer = set()  # cells that may get an inferred back wall
        for ty, row in enumerate(rows):
            line = []
            for tx in range(self.width):
                ch = row[tx] if tx < len(row) else " "
                if ch in ENTITY_CHARS:
                    self.spawns.append(Spawn(ch, tx, ty))
                    infer.add((tx, ty))
                    ch = " "
                elif ch in DECOR_CHARS:
                    self.decor.append(Spawn(ch, tx, ty))
                    infer.add((tx, ty))
                    ch = " "
                elif ch == DOOR:
                    door_cells.add((tx, ty))
                    ch = " "
                elif ch not in TILE_CHARS:
                    ch = " "
                if ch == LADDER:
                    infer.add((tx, ty))
                line.append(ch)
            self.tiles.append(line)
        # back walls: explicit ':' and 'O', plus inferred cells next to them
        self.back = [[self.tiles[y][x] in (BACKWALL, WINDOW) for x in range(self.width)]
                     for y in range(self.height)]
        changed = True
        while changed:
            changed = False
            for (x, y) in infer:
                if self.back[y][x]:
                    continue
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < self.width and 0 <= ny < self.height and self.back[ny][nx]:
                        self.back[y][x] = True
                        changed = True
                        break
        # doors: group vertical runs
        self.doors: List[Door] = []
        self.door_at = {}
        for (x, y) in sorted(door_cells, key=lambda c: (c[0], c[1])):
            if (x, y) in self.door_at:
                continue
            h = 1
            while (x, y + h) in door_cells:
                h += 1
            door = Door(x, y, h)
            self.doors.append(door)
            for c in door.cells():
                self.door_at[c] = door
        # houses: connected components of back-wall cells
        self.houses: List[House] = []
        self.house_map = {}
        seen = set()
        for y in range(self.height):
            for x in range(self.width):
                if not self.back[y][x] or (x, y) in seen:
                    continue
                stack, cells = [(x, y)], []
                seen.add((x, y))
                while stack:
                    cx, cy = stack.pop()
                    cells.append((cx, cy))
                    for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                        if (0 <= nx < self.width and 0 <= ny < self.height and self.back[ny][nx]
                                and (nx, ny) not in seen):
                            seen.add((nx, ny))
                            stack.append((nx, ny))
                house = House(len(self.houses), cells)
                self.houses.append(house)
                for c in cells:
                    self.house_map[c] = house
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
        if self.tile(tx, ty) == SOLID:
            return True
        door = self.door_at.get((tx, ty))
        return door is not None and not door.open

    def is_one_way(self, tx: int, ty: int) -> bool:
        """One-way platforms, and the top rung of every ladder."""
        t = self.tile(tx, ty)
        return t == ONE_WAY or (t == LADDER and self.tile(tx, ty - 1) != LADDER)

    def is_ladder(self, tx: int, ty: int) -> bool:
        return self.tile(tx, ty) == LADDER

    def is_back(self, tx: int, ty: int) -> bool:
        return 0 <= tx < self.width and 0 <= ty < self.height and self.back[ty][tx]

    def house_at_point(self, x: float, y: float):
        return self.house_map.get((math.floor(x / TILE), math.floor(y / TILE)))

    def door_near(self, x: float, y: float, reach: float = TILE * 1.6):
        best, best_d = None, reach
        for d in self.doors:
            dx, dy, dw, dh = d.rect
            px = min(max(x, dx), dx + dw)
            py = min(max(y, dy), dy + dh)
            dist = math.hypot(x - px, y - py)
            if dist <= best_d:
                best, best_d = d, dist
        return best

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
