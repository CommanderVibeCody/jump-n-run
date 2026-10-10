import math

import pytest

from game import constants as C
from game.level import Level
from game.physics import Body, integrate, move_and_collide
from game.player import InputState
from helpers import ARENA, make_world, settle, steps

FLOOR_Y = 9 * C.TILE


def test_gravity_accelerates_a_falling_body():
    level = Level.from_ascii(["P   "] + ["    "] * 30)
    body = Body(32, 0, 20, 20)
    integrate(body, level, 0.0, C.GRAVITY, 0.5)
    assert body.vy == pytest.approx(C.GRAVITY * 0.5)
    # exact for constant acceleration: y = 1/2 g t^2
    assert body.y == pytest.approx(0.5 * C.GRAVITY * 0.25)


def test_player_lands_on_the_floor():
    w = make_world()
    w.player.body.y -= 100  # start in the air
    steps(w, 120)
    b = w.player.body
    assert b.on_ground
    assert b.bottom == pytest.approx(FLOOR_Y)
    assert b.vy == 0.0


def test_full_jump_reaches_jump_height():
    w = make_world()
    settle(w)
    start = w.player.body.y
    w.step(InputState(jump_pressed=True, jump_held=True))
    apex = start
    for _ in range(120):
        w.step(InputState(jump_held=True))
        apex = min(apex, w.player.body.y)
    assert start - apex == pytest.approx(C.JUMP_HEIGHT, abs=2.0)
    assert w.player.on_ground  # and lands again


def test_releasing_jump_early_gives_a_lower_jump():
    w = make_world()
    settle(w)
    start = w.player.body.y
    w.step(InputState(jump_pressed=True, jump_held=True))
    steps(w, 5, InputState(jump_held=True))
    apex = start
    for _ in range(100):
        w.step(InputState(jump_held=False))
        apex = min(apex, w.player.body.y)
    height = start - apex
    assert 10 < height < C.JUMP_HEIGHT * 0.6


def test_run_accelerates_to_max_speed_and_friction_stops():
    w = make_world()
    settle(w)
    w.step(InputState(right=True))
    assert 0 < w.player.body.vx < C.RUN_SPEED
    steps(w, 30, InputState(right=True))
    assert w.player.body.vx == pytest.approx(C.RUN_SPEED)
    steps(w, 30)
    assert w.player.body.vx == 0.0


def test_wall_blocks_horizontal_movement():
    w = make_world()
    settle(w)
    steps(w, 600, InputState(right=True))
    b = w.player.body
    assert b.right == pytest.approx(25 * C.TILE)
    assert b.hit_right


def test_ceiling_stops_upward_motion():
    level = Level.from_ascii(["#####", "     ", "  P  ", "#####"])
    body = Body(40, 2 * C.TILE, 20, 20)
    body.vy = -600
    for _ in range(30):
        integrate(body, level, 0, C.GRAVITY, C.FIXED_DT)
        if body.hit_ceiling:
            break
    assert body.hit_ceiling
    assert body.top == pytest.approx(C.TILE)


def test_coyote_time_allows_late_jump():
    rows = ["          ", "          ", "          ", " P        ", "####      ", "          "]
    w = make_world(rows)
    settle(w)
    p = w.player
    # walk off the ledge
    while p.on_ground:
        w.step(InputState(right=True))
    steps(w, 4, InputState(right=True))  # ~33 ms after leaving the ledge
    w.step(InputState(right=True, jump_pressed=True, jump_held=True))
    assert p.body.vy < 0, "jump should still work within coyote time"


def test_no_jump_after_coyote_time():
    rows = ["          ", "          ", "          ", " P        ", "####      "] + ["          "] * 10
    w = make_world(rows)
    settle(w)
    p = w.player
    while p.on_ground:
        w.step(InputState(right=True))
    steps(w, int(0.2 / C.FIXED_DT), InputState(right=True))
    w.step(InputState(right=True, jump_pressed=True, jump_held=True))
    assert p.body.vy > 0


def test_jump_buffer_jumps_on_landing():
    w = make_world()
    w.player.body.y -= 40
    # press jump shortly before touching the floor
    while True:
        w.step()
        if FLOOR_Y - w.player.body.bottom < 6:
            break
    w.step(InputState(jump_pressed=True, jump_held=True))
    for _ in range(10):
        w.step(InputState(jump_held=True))
    assert w.player.body.vy < 0, "buffered jump should trigger after landing"


def test_one_way_platform_pass_from_below_and_land_on_top():
    w = make_world()
    p = w.player
    # place the player under the platform (cols 12-16, row 5)
    p.body.x = 13 * C.TILE
    settle(w)
    w.step(InputState(jump_pressed=True, jump_held=True))
    landed_on_platform = False
    for _ in range(200):
        w.step(InputState(jump_held=True))
        if p.on_ground and p.body.bottom == pytest.approx(5 * C.TILE):
            landed_on_platform = True
            break
    assert landed_on_platform


def test_drop_through_one_way_platform():
    w = make_world()
    p = w.player
    p.body.x = 13 * C.TILE
    p.body.y = 5 * C.TILE - p.body.h
    steps(w, 10)
    assert p.on_ground and p.body.bottom == pytest.approx(5 * C.TILE)
    w.step(InputState(down=True, jump_pressed=True, jump_held=True))
    steps(w, 60, InputState(down=True))
    assert p.body.bottom == pytest.approx(FLOOR_Y)


def test_fast_body_does_not_tunnel_through_floor():
    level = Level.from_ascii(["  P  ", "     ", "     ", "#####"])
    body = Body(40, 0, 20, 20)
    body.vy = 5000  # will be clamped to MAX_SPEED
    for _ in range(60):
        integrate(body, level, 0, C.GRAVITY, C.FIXED_DT)
    assert body.bottom == pytest.approx(3 * C.TILE)


def test_move_and_collide_side_walls_outside_level():
    level = Level.from_ascii(["P  ", "###"])
    body = Body(5, 0, 20, 20)
    move_and_collide(body, level, -20, 0)
    assert body.x == 0.0 and body.hit_left
