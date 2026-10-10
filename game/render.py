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
    key = (tuple(color[:3]), radius)
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
    "shotgun": [(-4, -2, 6, 3, 0.55), (4, -3, 27, 0, 0.8), (11, 0, 21, 3, 0.6)],
    "machinegun": [(-2, -3, 6, 2, 0.55), (4, -4, 22, 1, 0.8), (21, -3, 29, -1, 1.0), (10, 1, 14, 8, 0.6)],
    "rocket": [(-8, -5, 25, 2, 0.75), (25, -6, 28, 3, 0.95), (4, 2, 8, 8, 0.55), (8, -9, 13, -5, 0.6)],
}
GUN_BASE = {"pistol": (70, 72, 80), "shotgun": (110, 75, 45), "machinegun": (60, 70, 80), "rocket": (70, 95, 60)}


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


def draw_enemy(surface: pygame.Surface, e, ox: float, oy: float, t: float) -> None:
    b = e.body
    x, y = b.x - ox, b.y - oy
    flash = e.hurt_flash > 0
    if e.kind == "walker":
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
    elif e.kind == "shooter":
        col = (255, 255, 255) if flash else (140, 80, 200)
        r = pygame.Rect(int(x), int(y), int(b.w), int(b.h))
        pygame.draw.rect(surface, col, r, border_radius=6)
        pygame.draw.rect(surface, shade(col, 0.7), (x + 3, y + b.h - 10, b.w - 6, 10), border_radius=3)
        visor = pygame.Rect(int(x + 4 + (4 if e.facing > 0 else 0)), int(y + 7), int(b.w - 12), 7)
        glow = 1.0 if e.windup > 0 else 0.6
        pygame.draw.rect(surface, shade((255, 60, 90), glow + 0.2), visor, border_radius=3)
        if e.windup > 0:
            gx, gy = e.gun_pos()
            blit_glow(surface, (255, 60, 90), (gx - ox, gy - oy), 14 + 10 * (1 - e.windup / e.WINDUP))
        draw_gun(surface, "machinegun", b.cx - ox, y + 16, 0.0 if e.facing > 0 else math.pi, 0.9)
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
        surface.blit(self.level_surface, (-ox, -oy))

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

        fx = world.effects
        for part in fx.particles:
            x, y = part.x - ox, part.y - oy
            if -20 < x < self.size[0] + 20 and -20 < y < self.size[1] + 20:
                r = max(1, int(part.size * (0.4 + 0.6 * part.t)))
                if part.glow:
                    blit_glow(surface, part.color, (x, y), r * 3, part.t)
                    pygame.draw.circle(surface, lerp_color(part.color, (255, 255, 255), 0.4), (int(x), int(y)), max(1, r // 2 + 1))
                else:
                    pygame.draw.circle(surface, part.color, (int(x), int(y)), r)
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
    panel = pygame.Surface((270, 64), pygame.SRCALPHA)
    pygame.draw.rect(panel, (10, 12, 24, 160), panel.get_rect(), border_radius=10)
    surface.blit(panel, (12, 12))
    draw_heart(surface, 34, 33, 20, (235, 70, 80))
    frac = max(0.0, p.health / p.max_health)
    pygame.draw.rect(surface, (40, 40, 50), (52, 24, 200, 18), border_radius=6)
    col = lerp_color((235, 60, 60), (90, 220, 120), frac)
    if frac > 0:
        pygame.draw.rect(surface, col, (52, 24, int(200 * frac), 18), border_radius=6)
        pygame.draw.rect(surface, shade(col, 1.3), (56, 26, max(0, int(200 * frac) - 8), 4), border_radius=2)
    draw_text(surface, f"{max(0, int(p.health))}", (152, 33), 22, (255, 255, 255), anchor="center", bold=True)
    for i in range(world.lives):
        pygame.draw.circle(surface, (255, 214, 170), (60 + i * 22, 58), 7)
        pygame.draw.rect(surface, (220, 50, 60), (53 + i * 22, 50, 14, 4), border_radius=2)
    draw_text(surface, "LIVES", (140, 58), 20, (200, 200, 210), anchor="midleft")

    # score / level / time
    draw_text(surface, f"SCORE {world.score:06d}", (w - 16, 14), 30, (255, 230, 140), anchor="topright", bold=True)
    draw_text(surface, world.level.name, (w - 16, 42), 22, (210, 215, 230), anchor="topright")
    m, s = divmod(int(world.level_time), 60)
    draw_text(surface, f"TIME {m}:{s:02d}   KILLS {world.kills}", (w - 16, 62), 22, (210, 215, 230), anchor="topright")

    # weapon slots
    slot_w, slot_h = 76, 52
    x0 = w // 2 - (4 * slot_w + 3 * 8) // 2
    y0 = 12
    for i, key in enumerate(WEAPON_ORDER):
        r = pygame.Rect(x0 + i * (slot_w + 8), y0, slot_w, slot_h)
        owned = key in p.weapons
        current = key == p.current
        bg = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (10, 12, 24, 190 if current else 130), bg.get_rect(), border_radius=8)
        border = (255, 196, 64, 255) if current else (255, 255, 255, 50)
        pygame.draw.rect(bg, border, bg.get_rect(), width=3 if current else 1, border_radius=8)
        surface.blit(bg, r.topleft)
        draw_text(surface, str(i + 1), (r.left + 6, r.top + 4), 18, (180, 180, 190))
        if owned:
            draw_gun(surface, key, r.centerx - 12, r.top + 20, 0.0, 1.0)
            wpn = p.weapons[key]
            ammo = "INF" if wpn.infinite else str(wpn.ammo)
            col = (255, 255, 255) if wpn.has_ammo else (230, 80, 80)
            draw_text(surface, ammo, (r.centerx, r.bottom - 12), 22, col, anchor="center", bold=True)
        else:
            draw_text(surface, "-", (r.centerx, r.centery), 26, (90, 90, 100), anchor="center")
    spec = p.weapon.spec
    draw_text(surface, spec.name.upper(), (w // 2, y0 + slot_h + 14), 24, spec.color, anchor="center", bold=True)


def draw_crosshair(surface: pygame.Surface, pos, t: float) -> None:
    x, y = pos
    r = 10 + math.sin(t * 6) * 1.5
    pygame.draw.circle(surface, (255, 255, 255), (int(x), int(y)), int(r), 2)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        pygame.draw.line(surface, (255, 255, 255), (x + dx * (r - 4), y + dy * (r - 4)),
                         (x + dx * (r + 5), y + dy * (r + 5)), 2)
    pygame.draw.circle(surface, (255, 80, 80), (int(x), int(y)), 2)
