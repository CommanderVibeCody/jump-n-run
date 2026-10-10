import pytest

from game import constants as C
from game.level import Level, LevelDef
from game.levels import LEVELS
from game.player import InputState
from game.world import World
from helpers import make_world, settle, steps


def run_until_death(w, inp, max_steps=1000):
    for _ in range(max_steps):
        w.step(inp)
        if "death" in w.events:
            return True
    return False


def test_falling_into_a_pit_costs_a_life_and_respawns():
    rows = ["          ", " P        ", "###   ####"]
    w = make_world(rows)
    settle(w)
    assert run_until_death(w, InputState(right=True))
    assert w.lives == C.PLAYER_LIVES - 1
    steps(w, int(C.RESPAWN_DELAY / C.FIXED_DT) + 5)
    assert w.state == "playing"
    assert w.player.alive and w.player.health == C.PLAYER_MAX_HEALTH


def test_checkpoint_changes_respawn_point():
    rows = ["              ", " P   C        ", "#########   ##"]
    w = make_world(rows)
    settle(w)
    assert run_until_death(w, InputState(right=True))
    assert w.checkpoints[0].active
    assert w.respawn_tile == (5, 1)
    steps(w, int(C.RESPAWN_DELAY / C.FIXED_DT) + 5)
    assert int(w.player.body.cx // C.TILE) == 5


def test_game_over_after_last_life():
    w = make_world(lives=1)
    w.damage_player(500, None)
    assert w.state == "dead"
    steps(w, int(C.RESPAWN_DELAY / C.FIXED_DT) + 5)
    assert w.state == "game_over"


def test_spikes_hurt():
    w = make_world(["          ", " P ^      ", "##########"])
    settle(w)
    steps(w, 40, InputState(right=True))
    assert w.player.health == C.PLAYER_MAX_HEALTH - C.SPIKE_DAMAGE


def test_reaching_goal_advances_to_next_level_then_victory():
    defs = [LevelDef("A", ["        ", " P  G   ", "########"]),
            LevelDef("B", ["        ", " P  G   ", "########"])]
    w = World(defs, seed=1)
    w.player.give_weapon("shotgun")
    steps(w, 200, InputState(right=True))
    assert w.state == "level_complete"
    steps(w, int(C.LEVEL_END_DELAY / C.FIXED_DT) + 5)
    assert w.level_index == 1
    assert "shotgun" in w.player.weapons  # weapons carry over
    steps(w, 200, InputState(right=True))
    steps(w, int(C.LEVEL_END_DELAY / C.FIXED_DT) + 5)
    assert w.state == "victory"


@pytest.mark.parametrize("definition", LEVELS, ids=lambda d: d.name)
def test_shipped_levels_are_valid(definition):
    level = Level(definition)
    kinds = [s.kind for s in level.spawns]
    assert kinds.count("P") == 1 and kinds.count("G") == 1
    w = World([definition], seed=1)
    steps(w, 120)
    assert w.player.on_ground, "player must spawn on solid ground"
    assert w.state == "playing"


def test_first_level_contains_all_weapon_pickups():
    w = World(LEVELS[:1], seed=1)
    assert {p.kind for p in w.pickups} >= {"shotgun", "machinegun", "rocket"}


def test_camera_follows_player_and_stays_in_bounds():
    w = World(LEVELS[:1], seed=1)
    x0 = w.camera.x
    steps(w, 300, InputState(right=True))
    assert w.camera.x > x0
    assert 0 <= w.camera.x <= w.level.pixel_width - w.camera.w
    assert 0 <= w.camera.y <= w.level.pixel_height - w.camera.h
