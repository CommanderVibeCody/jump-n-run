"""Small UI helpers: cached fonts, text with shadow, panels and an animated
menu list used by the main menu, the controls screen and the pause menu."""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import pygame

from .constants import ACCENT, DIM, TEXT

_FONTS: Dict[Tuple[int, bool], pygame.font.Font] = {}


def font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in _FONTS:
        if not pygame.font.get_init():
            pygame.font.init()
        f = pygame.font.Font(None, size)
        f.set_bold(bold)
        _FONTS[key] = f
    return _FONTS[key]


def draw_text(surface: pygame.Surface, text: str, pos, size: int = 28, color=TEXT,
              anchor: str = "topleft", shadow: bool = True, bold: bool = False, alpha: int = 255) -> pygame.Rect:
    f = font(size, bold)
    img = f.render(text, True, color)
    rect = img.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
    if shadow:
        sh = f.render(text, True, (0, 0, 0))
        if alpha < 255:
            sh.set_alpha(alpha // 2)
        else:
            sh.set_alpha(140)
        surface.blit(sh, rect.move(2, 2))
    if alpha < 255:
        img.set_alpha(alpha)
    surface.blit(img, rect)
    return rect


def draw_panel(surface: pygame.Surface, rect: pygame.Rect, alpha: int = 190,
               border=(255, 255, 255, 40), radius: int = 14) -> None:
    panel = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(panel, (12, 14, 28, alpha), panel.get_rect(), border_radius=radius)
    pygame.draw.rect(panel, border, panel.get_rect(), width=2, border_radius=radius)
    surface.blit(panel, rect.topleft)


def dim_screen(surface: pygame.Surface, alpha: int = 140) -> None:
    shade = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    shade.fill((0, 0, 10, alpha))
    surface.blit(shade, (0, 0))


class MenuList:
    """A vertical list of selectable items.

    Keyboard: Up/Down (or W/S) to move, Enter/Space to choose.
    Mouse: hover to select, left click to choose.
    ``handle_event`` returns the index of the chosen item or None.
    """

    def __init__(self, items: Sequence[str], center: Tuple[int, int], spacing: int = 58, size: int = 46) -> None:
        self.items: List[str] = list(items)
        self.center = center
        self.spacing = spacing
        self.size = size
        self.selected = 0
        self.highlight = [0.0] * len(self.items)  # animated 0..1 per item
        self.time = 0.0

    def item_rect(self, i: int) -> pygame.Rect:
        cx, cy = self.center
        y = cy + (i - (len(self.items) - 1) / 2) * self.spacing
        w = max(220, font(self.size).size(self.items[i])[0] + 80)
        return pygame.Rect(0, 0, w, self.spacing - 10).move(cx - w // 2, int(y) - (self.spacing - 10) // 2)

    def move(self, delta: int) -> None:
        self.selected = (self.selected + delta) % len(self.items)

    def handle_event(self, event: pygame.event.Event) -> Optional[int]:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_w):
                self.move(-1)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.move(1)
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                return self.selected
        elif event.type == pygame.MOUSEMOTION:
            for i in range(len(self.items)):
                if self.item_rect(i).collidepoint(event.pos):
                    self.selected = i
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i in range(len(self.items)):
                if self.item_rect(i).collidepoint(event.pos):
                    self.selected = i
                    return i
        return None

    def update(self, dt: float) -> None:
        self.time += dt
        for i in range(len(self.items)):
            target = 1.0 if i == self.selected else 0.0
            self.highlight[i] += (target - self.highlight[i]) * min(1.0, dt * 14)

    def draw(self, surface: pygame.Surface, alpha: int = 255) -> None:
        for i, label in enumerate(self.items):
            h = self.highlight[i]
            rect = self.item_rect(i)
            if h > 0.02:
                glow = pygame.Surface(rect.inflate(int(30 * h), 6).size, pygame.SRCALPHA)
                pulse = 0.75 + 0.25 * math.sin(self.time * 5)
                pygame.draw.rect(glow, (255, 196, 64, int(55 * h * pulse * alpha / 255)), glow.get_rect(),
                                 border_radius=16)
                pygame.draw.rect(glow, (255, 210, 120, int(170 * h * alpha / 255)), glow.get_rect(), width=2,
                                 border_radius=16)
                surface.blit(glow, glow.get_rect(center=rect.center))
            size = int(self.size * (1.0 + 0.18 * h))
            color = tuple(int(DIM[k] + (ACCENT[k] - DIM[k]) * h) for k in range(3))
            if h < 0.5:
                color = tuple(int(TEXT[k] * (1 - h) + ACCENT[k] * h) for k in range(3))
            draw_text(surface, label, rect.center, size, color, anchor="center", bold=h > 0.5, alpha=alpha)
