"""The in-game scene: turns keyboard/mouse events into ``InputState``,
runs the world with a fixed timestep and draws world, HUD and overlays
(pause menu, level banners, game over and victory screens)."""
from __future__ import annotations

import math
from typing import Optional, Sequence, Set

import pygame

from . import constants as C
from .level import LevelDef
from .player import InputState
from .render import WorldRenderer, draw_crosshair, draw_hud
from .settings import Settings
from .ui import MenuList, dim_screen, draw_panel, draw_text
from .world import World

LEFT_KEYS = (pygame.K_a, pygame.K_LEFT)
RIGHT_KEYS = (pygame.K_d, pygame.K_RIGHT)
DOWN_KEYS = (pygame.K_s, pygame.K_DOWN)
UP_KEYS = (pygame.K_w, pygame.K_UP)
MINIMAP_KEYS = (pygame.K_TAB, pygame.K_n)
JUMP_KEYS = (pygame.K_SPACE, pygame.K_w, pygame.K_UP)
SHOOT_KEYS = (pygame.K_j, pygame.K_f)
SLOT_KEYS = (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8,
             pygame.K_9, pygame.K_0)
MOUSE_AIM_TIMEOUT = 3.0


class GameScene:
    def __init__(self, level_defs: Optional[Sequence[LevelDef]] = None, seed: Optional[int] = None,
                 size=(C.SCREEN_WIDTH, C.SCREEN_HEIGHT), settings: Optional[Settings] = None,
                 audio=None) -> None:
        self.size = size
        self.level_defs = level_defs
        self.seed = seed
        self.settings = settings or Settings()
        self.audio = audio
        self.world = World(level_defs, seed=seed, blood=self.settings.blood)
        self.renderer = WorldRenderer(size)
        self.accumulator = 0.0
        self.time = 0.0
        # input state collected from events
        self.held: Set[int] = set()
        self.mouse_down = False
        self.mouse_pos = (size[0] // 2, size[1] // 2)
        self.mouse_idle = MOUSE_AIM_TIMEOUT  # seconds since the mouse last moved
        self.jump_latch = False
        self.switch_latch = 0
        self.interact_latch = False
        self.slot_latch: Optional[int] = None
        # overlays
        self.paused = False
        self.pause_fade = 0.0
        self.pause_menu = MenuList(["Resume", "Restart Level", "Main Menu"], (size[0] // 2, size[1] // 2 + 40))
        self.end_menu = MenuList(["Play Again", "Main Menu"], (size[0] // 2, size[1] // 2 + 90))
        self.end_fade = 0.0
        self.flash = 1.0  # black fade used for restarts / new levels
        self.banner_time = 0.0
        self._last_level = self.world.level_index

    # ------------------------------------------------------------ helpers
    @property
    def mouse_aim(self) -> bool:
        return self.mouse_idle < MOUSE_AIM_TIMEOUT or self.mouse_down

    @property
    def game_ended(self) -> bool:
        return self.world.state in ("game_over", "victory")

    def restart(self, full: bool = False) -> None:
        if full:
            self.world = World(self.level_defs, seed=self.seed, blood=self.settings.blood)
        else:
            lives, score = self.world.lives, self.world.score
            self.world.restart_level()
            self.world.lives, self.world.score = lives, score
        self.flash = 1.0
        self.banner_time = 0.0
        self.paused = False
        self.end_fade = 0.0
        self.accumulator = 0.0

    def build_input(self) -> InputState:
        held = self.held
        aim = None
        if self.mouse_aim:
            aim = self.world.camera.to_world(*self.mouse_pos)
        return InputState(
            left=any(k in held for k in LEFT_KEYS),
            right=any(k in held for k in RIGHT_KEYS),
            down=any(k in held for k in DOWN_KEYS),
            up=any(k in held for k in UP_KEYS),
            interact=self.interact_latch,
            jump_pressed=self.jump_latch,
            jump_held=any(k in held for k in JUMP_KEYS),
            shoot=self.mouse_down or any(k in held for k in SHOOT_KEYS),
            aim=aim,
            switch=self.switch_latch,
            select_slot=self.slot_latch,
        )

    # -------------------------------------------------------------- events
    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        if event.type in (pygame.WINDOWFOCUSLOST,):
            self.held.clear()
            self.mouse_down = False
            return None
        if self.game_ended:
            chosen = self.end_menu.handle_event(event)
            if chosen == 0:
                self.restart(full=True)
            elif chosen == 1:
                return "menu"
            return None
        if self.paused:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.paused = False
                return None
            chosen = self.pause_menu.handle_event(event)
            if chosen == 0:
                self.paused = False
            elif chosen == 1:
                self.restart()
            elif chosen == 2:
                return "menu"
            return None

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.paused = True
                self.pause_menu.selected = 0
                self.held.clear()
                self.mouse_down = False
                return None
            self.held.add(event.key)
            if event.key in JUMP_KEYS:
                self.jump_latch = True
            elif event.key == pygame.K_q:
                self.switch_latch = 1
            elif event.key == pygame.K_e:
                self.interact_latch = True
            elif event.key in MINIMAP_KEYS:
                self.settings.toggle_minimap()
            elif event.key in SLOT_KEYS:
                self.slot_latch = SLOT_KEYS.index(event.key)
        elif event.type == pygame.KEYUP:
            self.held.discard(event.key)
        elif event.type == pygame.MOUSEMOTION:
            self.mouse_pos = event.pos
            self.mouse_idle = 0.0
        elif event.type == pygame.MOUSEBUTTONDOWN:
            self.mouse_pos = event.pos
            if event.button == 1:
                self.mouse_down = True
                self.mouse_idle = 0.0
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.mouse_down = False
        elif event.type == pygame.MOUSEWHEEL:
            self.switch_latch = -1 if event.y > 0 else 1
        return None

    # -------------------------------------------------------------- update
    def update(self, dt: float) -> None:
        dt = min(dt, C.MAX_FRAME_TIME)
        self.time += dt
        self.flash = max(0.0, self.flash - dt * 2.5)
        self.pause_fade += ((1.0 if self.paused else 0.0) - self.pause_fade) * min(1.0, dt * 12)
        self.pause_menu.update(dt)
        self.end_menu.update(dt)
        if self.game_ended:
            self.end_fade = min(1.0, self.end_fade + dt * 1.5)
        self.world.blood = self.settings.blood
        self.world.muted = self.settings.muted
        self._play_sounds()
        if self.paused:
            return
        self.mouse_idle += dt
        self.banner_time += dt
        self.accumulator += dt
        while self.accumulator >= C.FIXED_DT:
            self.world.step(self.build_input())
            # edge-triggered inputs only count for one step
            self.jump_latch = False
            self.switch_latch = 0
            self.interact_latch = False
            self.slot_latch = None
            self.accumulator -= C.FIXED_DT
            self._play_sounds()
            if self.world.level_index != self._last_level:
                self._last_level = self.world.level_index
                self.banner_time = 0.0
                self.flash = 1.0

    def _play_sounds(self) -> None:
        names = self.world.drain_sounds()
        if self.audio is not None:
            for name in names:
                self.audio.play(name)

    # ---------------------------------------------------------------- draw
    def draw(self, surface: pygame.Surface) -> None:
        w, h = self.size
        world = self.world
        self.renderer.draw(surface, world)
        draw_hud(surface, world)
        if self.settings.minimap:
            self.renderer.draw_minimap(surface, world)

        if self.banner_time < 2.5 and world.state == "playing":
            a = int(255 * min(1.0, (2.5 - self.banner_time) * 2, self.banner_time * 3))
            draw_text(surface, f"LEVEL {world.level_index + 1}", (w // 2, h * 0.28), 64, C.ACCENT,
                      anchor="center", bold=True, alpha=a)
            draw_text(surface, world.level.name.split("  ")[-1], (w // 2, h * 0.28 + 50), 34, C.TEXT,
                      anchor="center", alpha=a)
        if world.state == "level_complete":
            draw_text(surface, "LEVEL COMPLETE!", (w // 2, h * 0.32), 72, C.ACCENT, anchor="center", bold=True)
        elif world.state == "dead" and world.lives > 0:
            draw_text(surface, "OUCH!", (w // 2, h * 0.32), 72, C.RED, anchor="center", bold=True)

        if self.mouse_aim and not self.paused and not self.game_ended:
            draw_crosshair(surface, self.mouse_pos, self.time)
        pygame.mouse.set_visible(not (self.mouse_aim and not self.paused and not self.game_ended))

        if self.game_ended:
            self._draw_end(surface)
        if self.pause_fade > 0.01:
            self._draw_pause(surface)
        if self.flash > 0:
            veil = pygame.Surface((w, h))
            veil.set_alpha(int(255 * self.flash ** 2))
            surface.blit(veil, (0, 0))

    def _draw_pause(self, surface: pygame.Surface) -> None:
        w, h = self.size
        a = self.pause_fade
        dim_screen(surface, int(150 * a))
        panel = pygame.Rect(0, 0, 360, 300)
        panel.center = (w // 2, int(h // 2 + 10 + (1 - a) * 40))
        draw_panel(surface, panel, alpha=int(200 * a))
        draw_text(surface, "PAUSED", (w // 2, panel.top + 46), 64, C.ACCENT, anchor="center", bold=True,
                  alpha=int(255 * a))
        self.pause_menu.center = (w // 2, panel.top + 170)
        self.pause_menu.draw(surface, alpha=int(255 * a))

    def _draw_end(self, surface: pygame.Surface) -> None:
        w, h = self.size
        a = self.end_fade
        dim_screen(surface, int(170 * a))
        won = self.world.state == "victory"
        title = "YOU WIN!" if won else "GAME OVER"
        color = C.ACCENT if won else C.RED
        bounce = math.sin(self.time * 3) * 6 if won else 0
        draw_text(surface, title, (w // 2, h * 0.26 + bounce), 96, color, anchor="center", bold=True,
                  alpha=int(255 * a))
        draw_text(surface, f"Score {self.world.score}    Kills {self.world.kills}", (w // 2, h * 0.26 + 70),
                  36, C.TEXT, anchor="center", alpha=int(255 * a))
        self.end_menu.draw(surface, alpha=int(255 * a))
