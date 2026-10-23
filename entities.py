"""Game-world entities and their local behavior.

These classes hold mutable state. Cross-object interactions remain in Game's
simulation methods so collision and level rules have one owner.
"""

import math
import random

from game_config import (BLOOD, BLOOD_HI, CAR_COLS, CW_X0, CW_X1, LANE_DIR,
                         LANE_H, LANE_SPEED, MOTO_COLS, ROAD_BOT, ROAD_TOP,
                         SIDECAR_COLS, TRUCK_COLS, TYPES, VEHICLES, W,
                         WORLD_BOT, ICECREAM_COLS)
from geometry import box_corners, clamp, in_band, in_road, lane_center


# ---------------------------------------------------------------- entities
class Person:
    def __init__(self, kind, x, y, idx):
        self.kind = kind
        self.idx = idx
        self.x, self.y = x, y
        self.path = []
        self.alive = True
        self.saved = False
        self.go = False
        self.cd = 0.0
        self.dash = 0.0
        self.tired = 0.0
        self.slip_t = 0.0
        self.slip_v = (0.0, 0.0)
        self.slip_immune = 0.0
        self.carrying = None
        self.carried_by = None
        self.fuel = False
        self.alone_t = 0.0
        self.panic = False
        self.wander = (0.0, 0.0)
        self.wander_t = 0.0
        self.sign_t = 0.0
        self.walk = random.random() * 10
        self.moving = False
        self.facing = 1
        # health & animation state
        self.max_hp = TYPES[kind]["hp"]
        self.hp = float(self.max_hp)
        self.hurt_t = 0.0        # red flash after taking damage
        self.invuln = 0.0        # short grace period after a car hit
        self.down_t = 0.0        # knocked down, can't move
        self.burn_t = 0.0        # on fire
        self.char = 0.0          # 0..1 how burnt the body looks
        self.pose = 0.0          # 0 = standing, pi/2 = lying flat
        self.fall_dir = 1
        self.death_t = 0.0
        self.death_kind = None
        self.drip_t = 0.0

    @property
    def info(self):
        return TYPES[self.kind]

    @property
    def active(self):
        return self.alive and not self.saved and self.carried_by is None

    @property
    def injured(self):
        return self.hp < self.max_hp * 0.4

    def speed(self):
        if self.down_t > 0:
            return 0.0
        s = self.info["speed"]
        if self.injured:
            s *= 0.6
        if self.burn_t > 0:
            s *= 1.25            # running while on fire
        if self.dash > 0:
            s *= 2.2
        elif self.tired > 0:
            s *= 0.55
        if self.carrying:
            s *= 0.8
        return s

    def set_target(self, tx, ty):
        """Plan waypoints so people only cross the road on the zebra crossing."""
        ty = clamp(ty, 16, WORLD_BOT - 10)
        tx = clamp(tx, 12, W - 12)
        if in_road(ty):
            tx = clamp(tx, CW_X0 + 8, CW_X1 - 8)
        pts = []
        here_side = "near" if self.y >= ROAD_BOT else "far" if self.y <= ROAD_TOP else "road"
        there_side = "near" if ty >= ROAD_BOT else "far" if ty <= ROAD_TOP else "road"
        if here_side != there_side:
            if here_side != "road" and not in_band(self.x):
                curb = ROAD_BOT + 10 if here_side == "near" else ROAD_TOP - 10
                pts.append((clamp(self.x, CW_X0 + 8, CW_X1 - 8), curb))
            if there_side != "road" and not in_band(tx):
                curb = ROAD_BOT + 10 if there_side == "near" else ROAD_TOP - 10
                bx = pts[-1][0] if pts else clamp(self.x, CW_X0 + 8, CW_X1 - 8)
                pts.append((bx, curb))
        pts.append((tx, ty))
        self.path = pts


class Car:
    def __init__(self, lane, kind, level_settings):
        self.lane = lane
        self.dir = LANE_DIR[lane]
        self.kind = kind
        spec = VEHICLES[kind]
        self.length, self.width, self.height = spec["length"], spec["width"], spec["height"]
        mult = spec["speed"]
        self.col = random.choice({"truck": TRUCK_COLS, "moto": MOTO_COLS, "sidecar": SIDECAR_COLS,
                                  "icecream": ICECREAM_COLS, "tanker": [(230, 232, 228)]}.get(kind, CAR_COLS))
        self.cargo = random.choice(["passenger", "crates", "bottles"])   # what's in the sidecar
        self.fuse = 0.0          # tanker: seconds until it blows up after a crash
        self.burnt = False
        self.skid_points = None        # last wheel positions, for skid marks
        self.base_speed = LANE_SPEED[lane] * level_settings["speed"] * mult * random.uniform(0.9, 1.1)
        self.speed = self.base_speed
        self.x = -self.length if self.dir > 0 else W + self.length
        self.y = lane_center(lane)
        self.base_ang = 0.0 if self.dir > 0 else math.pi
        self.heading = self.base_ang
        self.lateral_speed = 0.0
        self.skid = 0.0          # sliding on blood
        self.stall = 0.0         # braking after hitting someone
        self.wreck = False       # crashed, blocking the road
        self.wreck_t = 0.0
        self.towed = False       # hooked by a drone
        self.lift = 0.0          # height while being carried away
        self.rider = random.choice([(200, 60, 50), (50, 120, 200), (230, 200, 60)])

    @property
    def ang(self):
        return self.heading

    def blocks(self, lane):
        """A wreck blocks every lane it overlaps; a moving car only its own lane."""
        if not self.wreck:
            return self.lane == lane
        return abs(lane_center(lane) - self.y) < self.width / 2 + LANE_H / 2 - 6

    def depth(self):
        return max(p[1] for p in box_corners(self.x, self.y, self.length, self.width, self.ang))

    def dangerous(self):
        return not self.wreck and not self.towed and (self.speed > 25 or self.skid > 0)

    def hits(self, px, py, r=8):
        c, s = math.cos(-self.ang), math.sin(-self.ang)
        dx, dy = px - self.x, py - self.y
        lx, ly = dx * c - dy * s, dx * s + dy * c
        return abs(lx) < self.length / 2 + r and abs(ly) < self.width / 2 + r


class Drone:
    """Tow drone: flies in, hooks a wrecked car, lifts it and flies away."""
    def __init__(self, car):
        self.car = car
        side = -1 if car.x < W / 2 else 1
        self.x, self.y, self.z = car.x + side * 420, -60.0, 150.0
        self.exit_x = -260 if side < 0 else W + 260
        self.state = "fly"
        self.t = 0.0
        self.cable = 0.0
        self.done = False

    def update(self, dt):
        c = self.car
        self.t += dt
        if self.state == "fly":
            dx, dy = c.x - self.x, c.y - self.y
            d = math.hypot(dx, dy)
            step = 380 * dt
            self.z += (120 - self.z) * min(1.0, 2 * dt)
            if d <= step:
                self.x, self.y = c.x, c.y
                self.state, self.t = "hook", 0.0
            else:
                self.x += dx / d * step
                self.y += dy / d * step
        elif self.state == "hook":
            self.cable = min(1.0, self.t / 0.6)
            if self.t > 0.7:
                c.towed = True              # no longer blocks traffic
                self.state, self.t = "lift", 0.0
        elif self.state == "lift":
            k = min(1.0, self.t / 0.8)
            c.lift = 70 * k
            self.z = 120 + 40 * k
            if k >= 1:
                self.state, self.t = "away", 0.0
        else:  # away
            dx, dy = self.exit_x - self.x, -120 - self.y
            d = math.hypot(dx, dy) or 1
            sp = min(320, 80 + self.t * 300)
            self.x += dx / d * sp * dt
            self.y += dy / d * sp * dt
            self.z += 20 * dt
            c.lift += 20 * dt
            c.x, c.y = self.x, self.y
            if d < 30 or self.x < -240 or self.x > W + 240:
                self.done = True


class Puddle:
    def __init__(self, x, y, r=24, col=BLOOD, hi=BLOOD_HI):
        self.x, self.y, self.r = x, y, r
        self.col, self.hi = col, hi
        self.life = 10.0
        self.hit = set()
        self.blobs = [(random.uniform(-r * 0.5, r * 0.5), random.uniform(-r * 0.4, r * 0.4),
                       random.uniform(r * 0.45, r * 0.85)) for _ in range(5)]
        self.blobs.append((0, 0, r * 0.8))


class Fire:
    def __init__(self, x, y, r=55):
        self.x, self.y, self.r = x, y, r
        self.life = 4.0


class Particle:
    def __init__(self, x, y, z, vx, vy, vz, col, size, life, grav=500, shape="dot"):
        self.x, self.y, self.z = x, y, z
        self.vx, self.lateral_speed, self.vz = vx, vy, vz
        self.col, self.size = col, size
        self.life = self.max_life = life
        self.grav = grav
        self.shape = shape                  # "dot", "chunk" (car part) or "wheel"
        self.ang = random.uniform(0, math.tau)
        self.spin = random.uniform(-12, 12)



