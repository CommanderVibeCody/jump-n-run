"""A smooth-following camera with look-ahead, clamped to the level bounds."""
from __future__ import annotations

import math

from .constants import SCREEN_HEIGHT, SCREEN_WIDTH


class Camera:
    LOOK_AHEAD = 90.0
    FOLLOW_RATE = 7.0      # higher = snappier horizontal follow
    VERTICAL_RATE = 4.5

    def __init__(self, level_width: float, level_height: float,
                 view_w: int = SCREEN_WIDTH, view_h: int = SCREEN_HEIGHT) -> None:
        self.level_w = level_width
        self.level_h = level_height
        self.w = view_w
        self.h = view_h
        self.x = 0.0
        self.y = 0.0
        self.look = 0.0

    def _clamp(self) -> None:
        if self.level_w <= self.w:
            self.x = (self.level_w - self.w) / 2
        else:
            self.x = max(0.0, min(self.x, self.level_w - self.w))
        if self.level_h <= self.h:
            self.y = self.level_h - self.h
        else:
            self.y = max(0.0, min(self.y, self.level_h - self.h))

    def target(self, cx: float, cy: float) -> tuple:
        return cx - self.w / 2 + self.look, cy - self.h * 0.62

    def snap(self, cx: float, cy: float, facing: int = 1) -> None:
        self.look = facing * self.LOOK_AHEAD
        self.x, self.y = self.target(cx, cy)
        self._clamp()

    def follow(self, cx: float, cy: float, facing: int, dt: float) -> None:
        self.look += (facing * self.LOOK_AHEAD - self.look) * (1 - math.exp(-2.5 * dt))
        tx, ty = self.target(cx, cy)
        self.x += (tx - self.x) * (1 - math.exp(-self.FOLLOW_RATE * dt))
        self.y += (ty - self.y) * (1 - math.exp(-self.VERTICAL_RATE * dt))
        self._clamp()

    def to_screen(self, x: float, y: float) -> tuple:
        return x - self.x, y - self.y

    def to_world(self, sx: float, sy: float) -> tuple:
        return sx + self.x, sy + self.y
