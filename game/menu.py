"""Start screen with an animated background, the controls screen and the
shared scene protocol:

* ``handle_event(event) -> Optional[str]`` returns an action
  (``"play"``, ``"controls"``, ``"menu"`` or ``"quit"``),
* ``update(dt)`` advances animations,
* ``draw(screen)`` renders the scene.
"""
from __future__ import annotations

import math
import random
from typing import List, Optional, Tuple

import pygame

from . import constants as C
from .levels import DAY
from .render import ParallaxBackground, blit_glow, draw_player, lerp_color, shade
from .settings import Settings
from .ui import MenuList, draw_panel, draw_text, font

TITLE = "JUMP 'N' RUN"


class MenuBackground:
    """Endless parallax landscape with a little hero running, jumping and
    shooting across it - a live preview of the game behind the menus."""

    GROUND_Y = C.SCREEN_HEIGHT - 70

    def __init__(self, size: Tuple[int, int] = (C.SCREEN_WIDTH, C.SCREEN_HEIGHT), seed: Optional[int] = None):
        self.size = size
        self.rng = random.Random(seed)
        self.parallax = ParallaxBackground(DAY, size, seed=11)
        self.time = 0.0
        self.scroll = 0.0
        self.hero_x = -40.0
        self.jump_t = -1.0       # time since jump start, <0 = on ground
        self.next_jump = 1.2
        self.shoot_timer = 0.8
        self.bullets: List[List[float]] = []
        self.sparks: List[List[float]] = []
        self.fireflies = [[self.rng.uniform(0, size[0]), self.rng.uniform(0, size[1] * 0.8),
                           self.rng.uniform(0, 6.28)] for _ in range(30)]

    def hero_y(self) -> float:
        if self.jump_t < 0:
            return self.GROUND_Y
        v, g = 620.0, 1800.0
        return self.GROUND_Y - (v * self.jump_t - 0.5 * g * self.jump_t ** 2)

    def update(self, dt: float) -> None:
        self.time += dt
        self.scroll += 90 * dt
        self.hero_x += 150 * dt
        if self.hero_x > self.size[0] + 60:
            self.hero_x = -60
        self.next_jump -= dt
        if self.jump_t >= 0:
            self.jump_t += dt
            if self.hero_y() >= self.GROUND_Y and self.jump_t > 0.1:
                self.jump_t = -1.0
        elif self.next_jump <= 0:
            self.jump_t = 0.0
            self.next_jump = self.rng.uniform(1.0, 2.5)
        self.shoot_timer -= dt
        if self.shoot_timer <= 0:
            self.shoot_timer = self.rng.uniform(0.25, 1.4)
            y = self.hero_y() - 23
            self.bullets.append([self.hero_x + 26, y])
            for _ in range(5):
                self.sparks.append([self.hero_x + 26, y, self.rng.uniform(80, 260), self.rng.uniform(-80, 80), 0.15])
        for b in self.bullets:
            b[0] += 900 * dt
        self.bullets = [b for b in self.bullets if b[0] < self.size[0] + 20]
        for s in self.sparks:
            s[0] += s[2] * dt
            s[1] += s[3] * dt
            s[4] -= dt
        self.sparks = [s for s in self.sparks if s[4] > 0]
        for f in self.fireflies:
            f[0] = (f[0] + math.sin(self.time * 0.7 + f[2]) * 12 * dt + 8 * dt) % self.size[0]
            f[1] += math.cos(self.time * 0.9 + f[2]) * 10 * dt

    def draw(self, surface: pygame.Surface) -> None:
        w, h = self.size
        self.parallax.draw(surface, self.scroll, 0, self.time, h)
        # scrolling ground strip
        gy = self.GROUND_Y
        pygame.draw.rect(surface, DAY.ground, (0, gy, w, h - gy))
        pygame.draw.rect(surface, DAY.grass, (0, gy, w, 7))
        pygame.draw.rect(surface, shade(DAY.grass, 0.7), (0, gy + 7, w, 3))
        off = -(self.scroll * 1.0) % C.TILE
        for i in range(-1, w // C.TILE + 2):
            x = off + i * C.TILE
            pygame.draw.rect(surface, DAY.ground_dark, (x + 6, gy + 22, 8, 5), border_radius=2)
            pygame.draw.rect(surface, DAY.ground_dark, (x + 20, gy + 44, 6, 4), border_radius=2)
        on_ground = self.jump_t < 0
        draw_player(surface, self.hero_x, self.hero_y(), 1, self.time * 14, 0.0, 0.0,
                    "machinegun", on_ground, 0.0, -1 if self.jump_t < 0.35 else 1)
        for b in self.bullets:
            blit_glow(surface, (120, 230, 255), (b[0], b[1]), 12, 0.7)
            pygame.draw.line(surface, (120, 230, 255), (b[0] - 14, b[1]), (b[0], b[1]), 3)
        for s in self.sparks:
            blit_glow(surface, (255, 220, 120), (s[0], s[1]), 6, s[4] / 0.15)
        for f in self.fireflies:
            a = 0.5 + 0.5 * math.sin(self.time * 3 + f[2])
            blit_glow(surface, (255, 240, 150), (f[0], f[1]), 10, a * 0.7)
        # subtle vignette at the top for title readability
        shade_surf = pygame.Surface((w, 200), pygame.SRCALPHA)
        for y in range(200):
            pygame.draw.line(shade_surf, (0, 0, 20, int(110 * (1 - y / 200))), (0, y), (w, y))
        surface.blit(shade_surf, (0, 0))


class Title:
    """Bouncing, colour-cycling title letters with a glow."""

    def __init__(self, text: str = TITLE) -> None:
        self.text = text
        self.time = 0.0

    def update(self, dt: float) -> None:
        self.time += dt

    def draw(self, surface: pygame.Surface, center: Tuple[int, int], size: int = 110) -> None:
        f = font(size, True)
        widths = [f.size(ch)[0] for ch in self.text]
        total = sum(widths)
        x = center[0] - total / 2
        for i, ch in enumerate(self.text):
            phase = self.time * 3.2 - i * 0.45
            dy = -abs(math.sin(phase)) * 16
            hue = 0.5 + 0.5 * math.sin(self.time * 1.5 + i * 0.4)
            col = lerp_color((255, 196, 64), (255, 110, 90), hue)
            if ch != " ":
                blit_glow(surface, shade(col, 0.5), (x + widths[i] / 2, center[1] + dy), size * 0.45, 0.6)
                outline = f.render(ch, True, (40, 20, 30))
                for ox, oy in ((-3, 0), (3, 0), (0, -3), (0, 3), (3, 4)):
                    surface.blit(outline, outline.get_rect(midtop=(x + widths[i] / 2 + ox, center[1] + dy - size * 0.35 + oy)))
                img = f.render(ch, True, col)
                surface.blit(img, img.get_rect(midtop=(x + widths[i] / 2, center[1] + dy - size * 0.35)))
            x += widths[i]


class MainMenu:
    ITEMS = ["Play", "Controls", "Settings", "Quit"]
    ACTIONS = ["play", "controls", "settings", "quit"]

    def __init__(self, background: MenuBackground, title: Title, size=(C.SCREEN_WIDTH, C.SCREEN_HEIGHT)) -> None:
        self.background = background
        self.title = title
        self.size = size
        self.menu = MenuList(self.ITEMS, (size[0] // 2, int(size[1] * 0.62)), spacing=56, size=46)
        self.time = 0.0

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return "quit"
        chosen = self.menu.handle_event(event)
        return None if chosen is None else self.ACTIONS[chosen]

    def update(self, dt: float) -> None:
        self.time += dt
        self.background.update(dt)
        self.title.update(dt)
        self.menu.update(dt)

    def draw(self, surface: pygame.Surface) -> None:
        w, h = self.size
        self.background.draw(surface)
        self.title.draw(surface, (w // 2, 120))
        draw_text(surface, "run  -  jump  -  shoot", (w // 2, 182), 30, (230, 235, 250), anchor="center")
        r = pygame.Rect(0, 0, 320, 250)
        r.center = (w // 2, int(h * 0.62))
        draw_panel(surface, r, alpha=120)
        self.menu.draw(surface)
        a = int(160 + 90 * math.sin(self.time * 2.5))
        draw_text(surface, "Up/Down + Enter  or  mouse", (w // 2, h - 22), 22, (230, 230, 240), anchor="center", alpha=a)


CONTROLS = [
    ("Move", "A / D  or  Left / Right"),
    ("Jump (hold = higher)", "Space / W / Up"),
    ("Drop through platform", "S / Down + Jump"),
    ("Shoot", "Left mouse  or  J / F"),
    ("Aim", "Mouse (or facing direction)"),
    ("Switch weapon", "Q / E  or  mouse wheel"),
    ("Select weapon", "1 - 9, 0"),
    ("Pause", "Esc"),
    ("Mute sound", "M"),
]


class ControlsScreen:
    def __init__(self, background: MenuBackground, size=(C.SCREEN_WIDTH, C.SCREEN_HEIGHT)) -> None:
        self.background = background
        self.size = size
        self.menu = MenuList(["Back"], (size[0] // 2, size[1] - 45), size=44)
        self.time = 0.0

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            return "menu"
        return "menu" if self.menu.handle_event(event) is not None else None

    def update(self, dt: float) -> None:
        self.time += dt
        self.background.update(dt)
        self.menu.update(dt)

    def draw(self, surface: pygame.Surface) -> None:
        w, h = self.size
        self.background.draw(surface)
        panel = pygame.Rect(0, 0, 720, 430)
        panel.midtop = (w // 2, 20)
        draw_panel(surface, panel)
        draw_text(surface, "CONTROLS", (w // 2, 56), 60, C.ACCENT, anchor="center", bold=True)
        y = 98
        for i, (action, keys) in enumerate(CONTROLS):
            if i % 2 == 0:
                row = pygame.Surface((660, 30), pygame.SRCALPHA)
                row.fill((255, 255, 255, 14))
                surface.blit(row, (w // 2 - 330, y - 4))
            draw_text(surface, action, (w // 2 - 310, y), 28, C.TEXT)
            draw_text(surface, keys, (w // 2 + 20, y), 28, C.ACCENT)
            y += 34
        draw_text(surface, "Collect weapons, stomp or shoot enemies and reach the flag!",
                  (w // 2, y + 10), 24, C.DIM, anchor="center")
        self.menu.draw(surface)


class SettingsScreen:
    """Master volume (Left/Right), sound effects, music and blood toggles."""

    def __init__(self, background: MenuBackground, settings: Settings,
                 size=(C.SCREEN_WIDTH, C.SCREEN_HEIGHT)) -> None:
        self.background = background
        self.settings = settings
        self.size = size
        self.menu = MenuList(self.labels(), (size[0] // 2, size[1] // 2 + 30), spacing=56, size=40)
        self.time = 0.0

    def labels(self):
        s = self.settings
        on = lambda v: "On" if v else "Off"  # noqa: E731
        return [f"Master Volume: < {int(round(s.master_volume * 100))}% >", f"Sound Effects: {on(s.sfx)}",
                f"Music: {on(s.music)}", f"Blood: {on(s.blood)}", "Back"]

    def refresh(self) -> None:
        self.menu.items = self.labels()

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        s = self.settings
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                return "menu"
            if event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_a, pygame.K_d) and self.menu.selected == 0:
                s.change_volume(Settings.VOLUME_STEP if event.key in (pygame.K_RIGHT, pygame.K_d) else -Settings.VOLUME_STEP)
                MenuList._sound("hover")
                self.refresh()
                return None
        chosen = self.menu.handle_event(event)
        if chosen is None:
            return None
        if chosen == 0:
            s.master_volume = 0.0 if s.master_volume >= 1.0 else min(1.0, round(s.master_volume + 0.2, 2))
        elif chosen == 1:
            s.sfx = not s.sfx
        elif chosen == 2:
            s.music = not s.music
        elif chosen == 3:
            s.blood = not s.blood
        else:
            return "menu"
        self.refresh()
        return None

    def update(self, dt: float) -> None:
        self.time += dt
        self.background.update(dt)
        self.menu.update(dt)

    def draw(self, surface: pygame.Surface) -> None:
        w, h = self.size
        self.background.draw(surface)
        panel = pygame.Rect(0, 0, 560, 420)
        panel.center = (w // 2, h // 2)
        draw_panel(surface, panel)
        draw_text(surface, "SETTINGS", (w // 2, panel.top + 46), 60, C.ACCENT, anchor="center", bold=True)
        self.menu.draw(surface)
        draw_text(surface, "Left/Right: volume   Enter: toggle   M: mute anywhere", (w // 2, panel.bottom - 22),
                  22, C.DIM, anchor="center")
