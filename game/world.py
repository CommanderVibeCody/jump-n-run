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
from .enemies import ENEMY_TYPES, Barrel, Corpse, Enemy, make_enemy
from .level import Level, LevelDef
from .physics import approach
from .player import InputState, Player
from .weapons import PICKUP_WEAPON, WEAPONS, Pickup, Projectile

PICKUP_KINDS = dict(PICKUP_WEAPON, **{"+": "health", "a": "ammo"})
ENEMY_CHARS = "".join(ENEMY_TYPES)
HEALTH_PACK = 40
HITSTOP_KILL = 0.045
HITSTOP_BIG = 0.09
BURN_DPS = 22.0
GIB_COLORS = [(170, 20, 25), (130, 10, 15), (230, 190, 150), (90, 110, 60), (200, 30, 40)]


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
                 start_level: int = 0, lives: int = C.PLAYER_LIVES, blood: bool = True) -> None:
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
        self.sounds: List[str] = []   # sound effects requested since the last drain
        self.blood = blood
        self.hitstop = 0.0
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
        self.enemies: List[Enemy] = [make_enemy(s.kind, s.tx, s.ty) for s in self.level.spawns_of(ENEMY_CHARS)]
        self.barrels: List[Barrel] = [Barrel(s.tx, s.ty) for s in self.level.spawns_of("b")]
        self.corpses: List[Corpse] = []
        self.pickups: List[Pickup] = [Pickup(PICKUP_KINDS[s.kind], s.tx, s.ty)
                                      for s in self.level.spawns_of("".join(PICKUP_KINDS))]
        self.checkpoints = [Checkpoint(s.tx, s.ty) for s in self.level.spawns_of("C")]
        goals = self.level.spawns_of("G")
        self.goal = Goal(goals[0].tx, goals[0].ty) if goals else None
        self.projectiles: List[Projectile] = []
        self.state = "playing"
        self.state_timer = 0.0
        self.level_time = 0.0
        self.camera = Camera(self.level.pixel_width, self.level.pixel_height)
        self.inside_house = None
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
        if self.hitstop > 0:  # freeze frame after kills
            self.hitstop -= dt
            return
        self.time += dt
        self.effects.update(dt, self.level)
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
        self._update_barrels(dt)
        self._update_projectiles(dt)
        for c in self.corpses:
            c.update(dt, self.level)
            if c.burning and self.rng.random() < 0.3:
                self.effects.fire(c.body.cx, c.body.cy)
        self.corpses = [c for c in self.corpses if c.life > 0 and c.body.y < self.level.pixel_height + 100]
        if self.state == "playing":
            self._check_contacts()
        self.camera.follow(self.player.body.cx, self.player.body.cy, self.player.facing, dt)

    def sfx(self, name: str) -> None:
        self.sounds.append(name)

    def drain_sounds(self) -> List[str]:
        out, self.sounds = self.sounds, []
        return out

    # ------------------------------------------------------------- player
    def _update_player(self, inp: InputState, dt: float) -> None:
        p = self.player
        if inp.switch:
            if p.cycle_weapon(inp.switch):
                self.events.append("switch")
                self.sfx("reload")
        if inp.select_slot is not None:
            if p.select_slot(inp.select_slot):
                self.events.append("switch")
                self.sfx("reload")

        p.update(inp, self.level, dt)
        b = p.body
        if p.just_jumped:
            self.effects.dust(b.cx, b.bottom, 5)
            self.events.append("jump")
            self.sfx("jump")
        if p.just_landed and p.landed_speed > 300:
            self.effects.dust(b.cx, b.bottom, int(4 + p.landed_speed / 120))
            self.events.append("land")
            self.sfx("land")
        step = int(p.run_phase / math.pi)
        if b.on_ground and step != getattr(self, "_last_step", step):
            self.sfx("step")
        self._last_step = step
        if b.on_ground and abs(b.vx) > 200 and self.rng.random() < 0.08:
            self.effects.dust(b.cx - p.facing * 8, b.bottom, 1)

        self._update_doors(inp, dt)

        if inp.shoot:
            self._fire_player_weapon()

        if self.level.touches_spikes(b.x, b.y, b.w, b.h):
            if p.invulnerable <= 0:
                self.damage_player(C.SPIKE_DAMAGE, None)
            if p.alive:
                b.vy = -650.0
        if b.y > self.level.pixel_height + 64:
            self.kill_player()

    # -------------------------------------------------------------- doors
    def _body_in_door(self, door) -> bool:
        dx, dy, dw, dh = door.rect
        bodies = [self.player.body] + [e.body for e in self.enemies if e.alive]
        return any(b.right > dx and b.left < dx + dw and b.bottom > dy and b.top < dy + dh for b in bodies)

    def open_door(self, door, side: int) -> bool:
        if door.open:
            return False
        door.open = True
        door.side = side
        self.events.append("door_open")
        self.sfx("door")
        return True

    def close_door(self, door) -> bool:
        if not door.open or door.broken or self._body_in_door(door):
            return False
        door.open = False
        self.events.append("door_close")
        self.sfx("door")
        return True

    def _update_doors(self, inp: InputState, dt: float) -> None:
        p = self.player
        b = p.body
        level = self.level
        # walking into a closed door opens it
        if b.hit_left or b.hit_right:
            side = -1 if b.hit_left else 1
            fx = b.left - 2 if side < 0 else b.right + 2
            tx = math.floor(fx / C.TILE)
            for ty in range(math.floor(b.top / C.TILE), math.floor((b.bottom - 1) / C.TILE) + 1):
                door = level.door_at.get((tx, ty))
                if door is not None and not door.open:
                    self.open_door(door, side)
                    break
        if inp.interact:
            door = level.door_near(b.cx, b.cy)
            if door is not None:
                if door.open:
                    self.close_door(door)
                else:
                    self.open_door(door, 1 if door.rect[0] > b.cx else -1)
        for door in level.doors:
            target = 1.0 if door.open else 0.0
            door.anim = approach(door.anim, target, dt * 6)
        # houses: reveal the interior while the player is inside
        inside = level.house_at_point(b.cx, b.cy)
        self.inside_house = inside
        for h in level.houses:
            h.reveal = approach(h.reveal, 1.0 if h is inside else 0.0, dt * 4)

    def _fire_player_weapon(self) -> None:
        p = self.player
        w = p.weapon
        if not w.can_fire():
            if w.cooldown <= 0 and not w.has_ammo:
                self.sfx("empty")
            return
        mx, my = p.muzzle()
        spec = w.spec
        if spec.hitscan:
            w.consume()
            self._fire_hitscan(mx, my, p.aim_angle, spec)
        else:
            shots = w.fire(mx, my, p.aim_angle, self.rng, "player")
            if not shots:
                return
            self.projectiles.extend(shots)
        if spec.kind != "flame":
            self.effects.muzzle_flash(mx, my, p.aim_angle, spec.color,
                                      big=spec.pellets > 1 or spec.explosion_radius > 0 or spec.damage >= 100)
        if spec.casing:
            sx, sy = p.shoulder()
            self.effects.casing(sx + math.cos(p.aim_angle) * 8, sy + math.sin(p.aim_angle) * 8, p.facing, spec.casing)
        self.effects.shake(spec.shake)
        p.recoil_anim = 1.0
        p.body.vx -= math.cos(p.aim_angle) * spec.recoil
        if not p.body.on_ground:
            p.body.vy -= math.sin(p.aim_angle) * spec.recoil * 0.5
        self.events.append("shoot")
        self.sfx(spec.key)
        if not w.has_ammo:
            self.events.append("out_of_ammo")
            self.sfx("empty")
            self.effects.text("OUT OF AMMO", p.body.cx, p.body.y - 20, C.RED, 1.0)
            p.current = "pistol"

    def _fire_hitscan(self, x: float, y: float, angle: float, spec) -> None:
        """Railgun: an instant beam that pierces every enemy up to a wall."""
        dx, dy = math.cos(angle), math.sin(angle)
        hit = set()
        ex, ey = x, y
        for i in range(1, 400):
            px, py = x + dx * i * 4, y + dy * i * 4
            ex, ey = px, py
            if self.level.solid_at(px, py):
                break
            for e in self.enemies:
                if e.alive and id(e) not in hit and e.body.contains_point(px, py, 2):
                    hit.add(id(e))
                    self.damage_enemy(e, spec.damage, dx * spec.knockback, dy * spec.knockback - 120,
                                      hit_x=px, hit_y=py, big=True)
            for bar in self.barrels:
                if bar.alive and id(bar) not in hit and bar.body.contains_point(px, py, 2):
                    hit.add(id(bar))
                    bar.take_damage(spec.damage)
        self.effects.beam(x, y, ex, ey, spec.color)
        self.effects.burst(ex, ey, spec.color, count=16, speed=300, life=0.4, glow=True)

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
        self.sfx("hurt")
        if self.blood:
            self.effects.blood(p.body.cx, p.body.cy, (1 if source_x is None or p.body.cx >= source_x else -1), -0.3, 10)
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
        if self.blood:
            self.effects.gibs(b.cx, b.cy, [(200, 30, 40), (50, 120, 230), (255, 214, 170)], 8)
        self.events.append("death")
        self.sfx("death")

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
            if not e.alive:
                continue
            shots = e.update(dt, self.level, self.player, self.rng, self.projectiles)
            if shots:
                self.projectiles.extend(shots)
                self.sfx("grenade_launcher" if shots[0].kind == "grenade" else "enemy_shot")
                gx, gy = shots[0].x, shots[0].y
                self.effects.muzzle_flash(gx, gy, math.atan2(shots[0].vy, shots[0].vx), (255, 120, 120))
                if e.human and shots[0].kind != "grenade":
                    self.effects.casing(e.body.cx, e.body.y + 16, e.facing)
            if e.burn > 0 and e.alive:
                e.burn -= dt
                if self.rng.random() < 0.5:
                    self.effects.fire(e.body.cx + self.rng.uniform(-8, 8), e.body.cy + self.rng.uniform(-10, 10))
                self.damage_enemy(e, BURN_DPS * dt, quiet=True)
        if any(not e.alive for e in self.enemies):
            self.enemies = [e for e in self.enemies if e.alive]

    def damage_enemy(self, enemy: Enemy, amount: float, knock_x: float = 0.0, knock_y: float = 0.0,
                     hit_x: Optional[float] = None, hit_y: Optional[float] = None, quiet: bool = False,
                     big: bool = False, explosive: bool = False) -> bool:
        if not enemy.alive:
            return False
        killed = enemy.take_damage(amount, knock_x, knock_y)
        b = enemy.body
        hx = b.cx if hit_x is None else hit_x
        hy = b.cy if hit_y is None else hit_y
        kd = math.hypot(knock_x, knock_y)
        dir_x, dir_y = (knock_x / kd, knock_y / kd) if kd > 1e-6 else (0.0, -1.0)
        if not quiet:
            if self.blood:
                self.effects.blood(hx, hy, dir_x, dir_y, int(8 + min(30, amount / 3)), 1.0 + min(1.0, amount / 100))
            else:
                self.effects.impact(hx, hy, (255, 200, 120))
        if killed:
            self.kills += 1
            self.score += enemy.SCORE
            self.effects.text(f"+{enemy.SCORE}", b.cx, b.y - 10, C.ACCENT, 0.9)
            self.effects.shake(0.35)
            self.hitstop = max(self.hitstop, HITSTOP_BIG if (big or explosive) else HITSTOP_KILL)
            self.events.append("enemy_killed")
            self.sfx("enemy_death")
            if explosive and self.blood and amount >= 40:
                self.effects.gibs(b.cx, b.cy, GIB_COLORS + [enemy.PALETTE["uniform"]], 12)
                self.events.append("gibbed")
            else:
                spin = (6 + kd / 60) * (1 if knock_x >= 0 else -1)
                vx = knock_x * (1.6 if explosive else 1.0)
                vy = min(-180.0, knock_y * (1.4 if explosive else 1.0) - 120)
                corpse = Corpse(enemy, vx, vy, spin)
                self.corpses.append(corpse)
        elif not quiet:
            self.events.append("enemy_hit")
            self.sfx("enemy_hit")
        return killed

    def _update_barrels(self, dt: float) -> None:
        for bar in self.barrels:
            if not bar.alive:
                continue
            if bar.triggered and self.rng.random() < 0.6:
                self.effects.fire(bar.body.cx, bar.body.y)
            if bar.update(dt, self.level):
                self.explode_at(bar.body.cx, bar.body.cy, Barrel.RADIUS, Barrel.DAMAGE, 520, "barrel")
                self.effects.burst(bar.body.cx, bar.body.cy, [(200, 50, 40), (90, 90, 90)], count=10,
                                   speed=500, life=2.5, size=4, gravity=1400, collide=1, kind="debris")
                self.events.append("barrel_exploded")
        self.barrels = [bar for bar in self.barrels if bar.alive]

    # -------------------------------------------------------- projectiles
    def _update_projectiles(self, dt: float) -> None:
        for pr in self.projectiles:
            if not pr.alive:
                continue
            pr.update(dt, self.level)
            if pr.kind == "rocket" and self.rng.random() < 0.8:
                self.effects.smoke(pr.x - pr.dir_x * 10, pr.y - pr.dir_y * 10)
            elif pr.kind == "grenade":
                if pr.bounced:
                    self.sfx("bounce")
                if self.rng.random() < 0.3:
                    self.effects.smoke(pr.x, pr.y)
            elif pr.kind == "flame" and self.rng.random() < 0.25:
                self.effects.fire(pr.x, pr.y)
            if not pr.alive:
                if pr.explosive and (pr.hit_wall or pr.expired):
                    self.explode(pr)
                elif pr.hit_wall and pr.kind != "flame":
                    self.effects.impact(pr.x - pr.dir_x * 3, pr.y - pr.dir_y * 3, pr.color)
                continue
            # barrels can be shot by anyone
            for bar in self.barrels:
                if bar.alive and id(bar) not in pr.hit_ids and bar.body.contains_point(pr.x, pr.y, pr.radius):
                    if pr.explosive:
                        pr.alive = False
                        self.explode(pr)
                        break
                    bar.take_damage(pr.damage)
                    pr.hit_ids.add(id(bar))
                    self.effects.impact(pr.x, pr.y, (255, 200, 120))
                    if pr.pierce <= 0:
                        pr.alive = False
                        break
                    pr.pierce -= 1
            if not pr.alive:
                continue
            if pr.owner == "player":
                for e in self.enemies:
                    if not e.alive or id(e) in pr.hit_ids or not e.body.contains_point(pr.x, pr.y, pr.radius):
                        continue
                    if pr.explosive:
                        pr.alive = False
                        self.explode(pr)
                        break
                    pr.hit_ids.add(id(e))
                    if pr.burn > 0:
                        e.burn = max(e.burn, pr.burn)
                    self.damage_enemy(e, pr.damage, pr.dir_x * pr.knockback, -60.0, pr.x, pr.y,
                                      quiet=pr.kind == "flame", big=pr.damage >= 100)
                    if pr.pierce <= 0:
                        pr.alive = False
                        break
                    pr.pierce -= 1
            elif self.state == "playing" and self.player.alive:
                if self.player.body.contains_point(pr.x, pr.y, pr.radius):
                    pr.alive = False
                    if pr.explosive:
                        self.explode(pr)
                    else:
                        self.effects.impact(pr.x, pr.y, pr.color)
                        self.damage_player(pr.damage, pr.x - pr.dir_x * 10)
        self.projectiles = [pr for pr in self.projectiles if pr.alive]

    def explode(self, pr: Projectile) -> None:
        x, y = pr.x - pr.dir_x * 4, pr.y - pr.dir_y * 4
        if self.level.solid_at(x, y):
            x, y = pr.prev_x, pr.prev_y
        self.explode_at(x, y, pr.explosion_radius, pr.damage, pr.knockback, pr.owner)

    def explode_at(self, x: float, y: float, r: float, damage: float, knockback: float, source: str) -> None:
        """Area damage with linear falloff, knockback and a shockwave.

        Player explosives never hurt the player (rocket jumps are allowed);
        enemy grenades and barrels do."""
        self.effects.explosion(x, y, r)
        self.events.append("explosion")
        self.sfx("explosion")
        self.hitstop = max(self.hitstop, 0.03)
        for e in list(self.enemies):
            if not e.alive:
                continue
            dx, dy = e.body.cx - x, e.body.cy - y
            d = math.hypot(dx, dy)
            if d < r + e.body.w / 2:
                falloff = max(0.3, 1.0 - d / (r + e.body.w / 2))
                nx, ny = (dx / d, dy / d) if d > 1e-6 else (0.0, -1.0)
                self.damage_enemy(e, damage * falloff, nx * knockback * falloff,
                                  ny * knockback * falloff - 200, explosive=True)
        for door in self.level.doors:
            dx, dy, dw, dh = door.rect
            if not door.broken and math.hypot(dx + dw / 2 - x, dy + dh / 2 - y) < r + dh / 2:
                door.open = door.broken = True
                door.side = 1 if dx > x else -1
                self.effects.burst(dx + dw / 2, dy + dh / 2, (120, 80, 45), count=14, speed=260, life=1.6,
                                   size=3, gravity=1200, collide=1, kind="debris")
        for bar in self.barrels:
            if bar.alive and math.hypot(bar.body.cx - x, bar.body.cy - y) < r + 12:
                bar.take_damage(Barrel.MAX_HEALTH)
                bar.body.vy -= 150
        p = self.player
        if p.alive:
            dx, dy = p.body.cx - x, p.body.cy - y
            d = math.hypot(dx, dy)
            if d < r * 1.1:
                k = 1.0 - d / (r * 1.1)
                nx, ny = (dx / d, dy / d) if d > 1e-6 else (0.0, -1.0)
                p.body.vx += nx * 900 * k
                p.body.vy += ny * 900 * k
                p.body.on_ground = False
                if source != "player":
                    self.damage_player(max(8.0, damage * 0.45 * k), None)

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
            stomping = b.vy > 50 and b.bottom - e.body.top < 16
            if stomping:
                self.damage_enemy(e, C.STOMP_DAMAGE, 0.0, 200.0)
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
                self.sfx("checkpoint")
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
            self.sfx("level_complete")

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
        self.sfx("weapon_pickup" if item.is_weapon else "pickup")


def _box_overlap(b, x: float, y: float, w: float, h: float) -> bool:
    return b.x < x + w and b.x + b.w > x and b.y < y + h and b.y + b.h > y


__all__ = ["World", "InputState", "Checkpoint", "Goal"]
