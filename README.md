# Jump 'n' Run – a 2D platformer in Pygame

A complete side-scrolling run-and-gun platformer written in Python with
**pygame**. Run, jump across platforms, pick up weapons, shoot or stomp
enemies and reach the flag at the end of each level.

All physics are **hand-written** – no physics library is used. Movement runs
on a fixed timestep with exact constant-acceleration integration and
axis-separated collision against the tile map (see
[`game/physics.py`](game/physics.py)). All graphics are drawn with pygame
primitives, so there are no image assets.

![Main menu](docs/menu.png)

![Gameplay: soldiers, blood and corpses](docs/gameplay.png)

![Barrel chain explosion with shockwave](docs/explosion.png)

![Night level](docs/night.png)

## Features

* **Tight platformer movement**: acceleration and friction, gravity with a
  stronger fall, variable jump height (release early for a short hop),
  coyote time, jump buffering, squash & stretch.
* **Own physics**: fixed timestep (1/120 s), exact integration for constant
  acceleration, tile collisions resolved per axis, no tunnelling. Particles,
  casings, debris, gibs, grenades and corpses all use the same tile world.
* **Three tile-based levels** written as ASCII maps ([`game/levels.py`](game/levels.py)):
  *Green Hills* (day), *Night Factory* (night) and *Sunset Warzone* (dense
  fights, bunkers and barrel fields). Solid blocks, one-way platforms you can
  jump through (and drop through), spikes, pits, checkpoints and a goal flag.
* **Ten weapons** with ammo, switching and a HUD (see the table below).
* **Human soldiers** drawn as animated figures (head, helmet, torso, arms,
  legs) with a walk cycle and an arm that aims the gun at you, plus blob
  walkers and flying drones.
* **Explosive barrels** that chain-react, big explosions with a shockwave
  ring, fire, smoke and bouncing debris, strong screen shake, hit-stop on
  kills, and bullet casings ejecting from every gun.
* **Blood** (can be switched off): drops spray in the hit direction, fall
  with gravity and leave splatter decals on floors, walls and ceilings;
  explosion kills burst into gibs; other kills leave ragdoll-style corpses
  that fly back, tumble and come to rest.
* **Procedural sound**: every sound effect and the background music loop are
  synthesised with numpy at startup – no audio files.
* **Health, lives, checkpoints, respawn**, health packs and ammo crates,
  score, kills and level timer.
* **Menus**: animated start menu (Play, Controls, Settings, Quit), settings
  screen, pause menu on `Esc` (Resume, Restart Level, Main Menu), game over /
  victory screens and fade transitions.

## Weapons

| Key | Weapon | Ammo per pickup (max) | Map char | Notes |
|-----|--------|-----------------------|----------|-------|
| 1 | Pistol | infinite | – | accurate starting weapon |
| 2 | Dual Pistols | 80 (160) | `D` | alternates two guns, fast |
| 3 | SMG | 120 (240) | `U` | very fast, wide spread |
| 4 | Shotgun | 12 (24) | `S` | 6 pellets, short range, big knockback |
| 5 | Machine Gun | 90 (180) | `M` | fast and fairly accurate |
| 6 | Sniper Rifle | 10 (20) | `N` | 120 damage, pierces up to 4 enemies |
| 7 | Flamethrower | 150 (300) | `F` | flames pass through enemies and set them on fire |
| 8 | Grenade Launcher | 6 (12) | `L` | bouncing grenades, 1.6 s fuse or explode on contact |
| 9 | Rocket Launcher | 5 (10) | `R` | accelerating rocket, area damage, rocket jumps |
| 0 | Railgun | 5 (10) | `Z` | instant beam that pierces every enemy up to a wall |

When a weapon runs dry you automatically switch back to the pistol. Your own
explosives push you around but never hurt you; enemy grenades and barrels do.

## Enemies

| Map char | Enemy | Behaviour |
|----------|-------|-----------|
| `r` | Rifleman | patrols, stops when he sees you, fires 3-round bursts |
| `k` | Shotgunner | short range, 5-pellet blasts |
| `g` | Grenadier | lobs bouncing grenades in a ballistic arc |
| `h` | Heavy | slow, 240 HP, spins up a minigun and sprays bullets |
| `s` | Guard | stationary, single aimed shots |
| `w` | Walker | blob that patrols and hurts on contact |
| `d` | Drone | flies after you when it has line of sight |
| `b` | Explosive barrel | explodes when shot, chains into nearby barrels |

Jump on an enemy's head to stomp it.

## Controls

| Action | Keys |
|--------|------|
| Move | `A` / `D` or `←` / `→` |
| Jump (hold for a higher jump) | `Space`, `W` or `↑` |
| Drop through a one-way platform | `S` / `↓` + Jump |
| Shoot | Left mouse button, `J` or `F` |
| Aim | Mouse (without mouse movement you shoot in the facing direction) |
| Switch weapon | `Q` / `E` or mouse wheel |
| Select weapon | `1` – `9`, `0` |
| Mute / unmute | `M` (works everywhere) |
| Pause menu | `Esc` |
| Menus | `↑` / `↓` + `Enter`, or the mouse |

## Settings

Open **Settings** from the main menu:

| Setting | Default | How |
|---------|---------|-----|
| Master volume | 80 % | `←` / `→` (or `Enter` to step up) |
| Sound effects | On | `Enter` toggles |
| Music | On | `Enter` toggles |
| Blood | On | `Enter` toggles; off replaces blood, gibs and splatter with sparks |

Settings apply immediately and last until you quit the game.

## Sound

All audio is generated in [`game/audio.py`](game/audio.py) with numpy when
the game starts (about 0.1 s): filtered noise bursts and pitch sweeps for
each of the ten weapons, the empty click and reload, jump, landing,
footsteps, pickups, enemy hits and deaths, player hurt and death,
explosions, grenade bounces, checkpoints, the level-complete fanfare and menu
hover/select blips. The music is a seamless 4-bar loop (bass, arpeggio, kick,
snare, hi-hats) at 124 BPM.

The sound buffers are built to match whatever format the mixer actually
opened (sample rate, 8/16-bit integer or 32-bit float, mono or stereo), and
each buffer is checked to be non-silent. If there is no audio device, or
numpy or the mixer is unavailable, the game still runs and prints a warning
starting with `[jump-n-run audio]` to the console that explains why.

### No sound? Run the audio test

```bash
python main.py --audio-test
```

It prints the pygame/SDL/numpy versions and the mixer format, then plays a
440 Hz test beep, three effects and a few seconds of music. If it reports
`enabled=False`, the printed reason tells you what failed (most often a
missing `numpy` – run `pip install -r requirements.txt` inside the activated
virtual environment). If it reports `enabled=True` but you hear nothing,
check the system volume and output device, and make sure sound is not muted
in the game (`M`, or Settings).

## Setup and running

### Requirements

* **Python 3.9 – 3.13** (64-bit recommended). The game depends on
  [pygame 2.6](https://pypi.org/project/pygame/), which only ships prebuilt
  wheels up to Python 3.13. On newer Python versions pip would try to build
  pygame from source, which usually fails, so stick to 3.9 – 3.13.
* Check your version with `python --version` (on macOS/Linux it may be
  `python3 --version`).

### 1. Create a virtual environment

Run this in the project folder (the one containing `main.py`):

```bash
python -m venv .venv
```

On macOS/Linux use `python3` if `python` is not available. The `.venv` folder
is listed in `.gitignore` and is never committed.

### 2. Activate it

| System | Command |
|--------|---------|
| Windows – PowerShell | `.venv\Scripts\Activate.ps1` |
| Windows – cmd | `.venv\Scripts\activate.bat` |
| macOS / Linux (bash, zsh) | `source .venv/bin/activate` |

When the environment is active, your prompt starts with `(.venv)`.

> **PowerShell note:** if activation fails with "running scripts is disabled
> on this system", allow local scripts for your user once and try again:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

### 3. Install the dependencies

```bash
pip install -r requirements.txt
```

This installs `pygame`, `numpy` (for the procedural sound) and `pytest` into the virtual environment only.

### 4. Play

```bash
python main.py
```

### 5. Run the tests

```bash
python -m pytest
```

The tests run headless (no window opens).

### 6. Deactivate the environment

```bash
deactivate
```

Next time, just activate the environment again (step 2) and run
`python main.py`; there is no need to reinstall.

## How the physics work

* The simulation advances in fixed steps of `1/120 s`
  (`FIXED_DT` in [`game/constants.py`](game/constants.py)). The frame loop
  accumulates real time and runs as many steps as needed, so the game feels
  the same at any frame rate.
* Each step applies a constant acceleration `a` (gravity, run acceleration
  or friction) and updates
  `v' = v + a·dt` and `x' = x + (v + v')/2 · dt`, which is exact for
  constant acceleration (the same as velocity Verlet in that case). A full
  jump therefore reaches exactly `JUMP_HEIGHT`.
* Collisions: the body moves along X, gets pushed out of solid tiles, then
  moves along Y and is pushed out again. Speeds are clamped so a body never
  moves more than one tile per step, which means only the tiles at the
  leading edge need checking. One-way platforms only block bodies whose
  feet were above the platform before the move.
* Projectiles sub-step their motion (quarter-tile steps) so even fast bullets
  cannot pass through walls.

## Make your own level

Levels are ASCII maps in [`game/levels.py`](game/levels.py):

| Char | Meaning | Char | Meaning |
|------|---------|------|---------|
| `#` | solid block | `=` | one-way platform |
| `^` | spikes | `P` | player start |
| `G` | goal flag | `C` | checkpoint |
| `+` | health pack | `a` | ammo crate |
| `b` | explosive barrel | | |

Enemy and weapon characters are listed in the tables above.

Add a new `LevelDef` to `LEVELS` and it is played after the existing ones.

## Project structure

```
jump-n-run/
├── main.py              # entry point: python main.py
├── requirements.txt
├── game/
│   ├── app.py           # window, main loop, scene switching with fades
│   ├── menu.py          # animated start menu, controls and settings screens
│   ├── game.py          # in-game scene: input, fixed timestep, pause/game over overlays
│   ├── world.py         # game rules: player, enemies, barrels, projectiles, explosions, blood, pickups
│   ├── audio.py         # procedural sound effects and music (numpy), silent fallback
│   ├── settings.py      # volume, sound, music and blood settings
│   ├── player.py        # player movement (coyote time, jump buffer, variable jump) and inventory
│   ├── physics.py       # hand-written integration and tile collision
│   ├── weapons.py       # weapon specs, projectiles, pickups
│   ├── enemies.py       # soldiers (rifleman, shotgunner, grenadier, heavy, guard), walker, drone, barrels, corpses
│   ├── level.py         # ASCII level parser and tile queries
│   ├── levels.py        # the level maps and colour themes
│   ├── camera.py        # smooth follow camera
│   ├── effects.py       # particles, blood and decals, shockwaves, beams, screen shake
│   ├── render.py        # all drawing: parallax, tiles, characters, HUD
│   ├── ui.py            # fonts, panels, animated menu list
│   └── constants.py     # tuning values
├── tests/               # pytest suite: physics, weapons, arsenal, enemies, action (barrels, blood),
│                        # world, audio and settings, menus, headless smoke test
├── tools/
│   └── make_screenshots.py  # renders the screenshots in docs/ headless
└── docs/                # screenshots
```
