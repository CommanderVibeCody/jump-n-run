import pytest

from game import constants as C
from game.enemies import ENEMY_TYPES, Recruit, Shooter
from game.player import InputState
from game.weapons import Projectile
from helpers import make_world, settle, steps


def test_bullets_damage_and_kill_enemies():
    rows = ["                    ", "  P       e         ", "####################"]
    w = make_world(rows)
    settle(w)
    enemy = w.enemies[0]
    assert isinstance(enemy, Recruit)
    w.step(InputState(shoot=True))
    for _ in range(40):
        w.step()
        if enemy.health < enemy.MAX_HEALTH:
            break
    assert enemy.health == pytest.approx(enemy.MAX_HEALTH - 25)
    for _ in range(300):
        w.step(InputState(shoot=True))
        if not w.enemies:
            break
    assert not w.enemies
    assert w.kills == 1
    assert w.score >= Recruit.SCORE


def test_rocket_explosion_hits_enemies_in_radius():
    rows = ["                    ", "  P      ee         ", "####################"]
    w = make_world(rows)
    settle(w)
    w.player.give_weapon("rocket")
    walkers = list(w.enemies)
    w.step(InputState(shoot=True))
    for _ in range(200):
        w.step()
        if "explosion" in w.events:
            break
    assert "explosion" in w.events
    # both walkers are caught by the blast (the nearer one dies)
    assert w.kills >= 1
    assert all(e.health < e.MAX_HEALTH for e in walkers)


def test_walker_turns_around_at_ledge():
    rows = ["     #               ", "  P  #  e            ", "######  ####         "]
    w = make_world(rows)
    walker = w.enemies[0]
    walker.facing = -1
    xs = []
    for _ in range(600):
        w.step()
        xs.append(walker.body.x)
    assert walker.alive
    assert min(xs) >= 8 * C.TILE - 6  # turned around at the ledge (x = 8 tiles)
    assert max(xs) + walker.W <= 12 * C.TILE + 6  # and at the other end (x = 12 tiles)
    assert walker.body.y < 2 * C.TILE  # still on the platform


def test_walker_turns_around_at_wall():
    rows = ["          ", "#P#   e  #", "##########"]
    w = make_world(rows)
    walker = w.enemies[0]
    walker.facing = 1
    steps(w, 240)
    assert walker.facing == -1 or walker.body.vx < 0 or walker.body.hit_right


def test_shooter_fires_at_visible_player():
    rows = ["                    ", "  P        s        ", "####################"]
    w = make_world(rows)
    fired = False
    for _ in range(int(3 / C.FIXED_DT)):
        w.step()
        if any(p.owner == "enemy" for p in w.projectiles):
            fired = True
            break
    assert fired


def test_shooter_cannot_see_through_walls():
    rows = ["       #            ", "  P    #   s        ", "####################"]
    w = make_world(rows)
    for _ in range(int(3 / C.FIXED_DT)):
        w.step()
        assert not any(p.owner == "enemy" for p in w.projectiles)


def test_enemy_bullet_damages_player_and_grants_invulnerability():
    w = make_world()
    settle(w)
    b = w.player.body
    w.projectiles.append(Projectile(b.cx + 20, b.cy, 3.14159, 300, 12, "enemy", 2.0, (255, 0, 0)))
    steps(w, 20)
    assert w.player.health == C.PLAYER_MAX_HEALTH - 12
    assert w.player.invulnerable > 0
    w.projectiles.append(Projectile(b.cx + 20, b.cy, 3.14159, 300, 12, "enemy", 2.0, (255, 0, 0)))
    steps(w, 10)
    assert w.player.health == C.PLAYER_MAX_HEALTH - 12  # still invulnerable


def test_contact_with_enemy_hurts_player():
    rows = ["                    ", "  P  e              ", "####################"]
    w = make_world(rows)
    e = w.enemies[0]
    e.body.x = w.player.body.x  # walk straight into the player before it can shoot
    for _ in range(240):
        w.step()
        if w.player.health < C.PLAYER_MAX_HEALTH:
            break
    assert w.player.health == C.PLAYER_MAX_HEALTH - Recruit.CONTACT_DAMAGE


def test_stomping_an_enemy_damages_it_and_bounces():
    # the player starts right above a shooter (70 HP)
    w = make_world(["          "] * 2 + ["    P     ", "          ", "    s     ", "##########"])
    e = w.enemies[0]
    e.body.vx = 0
    bounced = False
    for _ in range(60):
        w.step()
        if "stomp" in w.events:
            bounced = True
            break
    assert bounced
    assert e.health == e.MAX_HEALTH - C.STOMP_DAMAGE
    assert w.player.body.vy < 0
    assert w.player.health == C.PLAYER_MAX_HEALTH


def test_only_soldiers_remain():
    assert "w" not in ENEMY_TYPES and "d" not in ENEMY_TYPES
    assert all(cls.human for cls in ENEMY_TYPES.values())
