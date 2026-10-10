"""The player character: input-driven movement with platformer game feel."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from . import constants as C
from .physics import Body, approach, integrate, is_standing_on_one_way
from .weapons import PISTOL, WEAPON_ORDER, WEAPONS, Weapon


@dataclass
class InputState:
    """Everything the player can do during one simulation step.

    ``jump_pressed`` is an edge (true only on the step the button went down),
    ``jump_held`` is the level. ``aim`` is a target point in world
    coordinates (mouse) or None to shoot in the facing direction.
    """

    left: bool = False
    right: bool = False
    down: bool = False
    jump_pressed: bool = False
    jump_held: bool = False
    shoot: bool = False
    aim: Optional[Tuple[float, float]] = None
    switch: int = 0                 # -1 previous weapon, +1 next weapon
    select_slot: Optional[int] = None  # 0-based slot in WEAPON_ORDER


class Player:
    def __init__(self, x: float, y: float) -> None:
        self.body = Body(x, y, C.PLAYER_WIDTH, C.PLAYER_HEIGHT)
        self.facing = 1
        self.health = C.PLAYER_MAX_HEALTH
        self.max_health = C.PLAYER_MAX_HEALTH
        self.alive = True
        self.weapons: Dict[str, Weapon] = {"pistol": Weapon(PISTOL)}
        self.current = "pistol"
        self.aim_angle = 0.0
        self.coyote = 0.0
        self.jump_buffer = 0.0
        self.jumping = False       # rising from a jump (jump cut still possible)
        self.drop_timer = 0.0
        self.invulnerable = 0.0
        # animation state (no effect on gameplay)
        self.run_phase = 0.0
        self.squash = 0.0          # >0 squashed (landing), <0 stretched (jump)
        self.recoil_anim = 0.0
        self.landed_speed = 0.0    # impact speed of the last landing (for dust)
        self.just_jumped = False
        self.just_landed = False

    # ------------------------------------------------------------ helpers
    @classmethod
    def at_tile(cls, tx: int, ty: int) -> "Player":
        """Create a player standing on the floor of tile (tx, ty)."""
        x = tx * C.TILE + (C.TILE - C.PLAYER_WIDTH) / 2
        y = (ty + 1) * C.TILE - C.PLAYER_HEIGHT
        return cls(x, y)

    @property
    def weapon(self) -> Weapon:
        return self.weapons[self.current]

    @property
    def on_ground(self) -> bool:
        return self.body.on_ground

    def muzzle(self) -> Tuple[float, float]:
        """World position where projectiles leave the gun."""
        sx, sy = self.shoulder()
        return sx + math.cos(self.aim_angle) * 22, sy + math.sin(self.aim_angle) * 22

    def shoulder(self) -> Tuple[float, float]:
        return self.body.cx, self.body.y + 17

    def owned_in_order(self) -> List[str]:
        return [k for k in WEAPON_ORDER if k in self.weapons]

    # ----------------------------------------------------------- weapons
    def give_weapon(self, key: str) -> str:
        """Pick up a weapon. Returns "new", "ammo" or "full"."""
        spec = WEAPONS[key]
        if key not in self.weapons:
            self.weapons[key] = Weapon(spec)
            self.current = key
            return "new"
        if self.weapons[key].add_ammo(spec.pickup_ammo) > 0:
            return "ammo"
        return "full"

    def cycle_weapon(self, direction: int) -> bool:
        owned = [k for k in self.owned_in_order() if self.weapons[k].has_ammo]
        if len(owned) < 2:
            return False
        idx = owned.index(self.current) if self.current in owned else 0
        self.current = owned[(idx + direction) % len(owned)]
        return True

    def select_slot(self, slot: int) -> bool:
        if 0 <= slot < len(WEAPON_ORDER):
            key = WEAPON_ORDER[slot]
            if key in self.weapons and self.weapons[key].has_ammo and key != self.current:
                self.current = key
                return True
        return False

    # ---------------------------------------------------------- movement
    def update(self, inp: InputState, level, dt: float = C.FIXED_DT) -> None:
        body = self.body
        self.just_jumped = False
        self.just_landed = False
        self.invulnerable = max(0.0, self.invulnerable - dt)
        self.drop_timer = max(0.0, self.drop_timer - dt)
        self.jump_buffer = max(0.0, self.jump_buffer - dt)
        self.squash *= math.exp(-12 * dt)
        self.recoil_anim = max(0.0, self.recoil_anim - dt * 6)
        for w in self.weapons.values():
            w.tick(dt)

        if body.on_ground:
            self.coyote = C.COYOTE_TIME
        else:
            self.coyote = max(0.0, self.coyote - dt)

        move = (1 if inp.right else 0) - (1 if inp.left else 0)

        if inp.jump_pressed:
            if inp.down and body.on_ground and is_standing_on_one_way(body, level):
                self.drop_timer = C.DROP_THROUGH_TIME
                body.on_ground = False
                self.coyote = 0.0
            else:
                self.jump_buffer = C.JUMP_BUFFER

        # horizontal: accelerate towards the target speed, friction when idle
        if move != 0:
            accel = C.GROUND_ACCEL if body.on_ground else C.AIR_ACCEL
            if body.vx * move < 0:
                accel *= C.TURN_BOOST
            vx = approach(body.vx, move * C.RUN_SPEED, accel * dt)
            self.facing = move
        else:
            decel = C.GROUND_FRICTION if body.on_ground else C.AIR_DRAG
            vx = approach(body.vx, 0.0, decel * dt)
        ax = (vx - body.vx) / dt

        # jump (buffered input + coyote time)
        if self.jump_buffer > 0.0 and (body.on_ground or self.coyote > 0.0):
            body.vy = -C.JUMP_VELOCITY
            body.on_ground = False
            self.jump_buffer = 0.0
            self.coyote = 0.0
            self.jumping = True
            self.just_jumped = True
            self.squash = -0.35

        # variable jump height: releasing the button early cuts the jump
        if self.jumping and not inp.jump_held and body.vy < 0:
            body.vy *= C.JUMP_CUT
            self.jumping = False
        if body.vy >= 0:
            self.jumping = False

        g = C.GRAVITY * (C.FALL_GRAVITY_MULT if body.vy > 0 else 1.0)
        was_on_ground = body.on_ground
        fall_speed = body.vy
        integrate(body, level, ax, g, dt, max_fall=C.MAX_FALL_SPEED, drop_through=self.drop_timer > 0)

        if body.on_ground and not was_on_ground:
            self.just_landed = True
            self.landed_speed = fall_speed
            self.squash = min(0.45, fall_speed / 2000.0)

        # aiming
        sx, sy = self.shoulder()
        if inp.aim is not None:
            self.aim_angle = math.atan2(inp.aim[1] - sy, inp.aim[0] - sx)
            if abs(inp.aim[0] - sx) > 2:
                self.facing = 1 if inp.aim[0] > sx else -1
        else:
            self.aim_angle = 0.0 if self.facing > 0 else math.pi

        if body.on_ground and abs(body.vx) > 10:
            self.run_phase += abs(body.vx) * dt * 0.045
        elif body.on_ground:
            self.run_phase = 0.0
