"""Everything that draws the game world with pygame primitives:
parallax background, tiles, characters, weapons, projectiles, particles
and the HUD. No image files are used."""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

import pygame

from . import constants as C
from .level import Level, Theme
from .ui import draw_text, font
from .weapons import WEAPON_ORDER, WEAPONS

LAYER_WIDTH = 1920


# ---------------------------------------------------------------- helpers
def lerp_color(a, b, t: float):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def shade(color, factor: float):
    return tuple(max(0, min(255, int(c * factor))) for c in color[:3])


def vertical_gradient(size: Tuple[int, int], top, bottom) -> pygame.Surface:
    w, h = size
    surf = pygame.Surface((w, h))
    for y in range(h):
        pygame.draw.line(surf, lerp_color(top, bottom, y / max(1, h - 1)), (0, y), (w, y))
    return surf


_GLOW_CACHE: Dict[Tuple, pygame.Surface] = {}


def glow_sprite(color, radius: int) -> pygame.Surface:
    """A soft radial glow, meant to be blitted with BLEND_ADD."""
    radius = max(2, int(radius))
    if radius > 16:  # quantise so animated glows reuse cached sprites
        radius = (radius // 6) * 6
    color = tuple((c // 8) * 8 for c in color[:3])
    key = (color, radius)
    surf = _GLOW_CACHE.get(key)
    if surf is None:
        surf = pygame.Surface((radius * 2, radius * 2))
        surf.fill((0, 0, 0))
        steps = min(radius, 12)
        for i in range(steps, 0, -1):
            r = radius * i / steps
            k = (1 - i / steps) ** 1.6 * 0.9 + 0.05
            pygame.draw.circle(surf, shade(color, k), (radius, radius), int(r))
        if len(_GLOW_CACHE) > 400:
            _GLOW_CACHE.clear()
        _GLOW_CACHE[key] = surf
    return surf


def blit_glow(surface: pygame.Surface, color, pos, radius: float, strength: float = 1.0) -> None:
    if strength < 1.0:
        color = shade(color, strength)
    g = glow_sprite(color, int(radius))
    surface.blit(g, (int(pos[0] - g.get_width() / 2), int(pos[1] - g.get_height() / 2)),
                 special_flags=pygame.BLEND_ADD)


def transform_points(points, ox: float, oy: float, angle: float, flip: bool, scale: float = 1.0):
    ca, sa = math.cos(angle), math.sin(angle)
    out = []
    for x, y in points:
        x *= scale
        y *= -scale if flip else scale
        out.append((ox + x * ca - y * sa, oy + x * sa + y * ca))
    return out


# Gun shapes as rectangles in local space (x points along the barrel).
# Each entry: (x0, y0, x1, y1, brightness)
GUN_SHAPES = {
    "pistol": [(4, -3, 17, 1, 0.75), (6, 1, 10, 7, 0.55), (16, -3, 18, 0, 1.0)],
    "dual_pistols": [(4, -7, 16, -3, 0.8), (5, -3, 8, 2, 0.55), (6, 1, 18, 5, 0.75), (7, 5, 10, 10, 0.55)],
    "smg": [(0, -3, 16, 2, 0.75), (16, -2, 22, 0, 1.0), (8, 2, 11, 10, 0.55), (-4, -2, 0, 1, 0.5)],
    "sniper": [(-8, -2, 8, 3, 0.55), (6, -3, 22, 1, 0.75), (22, -2, 36, 0, 1.0), (6, -7, 16, -4, 0.9),
               (12, 1, 15, 6, 0.5)],
    "flamethrower": [(-6, -4, 6, 4, 0.6), (4, -3, 22, 1, 0.75), (20, -4, 26, 2, 1.0), (-2, 4, 10, 9, 0.9)],
    "grenade_launcher": [(-4, -3, 6, 3, 0.55), (4, -5, 22, 2, 0.75), (8, 2, 16, 7, 0.9), (22, -4, 25, 1, 1.0)],
    "railgun": [(-6, -3, 6, 3, 0.55), (4, -5, 28, -2, 0.85), (4, 0, 28, 3, 0.85), (10, -2, 26, 0, 1.2)],
    "minigun": [(-6, -6, 8, 5, 0.55), (8, -4, 30, -2, 0.9), (8, -1, 30, 1, 0.8), (8, 2, 30, 4, 0.9),
                (0, 5, 6, 10, 0.6)],
    "shotgun": [(-4, -2, 6, 3, 0.55), (4, -3, 27, 0, 0.8), (11, 0, 21, 3, 0.6)],
    "machinegun": [(-2, -3, 6, 2, 0.55), (4, -4, 22, 1, 0.8), (21, -3, 29, -1, 1.0), (10, 1, 14, 8, 0.6)],
    "rocket": [(-8, -5, 25, 2, 0.75), (25, -6, 28, 3, 0.95), (4, 2, 8, 8, 0.55), (8, -9, 13, -5, 0.6)],
}
GUN_BASE = {"pistol": (70, 72, 80), "shotgun": (110, 75, 45), "machinegun": (60, 70, 80), "rocket": (70, 95, 60),
            "dual_pistols": (90, 90, 100), "smg": (55, 60, 70), "sniper": (70, 80, 60), "flamethrower": (120, 60, 40),
            "grenade_launcher": (60, 80, 50), "railgun": (60, 70, 100), "minigun": (70, 70, 75)}


def draw_gun(surface: pygame.Surface, kind: str, x: float, y: float, angle: float, scale: float = 1.0,
             recoil: float = 0.0) -> None:
    flip = math.cos(angle) < 0
    base = GUN_BASE.get(kind, (80, 80, 80))
    accent = WEAPONS[kind].color if kind in WEAPONS else (200, 200, 200)
    x -= math.cos(angle) * recoil * 4 * scale
    y -= math.sin(angle) * recoil * 4 * scale
    for (x0, y0, x1, y1, b) in GUN_SHAPES.get(kind, GUN_SHAPES["pistol"]):
        pts = transform_points([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], x, y, angle, flip, scale)
        pygame.draw.polygon(surface, shade(base, 0.6 + b * 0.8), pts)
    # coloured stripe so weapons are easy to tell apart
    x0, y0, x1, y1, _ = GUN_SHAPES.get(kind, GUN_SHAPES["pistol"])[1 if kind != "pistol" else 0]
    pts = transform_points([(x0 + 2, y0 + 1), (x1 - 2, y0 + 1)], x, y, angle, flip, scale)
    pygame.draw.line(surface, accent, pts[0], pts[1], max(1, int(scale)))


# ------------------------------------------------------------- background
class ParallaxBackground:
    """Sky gradient, sun/moon, clouds or stars and three silhouette layers
    that scroll at different speeds."""

    FACTORS = (0.15, 0.35, 0.6)

    def __init__(self, theme: Theme, size: Tuple[int, int] = (C.SCREEN_WIDTH, C.SCREEN_HEIGHT), seed: int = 7):
        self.theme = theme
        self.size = size
        rng = random.Random(seed)
        self.sky = vertical_gradient(size, theme.sky_top, theme.sky_bottom)
        w, h = size
        self.stars = [(rng.uniform(0, w * 1.5), rng.uniform(0, h * 0.7), rng.uniform(0.6, 2.0),
                       rng.uniform(0, 6.28)) for _ in range(140)] if theme.night else []
        self.clouds = [(rng.uniform(0, LAYER_WIDTH), rng.uniform(30, h * 0.4), rng.uniform(0.6, 1.4))
                       for _ in range(9)] if not theme.night else []
        self.layers = [self._mountains(rng, theme.far, h),
                       self._hills(rng, theme.mid, h),
                       self._near(rng, theme.near, h, theme.night)]

    # Each layer is LAYER_WIDTH wide and tiles seamlessly.
    def _mountains(self, rng, color, h) -> pygame.Surface:
        surf = pygame.Surface((LAYER_WIDTH, h), pygame.SRCALPHA)
        n = 16
        peaks = [(i * LAYER_WIDTH / n, h * rng.uniform(0.28, 0.55)) for i in range(n)]
        pts = [(0, h)] + peaks + [(LAYER_WIDTH, peaks[0][1]), (LAYER_WIDTH, h)]
        pygame.draw.polygon(surf, color, pts)
        snow = shade(color, 1.35)
        for i, (px, py) in enumerate(peaks):
            if py < h * 0.4:
                nx = peaks[(i + 1) % n][0] if i + 1 < n else LAYER_WIDTH
                pygame.draw.polygon(surf, snow, [(px, py), (px - 22, py + 30), (px + min(22, (nx - px) / 4), py + 26)])
        return surf

    def _hills(self, rng, color, h) -> pygame.Surface:
        surf = pygame.Surface((LAYER_WIDTH, h), pygame.SRCALPHA)
        ph = [rng.uniform(0, 6.28) for _ in range(3)]
        pts = [(0, h)]
        for x in range(0, LAYER_WIDTH + 1, 8):
            t = x / LAYER_WIDTH * math.tau
            y = h * 0.62 + math.sin(t * 3 + ph[0]) * 30 + math.sin(t * 7 + ph[1]) * 14 + math.sin(t * 13 + ph[2]) * 6
            pts.append((x, y))
        pts.append((LAYER_WIDTH, h))
        pygame.draw.polygon(surf, color, pts)
        return surf

    def _near(self, rng, color, h, night) -> pygame.Surface:
        surf = pygame.Surface((LAYER_WIDTH, h), pygame.SRCALPHA)
        base = h * 0.78
        pygame.draw.rect(surf, color, (0, base, LAYER_WIDTH, h - base))
        x = 0
        while x < LAYER_WIDTH - 60:
            if night:
                bw, bh = rng.randint(50, 110), rng.randint(60, 190)
                pygame.draw.rect(surf, color, (x, base - bh, bw, bh + 2))
                if rng.random() < 0.5:
                    pygame.draw.rect(surf, color, (x + bw // 3, base - bh - 40, 10, 40))
                for wy in range(int(base - bh + 10), int(base - 8), 16):
                    for wx in range(x + 8, x + bw - 10, 14):
                        if rng.random() < 0.3:
                            pygame.draw.rect(surf, (255, 210, 120) if rng.random() < 0.7 else (120, 200, 255),
                                             (wx, wy, 6, 8))
                x += bw + rng.randint(4, 30)
            else:
                th = rng.randint(50, 120)
                pygame.draw.rect(surf, shade(color, 0.8), (x + 14, base - th * 0.4, 8, th * 0.4 + 2))
                pygame.draw.circle(surf, color, (x + 18, int(base - th * 0.5)), th // 3)
                pygame.draw.circle(surf, color, (x + 6, int(base - th * 0.35)), th // 4)
                pygame.draw.circle(surf, color, (x + 30, int(base - th * 0.38)), th // 4)
                x += rng.randint(40, 140)
        return surf

    def draw(self, surface: pygame.Surface, cam_x: float, cam_y: float, t: float, level_h: float = None) -> None:
        w, h = self.size
        surface.blit(self.sky, (0, 0))
        if level_h is None:
            level_h = h
        rise = (level_h - h) - cam_y  # how far the camera is above the bottom
        if self.theme.night:
            for sx, sy, r, ph in self.stars:
                x = (sx - cam_x * 0.03) % (w * 1.5)
                if x < w:
                    tw = 0.5 + 0.5 * math.sin(t * 2.0 + ph)
                    pygame.draw.circle(surface, lerp_color((90, 90, 140), (255, 255, 255), tw), (int(x), int(sy)), r)
            mx, my = w * 0.78 - cam_x * 0.02 % 60, 90 + rise * 0.05
            blit_glow(surface, (60, 60, 90), (mx, my), 90)
            pygame.draw.circle(surface, (235, 235, 210), (int(mx), int(my)), 34)
            pygame.draw.circle(surface, self.theme.sky_top, (int(mx) + 14, int(my) - 8), 30)
        else:
            sx, sy = w * 0.8, 90 + rise * 0.05
            blit_glow(surface, (120, 100, 40), (sx, sy), 130)
            pygame.draw.circle(surface, (255, 240, 170), (int(sx), int(sy)), 40)
            for cx, cy, s in self.clouds:
                x = (cx + t * 12 * s - cam_x * 0.08) % LAYER_WIDTH - 150
                if -200 < x < w + 50:
                    self._cloud(surface, x, cy + rise * 0.08, s)
        for layer, f in zip(self.layers, self.FACTORS):
            ox = -(cam_x * f) % LAYER_WIDTH
            oy = rise * f * 0.5
            surface.blit(layer, (ox - LAYER_WIDTH, oy))
            surface.blit(layer, (ox, oy))

    @staticmethod
    def _cloud(surface, x, y, s) -> None:
        col = (255, 255, 255)
        for dx, dy, r in ((0, 0, 22), (24, -10, 28), (52, 0, 24), (26, 8, 22)):
            pygame.draw.circle(surface, col, (int(x + dx * s), int(y + dy * s)), int(r * s))


# --------------------------------------------------------------- tiles
def render_level_surface(level: Level) -> pygame.Surface:
    """Pre-render all static tiles of a level into one big surface."""
    th = level.theme
    T = C.TILE
    surf = pygame.Surface((level.pixel_width, level.pixel_height), pygame.SRCALPHA)
    rng = random.Random(level.name)
    for ty in range(level.height):
        for tx in range(level.width):
            ch = level.tiles[ty][tx]
            x, y = tx * T, ty * T
            if ch == "#":
                pygame.draw.rect(surf, th.ground, (x, y, T, T))
                # texture: a few darker stones
                for _ in range(3):
                    pygame.draw.rect(surf, th.ground_dark, (x + rng.randint(2, T - 10), y + rng.randint(6, T - 8),
                                                            rng.randint(4, 8), rng.randint(3, 5)), border_radius=2)
                if not level.is_solid(tx, ty + 1):
                    pygame.draw.rect(surf, th.ground_dark, (x, y + T - 4, T, 4))
                if not level.is_solid(tx - 1, ty):
                    pygame.draw.rect(surf, shade(th.ground, 0.8), (x, y, 3, T))
                if not level.is_solid(tx + 1, ty):
                    pygame.draw.rect(surf, shade(th.ground, 0.7), (x + T - 3, y, 3, T))
                if not level.is_solid(tx, ty - 1) and level.tile(tx, ty - 1) != "=":
                    pygame.draw.rect(surf, th.grass, (x, y, T, 7))
                    pygame.draw.rect(surf, shade(th.grass, 0.7), (x, y + 7, T, 3))
                    if th.night:
                        pygame.draw.line(surf, (200, 240, 255), (x, y), (x + T - 1, y), 1)
                    else:
                        for bx in range(x + 2, x + T, 5):
                            pygame.draw.line(surf, shade(th.grass, 1.2), (bx, y), (bx + 1, y - rng.randint(2, 5)), 2)
            elif ch == "=":
                pygame.draw.rect(surf, th.platform, (x, y, T, 10))
                pygame.draw.rect(surf, shade(th.platform, 1.25), (x, y, T, 3))
                pygame.draw.line(surf, shade(th.platform, 0.6), (x + T - 1, y), (x + T - 1, y + 9))
                pygame.draw.line(surf, shade(th.platform, 0.6), (x + 6, y + 10), (x + 10, y + 16), 3)
                pygame.draw.line(surf, shade(th.platform, 0.6), (x + T - 6, y + 10), (x + T - 10, y + 16), 3)
            elif ch == "^":
                for i in range(4):
                    sx = x + i * 8
                    pygame.draw.polygon(surf, (190, 195, 205), [(sx, y + T), (sx + 4, y + T - 18), (sx + 8, y + T)])
                    pygame.draw.line(surf, (250, 250, 255), (sx + 4, y + T - 18), (sx + 4, y + T - 12))
    return surf


# ------------------------------------------------------------- characters
def draw_player(surface: pygame.Surface, x: float, y: float, facing: int, run_phase: float = 0.0,
                squash: float = 0.0, aim_angle: float = 0.0, weapon: Optional[str] = "pistol",
                on_ground: bool = True, recoil: float = 0.0, vy: float = 0.0) -> None:
    """Draw the hero with feet centred at (x, y)."""
    sx = 1.0 + squash * 0.6
    sy = 1.0 - squash * 0.5
    w, h = C.PLAYER_WIDTH * sx, C.PLAYER_HEIGHT * sy
    left = x - w / 2
    top = y - h
    leg_h = 12 * sy
    # legs
    if on_ground:
        swing = math.sin(run_phase) * 7
    else:
        swing = 5 if vy < 0 else -3
    for i, s in enumerate((swing, -swing)):
        hx = x + (i * 2 - 1) * 4
        pygame.draw.line(surface, (40, 50, 80), (hx, y - leg_h), (hx + s * 0.8, y - 2), 5)
        pygame.draw.line(surface, (30, 30, 40), (hx + s * 0.8 - 2, y - 2), (hx + s * 0.8 + 4 * facing, y - 2), 4)
    # torso
    body = pygame.Rect(int(left + 2), int(top + 13 * sy), int(w - 4), int(h - 13 * sy - leg_h + 2))
    pygame.draw.rect(surface, (50, 120, 230), body, border_radius=5)
    pygame.draw.rect(surface, (90, 160, 255), body.inflate(-8, -8).move(0, -2), border_radius=3)
    pygame.draw.line(surface, (30, 40, 70), (body.left + 2, body.bottom - 4), (body.right - 2, body.bottom - 4), 3)
    # head
    hx, hy = x + facing * 1, top + 8 * sy
    pygame.draw.circle(surface, (255, 214, 170), (int(hx), int(hy)), 9)
    pygame.draw.rect(surface, (220, 50, 60), (hx - 10, hy - 10, 20, 6), border_radius=3)  # bandana
    tail = hx - facing * 10
    pygame.draw.line(surface, (220, 50, 60), (tail, hy - 7), (tail - facing * 6, hy - 3 + math.sin(run_phase) * 2), 3)
    ex = hx + facing * 4
    pygame.draw.circle(surface, (30, 30, 40), (int(ex), int(hy)), 2)
    # gun + arm
    shoulder = (x, top + 17 * sy)
    if weapon:
        pygame.draw.line(surface, (255, 214, 170), shoulder,
                         (shoulder[0] + math.cos(aim_angle) * 9, shoulder[1] + math.sin(aim_angle) * 9), 4)
        draw_gun(surface, weapon, shoulder[0], shoulder[1], aim_angle, 1.0, recoil)


def draw_soldier(surface: pygame.Surface, x: float, y: float, facing: int, phase: float, aim: float,
                 palette, gun: str = "machinegun", scale: float = 1.0, flash: bool = False,
                 moving: bool = True, windup: float = 0.0) -> None:
    """A humanoid soldier with feet centred at (x, y)."""
    S = scale
    uni = (255, 255, 255) if flash else palette["uniform"]
    dark = (230, 230, 230) if flash else palette["dark"]
    skin = (255, 255, 255) if flash else palette["skin"]
    helmet = (255, 255, 255) if flash else palette["helmet"]
    hip = (x, y - 18 * S)
    swing = math.sin(phase) * 0.55 if moving else 0.0
    for i, sign in enumerate((-1, 1)):  # back leg first
        a = swing * sign
        knee = (hip[0] + math.sin(a) * 10 * S, hip[1] + math.cos(a) * 9 * S)
        bend = max(0.0, math.sin(phase + (0 if sign > 0 else math.pi))) * 0.6 if moving else 0.0
        foot = (knee[0] + math.sin(a - bend * facing) * 9 * S, knee[1] + math.cos(a - bend) * 9 * S)
        col = dark if i == 0 else shade(uni, 0.9)
        pygame.draw.line(surface, col, hip, knee, max(2, int(5 * S)))
        pygame.draw.line(surface, col, knee, foot, max(2, int(5 * S)))
        pygame.draw.line(surface, (35, 30, 25), (foot[0] - 2 * S, foot[1]), (foot[0] + 5 * S * facing, foot[1]),
                         max(2, int(4 * S)))
    shoulder = (x, y - 31 * S)
    # back arm
    pygame.draw.line(surface, dark, shoulder, (x - facing * 4 * S, y - 20 * S), max(2, int(4 * S)))
    torso = pygame.Rect(0, 0, int(13 * S), int(17 * S))
    torso.midbottom = (int(x), int(y - 16 * S))
    pygame.draw.rect(surface, uni, torso, border_radius=int(3 * S))
    pygame.draw.line(surface, dark, (torso.left, torso.bottom - 3 * S), (torso.right - 1, torso.bottom - 3 * S),
                     max(1, int(2 * S)))
    pygame.draw.rect(surface, dark, (torso.left + 2 * S, torso.top + 3 * S, torso.width - 4 * S, 5 * S),
                     border_radius=2)
    # head with helmet
    hx, hy = x + facing * 1.5 * S, y - 39 * S
    pygame.draw.circle(surface, skin, (int(hx), int(hy)), int(6 * S))
    pygame.draw.circle(surface, helmet, (int(hx), int(hy - 2 * S)), int(6.5 * S), draw_top_left=True,
                       draw_top_right=True)
    pygame.draw.line(surface, shade(helmet, 0.7), (hx - 7 * S, hy - 2 * S), (hx + 7 * S, hy - 2 * S), max(1, int(2 * S)))
    pygame.draw.circle(surface, (25, 25, 30), (int(hx + facing * 3 * S), int(hy + 1 * S)), max(1, int(1.5 * S)))
    # front arm aiming the gun
    arm_end = (shoulder[0] + math.cos(aim) * 9 * S, shoulder[1] + math.sin(aim) * 9 * S)
    pygame.draw.line(surface, uni, shoulder, arm_end, max(2, int(5 * S)))
    draw_gun(surface, gun, shoulder[0], shoulder[1] + 1, aim, S)
    if windup > 0:
        gx, gy = shoulder[0] + math.cos(aim) * 24 * S, shoulder[1] + math.sin(aim) * 24 * S
        blit_glow(surface, (255, 60, 90), (gx, gy), 10 + 10 * windup)


def draw_enemy(surface: pygame.Surface, e, ox: float, oy: float, t: float) -> None:
    b = e.body
    x, y = b.x - ox, b.y - oy
    flash = e.hurt_flash > 0
    if getattr(e, "human", False):
        windup = (1 - e.windup / e.WINDUP) if e.windup > 0 else 0.0
        draw_soldier(surface, b.cx - ox, b.bottom - oy, e.facing, e.walk_phase, e.aim_angle, e.PALETTE, e.GUN,
                     e.SCALE, flash, abs(b.vx) > 5, windup)
        if e.muzzle_flash > 0:
            gx, gy = e.gun_pos()
            blit_glow(surface, (255, 220, 150), (gx - ox, gy - oy), 14)
    elif e.kind == "walker":
        col = (255, 255, 255) if flash else (220, 90, 60)
        bob = abs(math.sin(e.anim * 9)) * 2
        r = pygame.Rect(int(x), int(y + bob), int(b.w), int(b.h - 4))
        pygame.draw.rect(surface, col, r, border_radius=9)
        pygame.draw.rect(surface, shade(col, 0.75), r.inflate(-6, -14).move(0, 5), border_radius=6)
        for i in (0, 1):
            fx = x + 6 + i * (b.w - 12) + math.sin(e.anim * 9 + i * math.pi) * 3
            pygame.draw.ellipse(surface, (60, 30, 30), (fx - 5, y + b.h - 6, 10, 6))
        ex = x + b.w / 2 + e.facing * 6
        for d in (-4, 4):
            pygame.draw.circle(surface, (255, 255, 255), (int(ex + d), int(y + 10 + bob)), 4)
            pygame.draw.circle(surface, (20, 20, 20), (int(ex + d + e.facing * 1.5), int(y + 10 + bob)), 2)
        pygame.draw.line(surface, (40, 20, 20), (ex - 8, y + 4 + bob), (ex - 1, y + 7 + bob), 2)
        pygame.draw.line(surface, (40, 20, 20), (ex + 8, y + 4 + bob), (ex + 1, y + 7 + bob), 2)
    else:  # drone
        col = (255, 255, 255) if flash else (90, 200, 170)
        cy = y + b.h / 2 + math.sin(t * 6 + e.anim) * 2
        pygame.draw.ellipse(surface, col, (x, cy - 9, b.w, 18))
        pygame.draw.ellipse(surface, shade(col, 0.6), (x + 4, cy, b.w - 8, 8))
        spin = abs(math.sin(t * 40 + e.anim)) * 12 + 2
        for px in (x + 4, x + b.w - 4):
            pygame.draw.line(surface, (200, 200, 210), (px, cy - 11), (px, cy - 9), 2)
            pygame.draw.line(surface, (220, 220, 230), (px - spin / 2, cy - 12), (px + spin / 2, cy - 12), 2)
        eye_col = (255, 60, 60) if e.chasing else (255, 210, 80)
        pygame.draw.circle(surface, eye_col, (int(x + b.w / 2 + e.facing * 6), int(cy - 1)), 4)
        blit_glow(surface, eye_col, (x + b.w / 2 + e.facing * 6, cy - 1), 10, 0.6)
    if e.health < e.MAX_HEALTH:
        frac = e.health / e.MAX_HEALTH
        pygame.draw.rect(surface, (30, 30, 30), (x - 2, y - 10, b.w + 4, 5))
        pygame.draw.rect(surface, lerp_color((230, 60, 60), (100, 230, 100), frac), (x - 1, y - 9, (b.w + 2) * frac, 3))


def draw_barrel(surface: pygame.Surface, bar, ox: float, oy: float, t: float) -> None:
    b = bar.body
    x, y = int(b.x - ox), int(b.y - oy)
    w, h = int(b.w), int(b.h)
    blink = bar.triggered and int(t * 30) % 2 == 0
    col = (255, 240, 200) if (blink or bar.hurt_flash > 0) else (190, 40, 35)
    pygame.draw.rect(surface, col, (x, y + 3, w, h - 3), border_radius=4)
    pygame.draw.ellipse(surface, shade(col, 1.2), (x, y, w, 7))
    for by in (y + 9, y + h - 8):
        pygame.draw.rect(surface, shade(col, 0.6), (x, by, w, 3))
    pygame.draw.polygon(surface, (250, 210, 40), [(x + w // 2, y + 12), (x + w // 2 - 6, y + 22), (x + w // 2 + 6, y + 22)])
    pygame.draw.line(surface, (30, 30, 30), (x + w // 2, y + 15), (x + w // 2, y + 19), 2)
    pygame.draw.line(surface, shade(col, 1.35), (x + 4, y + 5), (x + 4, y + h - 3), 2)


_CORPSE_SURF = {}


def draw_corpse(surface: pygame.Surface, c, ox: float, oy: float, t: float) -> None:
    size = int(90 * c.scale)
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = size / 2
    if c.palette:
        draw_soldier(surf, cx, cx + 21 * c.scale, c.facing, 0.0, 0.3 if c.facing > 0 else math.pi - 0.3,
                     c.palette, c.gun, c.scale, moving=False)
    else:  # walker blob
        pygame.draw.rect(surf, (150, 60, 40), (cx - 14, cx - 14, 28, 26), border_radius=9)
        for d in (-4, 4):
            pygame.draw.line(surf, (30, 20, 20), (cx + d - 2, cx - 6), (cx + d + 2, cx - 2), 2)
            pygame.draw.line(surf, (30, 20, 20), (cx + d + 2, cx - 6), (cx + d - 2, cx - 2), 2)
    if c.burning:
        surf.fill((90, 60, 50, 255), special_flags=pygame.BLEND_RGBA_MULT)
    rot = pygame.transform.rotate(surf, -math.degrees(c.angle) * c.facing)
    if c.life < 1.0:
        rot.set_alpha(int(255 * max(0.0, c.life)))
    b = c.body
    surface.blit(rot, rot.get_rect(center=(int(b.cx - ox), int(b.bottom - 7 - oy))))


def draw_decal(surface: pygame.Surface, d) -> None:
    r = max(1.5, d.radius)
    col = shade(d.color, 0.85)
    if d.surface == "floor":
        rect = (d.x - r * 1.6, d.y - r * 0.25, r * 3.2, r * 0.9)
    elif d.surface == "ceiling":
        rect = (d.x - r, d.y - r * 0.5, r * 2, r * 1.2)
    else:
        rect = (d.x - r * 0.45, d.y - r * 1.3, r * 0.9, r * 2.6)
    pygame.draw.ellipse(surface, col, rect)


def draw_pickup(surface: pygame.Surface, item, ox: float, oy: float, t: float) -> None:
    bob = math.sin(t * 3 + item.phase) * 4
    cx, cy = item.cx - ox, item.cy - oy + bob
    if item.is_weapon:
        color = WEAPONS[item.kind].color
        blit_glow(surface, color, (cx, cy), 26, 0.55 + 0.2 * math.sin(t * 4 + item.phase))
        draw_gun(surface, item.kind, cx - 12, cy + 1, 0.0, 1.15)
    elif item.kind == "health":
        blit_glow(surface, (200, 60, 60), (cx, cy), 22, 0.6)
        r = pygame.Rect(0, 0, 22, 18)
        r.center = (int(cx), int(cy))
        pygame.draw.rect(surface, (245, 245, 245), r, border_radius=4)
        pygame.draw.rect(surface, (220, 40, 50), (r.centerx - 2, r.top + 3, 5, 12))
        pygame.draw.rect(surface, (220, 40, 50), (r.left + 5, r.centery - 2, 12, 5))
    else:  # ammo crate
        blit_glow(surface, (200, 170, 60), (cx, cy), 22, 0.5)
        r = pygame.Rect(0, 0, 24, 18)
        r.center = (int(cx), int(cy))
        pygame.draw.rect(surface, (90, 110, 50), r, border_radius=3)
        pygame.draw.rect(surface, (60, 75, 35), r, 2, border_radius=3)
        for i in range(3):
            bx = r.left + 6 + i * 6
            pygame.draw.rect(surface, (230, 190, 70), (bx - 1, r.top + 4, 3, 9))


def draw_checkpoint(surface: pygame.Surface, cp, ox: float, oy: float, t: float) -> None:
    x, y = cp.x - ox, cp.y - oy
    pygame.draw.rect(surface, (200, 200, 210), (x + 6, y, 4, cp.h))
    pygame.draw.rect(surface, (90, 90, 100), (x, y + cp.h - 6, 16, 6), border_radius=2)
    col = (80, 230, 120) if cp.active else (150, 150, 160)
    wave = math.sin(t * 6) * 3 if cp.active else 0
    pygame.draw.polygon(surface, col, [(x + 10, y + 2), (x + 34, y + 10 + wave), (x + 10, y + 20)])
    if cp.active:
        blit_glow(surface, (60, 200, 100), (x + 20, y + 10), 24, 0.6)


def draw_goal(surface: pygame.Surface, goal, ox: float, oy: float, t: float) -> None:
    x, y = goal.x - ox + 14, goal.y - oy
    blit_glow(surface, (160, 130, 40), (x + 20, y + 20), 60, 0.5 + 0.2 * math.sin(t * 3))
    pygame.draw.rect(surface, (230, 230, 240), (x, y, 5, goal.h))
    pygame.draw.circle(surface, (255, 210, 80), (x + 2, y), 6)
    cols, rows, cell = 6, 4, 8
    for i in range(cols):
        for j in range(rows):
            wave = math.sin(t * 5 - i * 0.7) * (i * 1.2)
            px, py = x + 5 + i * cell, y + 4 + j * cell + wave
            color = (250, 250, 250) if (i + j) % 2 == 0 else (30, 30, 40)
            pygame.draw.rect(surface, color, (px, py, cell, cell))


# ------------------------------------------------------------------ world
class WorldRenderer:
    def __init__(self, size: Tuple[int, int] = (C.SCREEN_WIDTH, C.SCREEN_HEIGHT)) -> None:
        self.size = size
        self._level_key = None
        self.level_surface: Optional[pygame.Surface] = None
        self.background: Optional[ParallaxBackground] = None

    def _prepare(self, world) -> None:
        key = (world.level_index, id(world.level))
        if key != self._level_key:
            self._level_key = key
            self.level_surface = render_level_surface(world.level)
            if pygame.display.get_surface() is not None:
                self.level_surface = self.level_surface.convert_alpha()
            self.background = ParallaxBackground(world.level.theme, self.size, seed=world.level_index + 3)

    def draw(self, surface: pygame.Surface, world) -> None:
        self._prepare(world)
        t = world.time
        cam = world.camera
        sx, sy = world.effects.shake_offset()
        ox, oy = int(cam.x + sx), int(cam.y + sy)
        self.background.draw(surface, cam.x, cam.y, t, world.level.pixel_height)
        fx = world.effects
        for d in fx.new_decals:  # stamp blood permanently into the level surface
            draw_decal(self.level_surface, d)
        fx.new_decals.clear()
        surface.blit(self.level_surface, (-ox, -oy))
        for bar in getattr(world, "barrels", []):
            draw_barrel(surface, bar, ox, oy, t)
        for c in getattr(world, "corpses", []):
            draw_corpse(surface, c, ox, oy, t)

        for cp in world.checkpoints:
            draw_checkpoint(surface, cp, ox, oy, t)
        if world.goal:
            draw_goal(surface, world.goal, ox, oy, t)
        for item in world.pickups:
            draw_pickup(surface, item, ox, oy, t)
        for e in world.enemies:
            draw_enemy(surface, e, ox, oy, t)

        p = world.player
        if p.alive and not (p.invulnerable > 0 and int(p.invulnerable * 14) % 2 == 0):
            b = p.body
            draw_player(surface, b.cx - ox, b.bottom - oy, p.facing, p.run_phase, p.squash, p.aim_angle,
                        p.current, b.on_ground, p.recoil_anim, b.vy)

        for pr in world.projectiles:
            x, y = pr.x - ox, pr.y - oy
            if pr.kind == "flame":
                k = min(1.0, pr.age / pr.lifetime)
                col = lerp_color((255, 220, 120), (200, 40, 10), k)
                blit_glow(surface, col, (x, y), 8 + 26 * k, 1.0 - k * 0.6)
                continue
            if pr.kind == "grenade":
                pygame.draw.circle(surface, (60, 90, 50), (int(x), int(y)), 5)
                pygame.draw.circle(surface, (120, 150, 90), (int(x - 1), int(y - 2)), 2)
                if int(pr.age * (8 + pr.age * 10)) % 2 == 0:
                    blit_glow(surface, (255, 50, 50), (x, y - 4), 8)
                continue
            if pr.kind == "rocket":
                tail = (x - pr.dir_x * 16, y - pr.dir_y * 16)
                blit_glow(surface, (255, 140, 40), tail, 16 + math.sin(t * 50) * 3)
                pygame.draw.line(surface, (200, 200, 190), tail, (x, y), 7)
                pygame.draw.circle(surface, (255, 90, 80), (int(x), int(y)), 4)
            else:
                tail = (x - pr.dir_x * min(18, pr.speed * 0.02), y - pr.dir_y * min(18, pr.speed * 0.02))
                blit_glow(surface, pr.color, (x, y), pr.radius * 4, 0.7)
                pygame.draw.line(surface, pr.color, tail, (x, y), max(2, int(pr.radius)))
                pygame.draw.circle(surface, (255, 255, 240), (int(x), int(y)), max(1, int(pr.radius * 0.7)))

        for part in fx.particles:
            x, y = part.x - ox, part.y - oy
            if -20 < x < self.size[0] + 20 and -20 < y < self.size[1] + 20:
                r = max(1, int(part.size * (0.4 + 0.6 * part.t)))
                if part.kind == "smoke":
                    r = max(1, int(part.size * (1.6 - part.t)))
                    pygame.draw.circle(surface, lerp_color(part.color, (140, 140, 145), 1 - part.t), (int(x), int(y)), r)
                elif part.kind == "casing":
                    pygame.draw.rect(surface, part.color, (int(x) - 2, int(y) - 1, 4, 2))
                elif part.kind in ("gib", "debris", "blood"):
                    pygame.draw.circle(surface, part.color, (int(x), int(y)), max(1, int(part.size)))
                elif part.glow:
                    blit_glow(surface, part.color, (x, y), r * 3, part.t)
                    pygame.draw.circle(surface, lerp_color(part.color, (255, 255, 255), 0.4), (int(x), int(y)), max(1, r // 2 + 1))
                else:
                    pygame.draw.circle(surface, part.color, (int(x), int(y)), r)
        for ring in fx.rings:
            k = ring.life / ring.max_life
            rr = int(ring.radius)
            if rr > 2:
                rs = pygame.Surface((rr * 2 + 8, rr * 2 + 8), pygame.SRCALPHA)
                pygame.draw.circle(rs, (*ring.color, int(220 * k)), (rr + 4, rr + 4), rr, max(2, int(8 * k)))
                surface.blit(rs, (ring.x - ox - rr - 4, ring.y - oy - rr - 4))
        for bm in fx.beams:
            k = bm.life / bm.max_life
            a, b2 = (bm.x0 - ox, bm.y0 - oy), (bm.x1 - ox, bm.y1 - oy)
            pygame.draw.line(surface, bm.color, a, b2, max(1, int(12 * k)))
            pygame.draw.line(surface, (255, 255, 255), a, b2, max(1, int(5 * k)))
            blit_glow(surface, bm.color, b2, 30 * k + 4)
        for fl in fx.flashes:
            k = fl.life / fl.max_life
            blit_glow(surface, fl.color, (fl.x - ox, fl.y - oy), fl.radius * (1.5 + (1 - k)), k)
        for txt in fx.texts:
            a = int(255 * min(1.0, txt.life / txt.max_life * 2))
            draw_text(surface, txt.text, (txt.x - ox, txt.y - oy), 26, txt.color, anchor="center", bold=True, alpha=a)


# -------------------------------------------------------------------- HUD
def draw_heart(surface: pygame.Surface, x: float, y: float, size: float, color) -> None:
    r = size * 0.3
    pygame.draw.circle(surface, color, (int(x - r), int(y)), int(r) + 1)
    pygame.draw.circle(surface, color, (int(x + r), int(y)), int(r) + 1)
    pygame.draw.polygon(surface, color, [(x - size * 0.6, y + 1), (x + size * 0.6, y + 1), (x, y + size * 0.7)])


def draw_hud(surface: pygame.Surface, world) -> None:
    p = world.player
    w, h = surface.get_size()
    # health bar
    panel = pygame.Surface((216, 64), pygame.SRCALPHA)
    pygame.draw.rect(panel, (10, 12, 24, 160), panel.get_rect(), border_radius=10)
    surface.blit(panel, (12, 12))
    draw_heart(surface, 34, 33, 20, (235, 70, 80))
    frac = max(0.0, p.health / p.max_health)
    pygame.draw.rect(surface, (40, 40, 50), (52, 24, 150, 18), border_radius=6)
    col = lerp_color((235, 60, 60), (90, 220, 120), frac)
    if frac > 0:
        pygame.draw.rect(surface, col, (52, 24, int(150 * frac), 18), border_radius=6)
        pygame.draw.rect(surface, shade(col, 1.3), (56, 26, max(0, int(150 * frac) - 8), 4), border_radius=2)
    draw_text(surface, f"{max(0, int(p.health))}", (127, 33), 22, (255, 255, 255), anchor="center", bold=True)
    for i in range(world.lives):
        pygame.draw.circle(surface, (255, 214, 170), (60 + i * 22, 58), 7)
        pygame.draw.rect(surface, (220, 50, 60), (53 + i * 22, 50, 14, 4), border_radius=2)
    draw_text(surface, "LIVES", (130, 58), 20, (200, 200, 210), anchor="midleft")

    # score / level / time
    draw_text(surface, f"SCORE {world.score:06d}", (w - 16, 14), 30, (255, 230, 140), anchor="topright", bold=True)
    draw_text(surface, world.level.name, (w - 16, 42), 22, (210, 215, 230), anchor="topright")
    m, s = divmod(int(world.level_time), 60)
    draw_text(surface, f"TIME {m}:{s:02d}   KILLS {world.kills}", (w - 16, 62), 22, (210, 215, 230), anchor="topright")

    # weapon slots (keys 1-9, 0)
    slot_w, slot_h, gap = 44, 46, 4
    x0 = w // 2 - (len(WEAPON_ORDER) * (slot_w + gap) - gap) // 2
    y0 = 10
    for i, key in enumerate(WEAPON_ORDER):
        r = pygame.Rect(x0 + i * (slot_w + gap), y0, slot_w, slot_h)
        owned = key in p.weapons
        current = key == p.current
        bg = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (10, 12, 24, 200 if current else 120), bg.get_rect(), border_radius=7)
        border = (255, 196, 64, 255) if current else (255, 255, 255, 45)
        pygame.draw.rect(bg, border, bg.get_rect(), width=3 if current else 1, border_radius=7)
        surface.blit(bg, r.topleft)
        draw_text(surface, str((i + 1) % 10), (r.left + 4, r.top + 2), 16, (170, 170, 185))
        if owned:
            draw_gun(surface, key, r.centerx - 11, r.top + 19, 0.0, 0.75)
            wpn = p.weapons[key]
            ammo = "INF" if wpn.infinite else str(wpn.ammo)
            col = (255, 255, 255) if wpn.has_ammo else (230, 80, 80)
            draw_text(surface, ammo, (r.centerx, r.bottom - 10), 18, col, anchor="center", bold=True)
        else:
            draw_text(surface, "-", (r.centerx, r.centery + 2), 22, (90, 90, 100), anchor="center")
    spec = p.weapon.spec
    draw_text(surface, spec.name.upper(), (w // 2, y0 + slot_h + 13), 24, spec.color, anchor="center", bold=True)
    if getattr(world, "muted", False):
        draw_text(surface, "MUTED (M)", (w - 16, 84), 20, (255, 150, 150), anchor="topright")


def draw_crosshair(surface: pygame.Surface, pos, t: float) -> None:
    x, y = pos
    r = 10 + math.sin(t * 6) * 1.5
    pygame.draw.circle(surface, (255, 255, 255), (int(x), int(y)), int(r), 2)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        pygame.draw.line(surface, (255, 255, 255), (x + dx * (r - 4), y + dy * (r - 4)),
                         (x + dx * (r + 5), y + dy * (r + 5)), 2)
    pygame.draw.circle(surface, (255, 80, 80), (int(x), int(y)), 2)
