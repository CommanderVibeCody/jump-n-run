"""Global constants: window size, tile size, timestep and movement tuning.

All distances are in pixels, all times in seconds.
"""
import math

SCREEN_WIDTH = 960
SCREEN_HEIGHT = 540
TILE = 32

# The simulation always advances in fixed steps of FIXED_DT, independent of
# the frame rate. MAX_FRAME_TIME limits how much time one slow frame may add
# (prevents the "spiral of death" after a hitch).
FIXED_DT = 1.0 / 120.0
MAX_FRAME_TIME = 0.1

# --- Player movement -------------------------------------------------------
GRAVITY = 2200.0            # px/s^2 while rising
FALL_GRAVITY_MULT = 1.5     # stronger gravity while falling feels snappier
MAX_FALL_SPEED = 950.0
RUN_SPEED = 300.0
GROUND_ACCEL = 2800.0
AIR_ACCEL = 1700.0
TURN_BOOST = 1.6            # extra acceleration when reversing direction
GROUND_FRICTION = 3200.0
AIR_DRAG = 450.0
JUMP_HEIGHT = 140.0         # apex height of a full (held) jump
JUMP_VELOCITY = math.sqrt(2.0 * GRAVITY * JUMP_HEIGHT)
JUMP_CUT = 0.45             # vy multiplier when the jump button is released early
COYOTE_TIME = 0.10          # can still jump this long after walking off a ledge
JUMP_BUFFER = 0.12          # a jump pressed this long before landing still counts
DROP_THROUGH_TIME = 0.25    # one-way platforms are ignored this long after dropping
MAX_SPEED = 1500.0          # hard clamp, keeps per-step motion below one tile

PLAYER_WIDTH = 22
PLAYER_HEIGHT = 40
PLAYER_MAX_HEALTH = 100
PLAYER_LIVES = 3
INVULNERABLE_TIME = 1.0
RESPAWN_DELAY = 1.6
LEVEL_END_DELAY = 2.5
STOMP_DAMAGE = 60
STOMP_BOUNCE = 620.0
SPIKE_DAMAGE = 35

# --- Colours -------------------------------------------------------------
WHITE = (245, 245, 250)
BLACK = (0, 0, 0)
TEXT = (235, 238, 245)
DIM = (150, 160, 180)
ACCENT = (255, 196, 64)
RED = (235, 70, 70)
GREEN = (90, 220, 120)
