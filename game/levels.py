"""Level data. Each level is an ASCII map; see ``game/level.py`` for the
legend. Edit the maps to build your own levels - every row may have a
different length, shorter rows are padded with empty space."""
from typing import Dict, List, Sequence, Tuple

from .level import LevelDef, Theme


def add_house(rows: List[str], x0: int, width: int, ground: int, floors: int = 1,
              contents: Dict[Tuple[int, int], str] = None, ladder: int = None, windows: Sequence[int] = ()) -> None:
    """Stamp an enterable house into ``rows`` (in place).

    ``x0`` is the left wall column, ``ground`` the first solid row under the
    house. Every floor has three rows of interior (back wall ``:``) and is
    separated from the next one by a slab with a ladder ``H`` hole at column
    ``x0 + ladder``. The ground floor gets a two tile door ``|`` in both walls.
    ``contents`` maps ``(dx, floor)`` to a map character standing on that
    floor (enemies, pickups, barrels, decoration); ``windows`` lists the dx
    of windows ``O`` on every floor.
    """
    contents = contents or {}
    grid = [list(r) for r in rows]
    width_all = max(len(r) for r in grid)
    for r in grid:
        r.extend(" " * (width_all - len(r)))
    top = ground - 4 * floors
    ladder = width // 2 if ladder is None else ladder
    for y in range(top, ground):
        for dx in range(width):
            x = x0 + dx
            rel = ground - y            # 1 = lowest interior row
            floor, level_row = (rel - 1) // 4, (rel - 1) % 4   # level_row 3 = slab / roof
            if y == top:
                grid[y][x] = "#"
            elif dx in (0, width - 1):
                grid[y][x] = "|" if (floor == 0 and level_row < 2) else "#"
            elif level_row == 3:
                grid[y][x] = "H" if dx == ladder else "#"
            elif dx == ladder and floor < floors - 1:
                grid[y][x] = "H"
            elif level_row == 2 and dx in windows:
                grid[y][x] = "O"
            elif level_row == 0 and (dx, floor) in contents:
                grid[y][x] = contents[(dx, floor)]
            else:
                grid[y][x] = ":"
    # roof overhang
    for x in (x0 - 1, x0 + width):
        if 0 <= x < width_all and grid[top][x] == " ":
            grid[top][x] = "="
    rows[:] = ["".join(r) for r in grid]


def put(rows: List[str], x: int, y: int, ch: str) -> None:
    r = rows[y].ljust(x + 1)
    rows[y] = r[:x] + ch + r[x + 1:]

GREEN_HILLS = [
    "                                                                                                                                                      ",
    "                                                                                                                                                      ",
    "                                                                                                                                                      ",
    "                                                                                                                                                      ",
    "                                                                                                                                                      ",
    "                                                                                                                                                      ",
    "                                                                                                                                                      ",
    "                                                                                                                                                      ",
    "                                        S                                                                                                             ",
    "                                      ======                                                                                                          ",
    "                                                                                          M   e                         R                             ",
    "                                                                                      ###########                   ========                          ",
    "                        r        =====                    ##                      === ###########                              ##                     ",
    "                    #######                               ##                          ###########                              ##                     ",
    "   P      D     e   #######         r        r    bb s    ##  C U   +   k             ########### a  bbs  g C   + r   ^^^^   bb##  e    k   s h   G   ",
    "###########################    #############################################    ######################################################################",
    "###########################    #############################################    ######################################################################",
    "###########################    #############################################    ######################################################################",
    "###########################    #############################################    ######################################################################",
    "###########################    #############################################    ######################################################################",
    "###########################    #############################################    ######################################################################",
]
NIGHT_FACTORY = [
    "                                                                                                                                                                ",
    "                                                                                                                                                                ",
    "                                                                                                                                                                ",
    "                                                                                                                                                                ",
    "                                                                                                                                                                ",
    "                                                                                                                                                                ",
    "                                                                                                                                                                ",
    "                                                                                                                                                                ",
    "                                                                                                                                                                ",
    "                                                            +                              R                                                                    ",
    "                                                  #####################             ###=========                                                                ",
    "                                                  #####################             ###                                                                         ",
    "                                                  #####################             ###                                                                         ",
    "                           ====               === #####################         ### ###                                                                         ",
    "                                                  #####################         ### ###                        s                       a                        ",
    "                                                                                ### ###                       ####                 ======                       ",
    "                      ====      ====     ====                               ### ### ###                       ####                                              ",
    "                                                                            ### ### ###                                                                         ",
    "  P     a   b s                       F S   ^^^^       e  bb  n  h  s    C  ### ### ###   o   e  M k        +      N  q aL  e g C    bb     s  r      r    G    ",
    "#####################                ###################################################################    ####################################################",
    "#####################                ###################################################################    ####################################################",
    "#####################                ###################################################################    ####################################################",
    "#####################                ###################################################################    ####################################################",
    "#####################                ###################################################################    ####################################################",
    "#####################                ###################################################################    ####################################################",
]

SUNSET_WARZONE = [
    "                                                                                                                                                                                    ",
    "                                                                                                                                                                                    ",
    "                                                                                                                                                                                    ",
    "                                                                                                                                                                                    ",
    "                                                                                                                                                                                    ",
    "                                                                                                                                                                                    ",
    "                                                                                                                                                                                    ",
    "                                                                                                                                                                                    ",
    "                                                                                                                                                                                    ",
    "                                                                                                                                                                                    ",
    "                                                                                                                Z     g   U                                                         ",
    "                                                        g                                           ##########################                                                      ",
    "                                                       ####                                         ##########################                                                      ",
    "                     k                                 ####                                         ##########################                    g                                 ",
    "                  =======                              ####                                     ===                                             =====                               ",
    "                                                  ==== ####                                                                                                                         ",
    "              ##                                       ####                                                                                                       ##                ",
    "  P D N       ##    r  bbb  r    +   g         L    C  #### F   bbbb  h         r  b k  +             a r   bb   k      h       C    R bbb  r    +    r    k a  h ##  bb  r    G    ",
    "#########################################    ##############################################    #####################################################################################",
    "#########################################    ##############################################    #####################################################################################",
    "#########################################    ##############################################    #####################################################################################",
    "#########################################    ##############################################    #####################################################################################",
]

def _furnish() -> None:
    g = GREEN_HILLS
    # 1-1: a small cottage, a two storey house and a bunker near the goal
    add_house(g, 44, 12, 15, 1, {(2, 0): "t", (4, 0): "e", (6, 0): "b", (8, 0): "x", (9, 0): "s"},
              windows=(3, 9))
    add_house(g, 101, 14, 15, 2, {(2, 0): "x", (4, 0): "r", (9, 0): "b", (11, 0): "+",
                                  (2, 1): "l", (3, 1): "a", (5, 1): "n", (10, 1): "t", (11, 1): "U"},
              ladder=7, windows=(3, 10))
    put(g, 99, 14, "C")
    add_house(g, 135, 10, 15, 1, {(2, 0): "x", (4, 0): "o", (7, 0): "h"}, windows=(5,))
    n = NIGHT_FACTORY
    # 1-2: a guard post, a two storey barracks and a small bunker
    add_house(n, 96, 8, 19, 2, {(2, 0): "M", (5, 0): "k", (2, 1): "x", (5, 1): "n"}, ladder=3, windows=(5,))
    add_house(n, 114, 16, 19, 2, {(2, 0): "N", (4, 0): "e", (6, 0): "t", (9, 0): "a", (10, 0): "L",
                                  (12, 0): "q", (2, 1): "l", (4, 1): "o", (9, 1): "x", (11, 1): "+",
                                  (13, 1): "r"}, ladder=7, windows=(3, 12))
    put(n, 131, 18, "C")
    add_house(n, 139, 7, 19, 1, {(2, 0): "s", (4, 0): "x"}, windows=(3,))
    w = SUNSET_WARZONE
    # 1-3: a ruined house, a depot, a command post and a final bunker
    add_house(w, 25, 14, 18, 2, {(2, 0): "b", (4, 0): "r", (8, 0): "+", (11, 0): "g",
                                 (2, 1): "t", (4, 1): "n", (10, 1): "x", (11, 1): "a"}, ladder=6, windows=(3, 10))
    add_house(w, 61, 14, 18, 1, {(1, 0): "F", (4, 0): "b", (5, 0): "b", (8, 0): "q", (11, 0): "h"}, windows=(6,))
    add_house(w, 126, 16, 18, 2, {(3, 0): "R", (5, 0): "x", (7, 0): "b", (11, 0): "o", (13, 0): "e",
                                  (2, 1): "l", (4, 1): "q", (9, 1): "+", (12, 1): "n"}, ladder=8, windows=(4, 11))
    put(w, 124, 17, "C")
    put(w, 54, 15, "=")  # step up to the watch tower
    add_house(w, 166, 8, 18, 1, {(2, 0): "b", (5, 0): "o"}, windows=(3,))


_furnish()

DAY = Theme()

NIGHT = Theme(
    sky_top=(10, 12, 40),
    sky_bottom=(60, 40, 90),
    far=(45, 40, 85),
    mid=(32, 30, 64),
    near=(20, 20, 42),
    ground=(70, 74, 92),
    ground_dark=(46, 48, 64),
    grass=(110, 200, 255),
    platform=(140, 140, 160),
    night=True,
)

SUNSET = Theme(
    sky_top=(70, 40, 100),
    sky_bottom=(255, 160, 90),
    far=(170, 90, 100),
    mid=(120, 65, 80),
    near=(75, 40, 55),
    ground=(165, 120, 80),
    ground_dark=(125, 88, 58),
    grass=(215, 180, 100),
    platform=(120, 95, 75),
)

LEVELS = [
    LevelDef("1-1  Green Hills", GREEN_HILLS, DAY),
    LevelDef("1-2  Night Factory", NIGHT_FACTORY, NIGHT),
    LevelDef("1-3  Sunset Warzone", SUNSET_WARZONE, SUNSET),
]
