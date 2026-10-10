"""Small helpers shared by the tests."""
from game.level import LevelDef
from game.player import InputState
from game.world import World

# A flat test arena: floor on row 9, a wall on the right, a one-way platform.
ARENA = [
    "                              ",
    "                              ",
    "                              ",
    "                              ",
    "                              ",
    "            =====             ",
    "                              ",
    "                         #    ",
    "  P                      #    ",
    "##############################",
    "##############################",
]


def make_world(rows=None, **kwargs) -> World:
    return World([LevelDef("Test", rows or ARENA)], seed=1, **kwargs)


def steps(world: World, n: int, inp: InputState = None) -> None:
    for _ in range(n):
        world.step(inp or InputState())


def settle(world: World) -> None:
    """Let the player fall onto the floor."""
    steps(world, 60)
