"""The game world: one level with the player, enemies, projectiles and
pickups. ``World.step`` advances everything by one fixed timestep.

The world has no dependency on a display, so it can be simulated headless
(the tests do exactly that)."""
from __future__ import annotations

import math
import random
from typing import List, Optional, Sequence

from . import constants as C
from .camera import Camera
from .effects import Effects
from .enemies import Enemy, make_enemy
from .level import Level, LevelDef
from .player import InputState, Player
from .weapons import WEAPONS, Pickup, Projectile

PICKUP_KINDS = {"S": "shotgun", "M": "machinegun", "R": "rocket", "+": "health", "a": "ammo"}
HEALTH_PACK = 40


class Checkpoint:
    def __init__(self, tx: int, ty: int) -> None:
        self.tx, self.ty = tx, ty
        self.x = tx * C.TILE + 8
        self.y = (ty + 1) * C.TILE - 64
        self.w, self.h = 16, 64
        self.active = False

    def spawn_point(self):
        return self.tx, self.ty


class Goal:
    def __init__(self, tx: int, ty: int) -> None:
        self.x = tx * C.TILE
        self.y = (ty + 1) * C.TILE - 96
        self.w, self.h = C.TILE, 96


class World:
    """States: "playing", "dead" (respawn countdown), "level_complete",
    "game_over" and "victory"."""

    def __init__(self, level_defs: Optional[Sequence[LevelDef]] = None, seed: Optional[int] = None,
                 start_level: int = 0, lives: int = C.PLAYER_LIVES) -> None:
        if level_defs is None:
            from .levels import LEVELS
            level_defs = LEVELS
        self.level_defs = list(level_defs)
        self.rng = random.Random(seed)
        self.effects = Effects(self.rng)
        self.lives = lives
        self.score = 0
        self.kills = 0
        self.time = 0.0
        self.events: List[str] = []
        self.load_level(start_level)

    # --------------------------------------------------------------- setup
    def load_level(self, index: int, keep_player: Optional[Player] = None) -> None:
        self.level_index = index
        self.level = Level(self.level_defs[index])
        sp = self.level.player_spawn
        self.respawn_tile = (sp.tx, sp.ty)
        self.player = Player.at_tile(sp.tx, sp.ty)
        if keep_player is not None:
            self.player.weapons = keep_player.weapons
            self.player.current = keep_player.current
            self.player.health = keep_player.health
        self.enemies: List[Enemy] = [make_enemy(s.kind, s.tx, s.ty) for s in self.level.spawns_of("wsd")]
        self.pickups: List[Pickup] = [Pickup(PICKUP_KINDS[s.kind], s.tx, s.ty)
                                      for s in self.level.spawns_of("SMR+a")]
        self.checkpoints = [Checkpoint(s.tx, s.ty) for s in self.level.spawns_of("C")]
        goals = self.level.spawns_of("G")
        self.goal = Goal(goals[0].tx, goals[0].ty) if goals else None
        self.projectiles: List[Projectile] = []
        self.state = "playing"
        self.state_timer = 0.0
        self.level_time = 0.0
        self.camera = Camera(self.level.pixel_width, self.level.pixel_height)
        self.camera.snap(self.player.body.cx, self.player.body.cy, self.player.facing)

    def restart_level(self) -> None:
        """Restart the current level from scratch (pistol only)."""
        self.load_level(self.level_index)

    @property
    def is_last_level(self) -> bool:
        return self.level_index >= len(self.level_defs) - 1

    # ---------------------------------------------------------------- step
    def step(self, inp: Optional[InputState] = None) -> None:
        dt = C.FIXED_DT
        inp = inp or InputState()
        self.events.clear()
        self.time += dt
        self.effects.update(dt)
        p = self.player

        if self.state == "playing":
            self.level_time += dt
            self._update_player(inp, dt)
        elif self.state == "dead":
            self.state_timer -= dt
            if self.state_timer <= 0:
                if self.lives > 0:
                    self._respawn()
                else:
                    self.state = "game_over"
                    self.events.append("game_over")
        elif self.state == "level_complete":
            self.state_timer -= dt
            if self.state_timer <= 0:
                if self.is_last_level:
                    self.state = "victory"
                    self.events.append("victory")
                else:
                    self.load_level(self.level_index + 1, keep_player=p)
                    self.events.append("next_level")
                    return

        self._update_enemies(dt)
        self._update_projectiles(dt)
        if self.state == "playing":
            self._check_contacts()
        self.camera.follow(self.player.body.cx, self.player.body.cy, self.player.facing, dt)

    # ------------------------------------------------------------- player
    def _update_player(self, inp: InputState, dt: float) -> None:
        p = self.player
        if inp.switch:
            if p.cycle_weapon(inp.switch):
                self.events.append("switch")
        if inp.select_slot is not None:
            if p.select_slot(inp.select_slot):
                self.events.append("switch")

        p.update(inp, self.level, dt)
        b = p.body
        if p.just_jumped:
            self.effects.dust(b.cx, b.bottom, 5)
            self.events.append("jump")
        if p.just_landed and p.landed_speed > 300:
            self.effects.dust(b.cx, b.bottom, int(4 + p.landed_speed / 120))
            self.events.append("land")
        if b.on_ground and abs(b.vx) > 200 and self.rng.random() < 0.08:
            self.effects.dust(b.cx - p.facing * 8, b.bottom, 1)

        if inp.shoot:
            self._fire_player_weapon()

        if self.level.touches_spikes(b.x, b.y, b.w, b.h):
            if p.invulnerable <= 0:
                self.damage_player(C.SPIKE_DAMAGE, None)
            if p.alive:
                b.vy = -650.0
        if b.y > self.level.pixel_height + 64:
            self.kill_player()

    def _fire_player_weapon(self) -> None:
        p = self.player
        w = p.weapon
        if not w.can_fire():
            return
        mx, my = p.muzzle()
        shots = w.fire(mx, my, p.aim_angle, self.rng, "player")
        if not shots:
            return
        self.projectiles.extend(shots)
        spec = w.spec
        self.effects.muzzle_flash(mx, my, p.aim_angle, spec.color, big=spec.pellets > 1 or spec.explosion_radius > 0)
        self.effects.shake(spec.shake)
        p.recoil_anim = 1.0
        p.body.vx -= math.cos(p.aim_angle) * spec.recoil
        if not p.body.on_ground:
            p.body.vy -= math.sin(p.aim_angle) * spec.recoil * 0.5
        self.events.append("shoot")
        if not w.has_ammo:
            self.events.append("out_of_ammo")
            self.effects.text("OUT OF AMMO", p.body.cx, p.body.y - 20, C.RED, 1.0)
            p.current = "pistol"

    def damage_player(self, amount: float, source_x: Optional[float]) -> bool:
        """Hurt the player unless invulnerable. Returns True if damage was dealt."""
        p = self.player
        if not p.alive or p.invulnerable > 0 or self.state != "playing":
            return False
        p.health -= amount
        p.invulnerable = C.INVULNERABLE_TIME
        self.effects.shake(0.45)
        self.effects.burst(p.body.cx, p.body.cy, (255, 80, 80), count=10, speed=200, life=0.4)
        if source_x is not None:
            direction = 1 if p.body.cx >= source_x else -1
            p.body.vx = direction * 330
            p.body.vy = -380
        self.events.append("hurt")
        if p.health <= 0:
            self.kill_player()
        return True

    def kill_player(self) -> None:
        p = self.player
        if not p.alive:
            return
        p.alive = False
        p.health = 0
        self.lives -= 1
        self.state = "dead"
        self.state_timer = C.RESPAWN_DELAY
        b = p.body
        self.effects.burst(b.cx, b.cy, (90, 170, 255), count=40, speed=380, life=0.9, size=4, glow=True)
        self.effects.burst(b.cx, b.cy, (255, 255, 255), count=15, speed=220, life=0.5, size=3)
        self.effects.shake(0.8)
        self.events.append("death")

    def _respawn(self) -> None:
        old = self.player
        tx, ty = self.respawn_tile
        self.player = Player.at_tile(tx, ty)
        self.player.weapons = old.weapons
        self.player.current = old.current if old.weapons[old.current].has_ammo else "pistol"
        self.player.invulnerable = 1.5
        self.state = "playing"
        self.projectiles = [pr for pr in self.projectiles if pr.owner == "player"]
        self.camera.snap(self.player.body.cx, self.player.body.cy, self.player.facing)
        self.effects.burst(self.player.body.cx, self.player.body.cy, (120, 220, 255), count=25,
                           speed=250, life=0.6, glow=True)
        self.events.append("respawn")

    # ------------------------------------------------------------ enemies
    def _update_enemies(self, dt: float) -> None:
        for e in self.enemies:
            if e.alive:
                self.projectiles.extend(e.update(dt, self.level, self.player, self.rng))
        dead = [e for e in self.enemies if not e.alive]
        if dead:
            self.enemies = [e for e in self.enemies if e.alive]

    def damage_enemy(self, enemy: Enemy, amount: float, knock_x: float = 0.0, knock_y: float = 0.0) -> bool:
        killed = enemy.take_damage(amount, knock_x, knock_y)
        b = enemy.body
        if killed:
            self.kills += 1
            self.score += enemy.SCORE
            self.effects.burst(b.cx, b.cy, (255, 120, 60), count=26, speed=320, life=0.7, size=4, glow=True)
            self.effects.burst(b.cx, b.cy, (60, 60, 70), count=12, speed=200, life=1.0, size=5, gravity=900)
            self.effects.text(f"+{enemy.SCORE}", b.cx, b.y - 10, C.ACCENT, 0.9)
            self.effects.shake(0.25)
            self.events.append("enemy_killed")
        else:
            self.events.append("enemy_hit")
        return killed

    # -------------------------------------------------------- projectiles
    def _update_projectiles(self, dt: float) -> None:
        for pr in self.projectiles:
            if not pr.alive:
                continue
            pr.update(dt, self.level)
            if pr.kind == "rocket" and self.rng.random() < 0.7:
                self.effects.smoke(pr.x - pr.dir_x * 10, pr.y - pr.dir_y * 10)
            if not pr.alive:
                if pr.hit_wall:
                    if pr.explosive:
                        self.explode(pr)
                    else:
                        self.effects.impact(pr.x - pr.dir_x * 3, pr.y - pr.dir_y * 3, pr.color)
                continue
            if pr.owner == "player":
                for e in self.enemies:
                    if e.alive and e.body.contains_point(pr.x, pr.y, pr.radius):
                        pr.alive = False
                        if pr.explosive:
                            self.explode(pr)
                        else:
                            self.effects.impact(pr.x, pr.y, (255, 200, 120))
                            self.damage_enemy(e, pr.damage, pr.dir_x * pr.knockback, -60.0)
                        break
            elif self.state == "playing" and self.player.alive:
                if self.player.body.contains_point(pr.x, pr.y, pr.radius):
                    pr.alive = False
                    self.effects.impact(pr.x, pr.y, pr.color)
                    self.damage_player(pr.damage, pr.x - pr.dir_x * 10)
        self.projectiles = [pr for pr in self.projectiles if pr.alive]

    def explode(self, pr: Projectile) -> None:
        """Rocket explosion: area damage with linear falloff and knockback.

        The player is not damaged by their own rockets but gets pushed away
        (rocket jumps are allowed)."""
        x, y, r = pr.x - pr.dir_x * 4, pr.y - pr.dir_y * 4, pr.explosion_radius
        self.effects.explosion(x, y, r)
        self.events.append("explosion")
        for e in list(self.enemies):
            if not e.alive:
                continue
            dx, dy = e.body.cx - x, e.body.cy - y
            d = math.hypot(dx, dy)
            if d < r + e.body.w / 2:
                falloff = max(0.3, 1.0 - d / (r + e.body.w / 2))
                nx, ny = (dx / d, dy / d) if d > 1e-6 else (0.0, -1.0)
                self.damage_enemy(e, pr.damage * falloff, nx * pr.knockback * falloff,
                                  ny * pr.knockback * falloff - 150)
        p = self.player
        if p.alive:
            dx, dy = p.body.cx - x, p.body.cy - y
            d = math.hypot(dx, dy)
            if d < r * 1.1:
                push = (1.0 - d / (r * 1.1)) * 900
                nx, ny = (dx / d, dy / d) if d > 1e-6 else (0.0, -1.0)
                p.body.vx += nx * push
                p.body.vy += ny * push
                p.body.on_ground = False

    # ------------------------------------------------------------ contacts
    def _check_contacts(self) -> None:
        p = self.player
        if not p.alive:
            return
        b = p.body
        # enemies: stomp from above or take contact damage
        for e in self.enemies:
            if not e.alive or not b.overlaps(e.body):
                continue
            stomping = b.vy > 50 and b.bottom - e.body.top < 16 and e.kind != "drone"
            if stomping:
                self.damage_enemy(e, C.STOMP_DAMAGE, 0.0, 0.0)
                b.vy = -C.STOMP_BOUNCE
                p.jumping = False
                self.effects.dust(b.cx, b.bottom, 8)
                self.events.append("stomp")
            else:
                self.damage_player(e.CONTACT_DAMAGE, e.body.cx)
        # pickups
        for item in self.pickups:
            if item.alive and _box_overlap(b, item.x, item.y, item.W, item.H):
                self._collect(item)
        self.pickups = [i for i in self.pickups if i.alive]
        # checkpoints
        for cp in self.checkpoints:
            if not cp.active and _box_overlap(b, cp.x - 8, cp.y, cp.w + 16, cp.h):
                for other in self.checkpoints:
                    other.active = False
                cp.active = True
                self.respawn_tile = cp.spawn_point()
                self.effects.burst(cp.x + 8, cp.y + 8, C.GREEN, count=20, speed=200, life=0.6, glow=True)
                self.effects.text("CHECKPOINT", cp.x + 8, cp.y - 10, C.GREEN, 1.2)
                self.events.append("checkpoint")
        # goal
        if self.goal and _box_overlap(b, self.goal.x, self.goal.y, self.goal.w, self.goal.h):
            self.state = "level_complete"
            self.state_timer = C.LEVEL_END_DELAY
            bonus = 500 + max(0, int(300 - self.level_time) * 5)
            self.score += bonus
            self.effects.text(f"LEVEL CLEAR +{bonus}", self.goal.x + 16, self.goal.y - 10, C.ACCENT, 2.0)
            for i in range(5):
                self.effects.burst(self.goal.x + 16, self.goal.y + 10, [(255, 220, 90), (120, 220, 255),
                                   (255, 120, 200)][i % 3], count=20, speed=350, life=1.2, glow=True)
            self.events.append("level_complete")

    def _collect(self, item: Pickup) -> None:
        p = self.player
        x, y = item.cx, item.y - 8
        if item.is_weapon:
            result = p.give_weapon(item.kind)
            if result == "full":
                return
            name = WEAPONS[item.kind].name.upper()
            self.effects.text(name if result == "new" else f"{name} AMMO", x, y, WEAPONS[item.kind].color)
        elif item.kind == "health":
            if p.health >= p.max_health:
                return
            p.health = min(p.max_health, p.health + HEALTH_PACK)
            self.effects.text(f"+{HEALTH_PACK} HP", x, y, C.GREEN)
        elif item.kind == "ammo":
            gained = sum(w.add_ammo(max(1, w.spec.pickup_ammo // 2)) for w in p.weapons.values())
            if gained == 0:
                return
            self.effects.text("AMMO", x, y, C.ACCENT)
        item.alive = False
        self.score += 25
        self.effects.burst(item.cx, item.cy, (255, 255, 200), count=14, speed=180, life=0.4, glow=True)
        self.events.append("pickup")


def _box_overlap(b, x: float, y: float, w: float, h: float) -> bool:
    return b.x < x + w and b.x + b.w > x and b.y < y + h and b.y + b.h > y


__all__ = ["World", "InputState", "Checkpoint", "Goal"]
