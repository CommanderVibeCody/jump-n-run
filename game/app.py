"""Application shell: owns the window, switches between scenes with smooth
fade transitions and runs the main loop."""
from __future__ import annotations

from typing import Optional, Sequence

import pygame

from . import constants as C
from .game import GameScene
from .level import LevelDef
from .audio import Audio
from .menu import ControlsScreen, MainMenu, MenuBackground, SettingsScreen, Title
from .settings import Settings
from .ui import MenuList

FADE_TIME = 0.35  # seconds for each half of a transition (out, then in)
SCENES = ("menu", "controls", "settings", "game")


class App:
    def __init__(self, seed: Optional[int] = None, level_defs: Optional[Sequence[LevelDef]] = None,
                 settings: Optional[Settings] = None, audio: Optional[Audio] = None) -> None:
        self.size = (C.SCREEN_WIDTH, C.SCREEN_HEIGHT)
        self.seed = seed
        self.level_defs = level_defs
        self.settings = settings or Settings()
        self.audio = audio if audio is not None else Audio(self.settings)
        MenuList.sound_hook = self.audio.play
        self.background = MenuBackground(self.size, seed)
        self.menu = MainMenu(self.background, Title(), self.size)
        self.controls = ControlsScreen(self.background, self.size)
        self.settings_screen = SettingsScreen(self.background, self.settings, self.size)
        self.game: Optional[GameScene] = None
        self.scene_name = "menu"
        self.scene = self.menu
        self.running = True
        self.fade = 1.0     # start black and fade in
        self.fade_dir = -1  # +1 fading out, -1 fading in, 0 idle
        self.pending: Optional[str] = None

    @property
    def transitioning(self) -> bool:
        return self.fade_dir == 1

    def go(self, name: str) -> None:
        """Start a fade-out; the scene switches when the screen is black."""
        if name not in SCENES or self.transitioning:
            return
        self.pending = name
        self.fade_dir = 1

    def _switch(self, name: str) -> None:
        if name == "game":
            self.game = GameScene(self.level_defs, self.seed, self.size, self.settings, self.audio)
            self.scene = self.game
        elif name == "menu":
            self.game = None
            self.menu.menu.selected = 0
            self.scene = self.menu
            pygame.mouse.set_visible(True)
        elif name == "controls":
            self.scene = self.controls
        elif name == "settings":
            self.settings_screen.menu.selected = 0
            self.settings_screen.refresh()
            self.scene = self.settings_screen
        self.scene_name = name

    def perform(self, action: Optional[str]) -> None:
        if action is None:
            return
        if action == "quit":
            self.running = False
        elif action == "play":
            self.go("game")
        else:
            self.go(action)

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_m:
            self.settings.toggle_mute()
            self.audio.apply_settings()
            return
        if self.transitioning:
            return
        self.perform(self.scene.handle_event(event))

    def update(self, dt: float) -> None:
        if self.fade_dir == 1:
            self.fade = min(1.0, self.fade + dt / FADE_TIME)
            if self.fade >= 1.0:
                if self.pending is not None:
                    self._switch(self.pending)
                    self.pending = None
                self.fade_dir = -1
        elif self.fade_dir == -1:
            self.fade = max(0.0, self.fade - dt / FADE_TIME)
            if self.fade <= 0.0:
                self.fade_dir = 0
        self.scene.update(dt)
        self.audio.update(dt)

    def draw(self, screen: pygame.Surface) -> None:
        self.scene.draw(screen)
        if self.fade > 0.0:
            a = self.fade * self.fade * (3 - 2 * self.fade)  # smoothstep
            overlay = pygame.Surface(screen.get_size())
            overlay.set_alpha(int(255 * a))
            screen.blit(overlay, (0, 0))


def run() -> None:
    try:
        pygame.mixer.pre_init(22050, -16, 2, 512)
    except Exception:
        pass
    pygame.init()
    pygame.display.set_caption("Jump 'n' Run")
    screen = pygame.display.set_mode((C.SCREEN_WIDTH, C.SCREEN_HEIGHT))
    clock = pygame.time.Clock()
    app = App()
    while app.running:
        dt = clock.tick(120) / 1000.0
        for event in pygame.event.get():
            app.handle_event(event)
            if not app.running:
                break
        app.update(dt)
        app.draw(screen)
        pygame.display.flip()
    pygame.quit()
