"""User settings shared by the menus, the game and the audio system."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Settings:
    master_volume: float = 0.8   # 0.0 .. 1.0
    sfx: bool = True
    music: bool = True
    blood: bool = True
    muted: bool = False          # toggled with the M key

    VOLUME_STEP = 0.1

    def change_volume(self, delta: float) -> None:
        self.master_volume = round(min(1.0, max(0.0, self.master_volume + delta)), 2)

    def toggle_mute(self) -> None:
        self.muted = not self.muted

    @property
    def sfx_volume(self) -> float:
        return 0.0 if (self.muted or not self.sfx) else self.master_volume

    @property
    def music_volume(self) -> float:
        return 0.0 if (self.muted or not self.music) else self.master_volume
