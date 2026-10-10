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

![Gameplay](docs/gameplay.png)

![Night level](docs/night.png)

## Features

* **Tight platformer movement**: acceleration and friction, gravity with a
  stronger fall, variable jump height (release early for a short hop),
  coyote time, jump buffering, squash & stretch.
* **Own physics**: fixed timestep (1/120 s), exact integration for constant
  acceleration, tile collisions resolved per axis, no tunnelling.
* **Tile-based levels** written as ASCII maps ([`game/levels.py`](game/levels.py)):
  solid blocks, one-way platforms you can jump through (and drop down
  through), spikes, bottomless pits, checkpoints and a goal flag.
  Two levels: *Green Hills* (day) and *Night Factory* (night).
* **Smooth scrolling camera** with look-ahead, clamped to the level.
* **Four weapons** with ammo, switching and a HUD:

  | Slot | Weapon | Ammo | Notes |
  |------|--------|------|-------|
  | 1 | Pistol | infinite | accurate, medium fire rate |
  | 2 | Shotgun | 12 per pickup (max 24) | 6 pellets, short range, big recoil |
  | 3 | Machine Gun | 90 per pickup (max 180) | very fast, slight spread |
  | 4 | Rocket Launcher | 5 per pickup (max 10) | accelerating rocket, area damage, rocket jumps |

* **Enemies**: *walkers* patrol and turn at walls and ledges, *shooters*
  fire at you when they have line of sight, *drones* fly after you.
  Shoot them or jump on their heads.
* **Health, lives, checkpoints, respawn**, health packs and ammo crates,
  score, kills and level timer.
* **Juice**: parallax background (3 layers + sky), muzzle flashes, impact
  sparks, explosions, dust, floating texts, screen shake.
* **Menus**: animated start menu (Play, Controls, Quit) with a little hero
  running and shooting in the background, pause menu on `Esc`
  (Resume, Restart Level, Main Menu), game over / victory screens and fade
  transitions between all screens.

## Controls

| Action | Keys |
|--------|------|
| Move | `A` / `D` or `←` / `→` |
| Jump (hold for a higher jump) | `Space`, `W` or `↑` |
| Drop through a one-way platform | `S` / `↓` + Jump |
| Shoot | Left mouse button, `J` or `F` |
| Aim | Mouse (without mouse movement you shoot in the facing direction) |
| Switch weapon | `Q` / `E` or mouse wheel |
| Select weapon | `1` – `4` |
| Pause menu | `Esc` |
| Menus | `↑` / `↓` + `Enter`, or the mouse |

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

This installs `pygame` and `pytest` into the virtual environment only.

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
| `w` | walker enemy | `s` | shooter enemy |
| `d` | drone enemy | `+` | health pack |
| `S` | shotgun | `M` | machine gun |
| `R` | rocket launcher | `a` | ammo crate |

Add a new `LevelDef` to `LEVELS` and it is played after the existing ones.

## Project structure

```
jump-n-run/
├── main.py              # entry point: python main.py
├── requirements.txt
├── game/
│   ├── app.py           # window, main loop, scene switching with fades
│   ├── menu.py          # animated start menu, controls screen
│   ├── game.py          # in-game scene: input, fixed timestep, pause/game over overlays
│   ├── world.py         # game rules: player, enemies, projectiles, pickups, checkpoints, goal
│   ├── player.py        # player movement (coyote time, jump buffer, variable jump) and inventory
│   ├── physics.py       # hand-written integration and tile collision
│   ├── weapons.py       # weapon specs, projectiles, pickups
│   ├── enemies.py       # walker, shooter and drone AI
│   ├── level.py         # ASCII level parser and tile queries
│   ├── levels.py        # the level maps and colour themes
│   ├── camera.py        # smooth follow camera
│   ├── effects.py       # particles, floating texts, screen shake
│   ├── render.py        # all drawing: parallax, tiles, characters, HUD
│   ├── ui.py            # fonts, panels, animated menu list
│   └── constants.py     # tuning values
├── tests/               # pytest suite (physics, weapons, enemies, world, menus, headless smoke test)
├── tools/
│   └── make_screenshots.py  # renders the screenshots in docs/ headless
└── docs/                # screenshots
```
