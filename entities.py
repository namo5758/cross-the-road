"""Game-world entities and their local behavior.

These classes hold mutable state. Cross-object interactions remain in Game's
simulation methods so collision and level rules have one owner.
"""

import math
import random

from game_config import (
    BLOOD,
    BLOOD_HIGHLIGHT,
    CAR_COLORS,
    CROSSING_START_X,
    CROSSING_END_X,
    ICECREAM_COLORS,
    LANE_DIRECTION,
    LANE_HEIGHT,
    LANE_SPEED,
    MOTORCYCLE_COLORS,
    PERSON_TYPES,
    ROAD_BOTTOM,
    ROAD_TOP,
    SCREEN_WIDTH,
    SIDECAR_COLORS,
    TRUCK_COLORS,
    VEHICLES,
    WORLD_BOTTOM,
)
from geometry import box_corners, clamp, in_band, in_road, lane_center


# ---------------------------------------------------------------- entities
class Person:
    def __init__(self, kind, x, y, index):
        self.kind = kind
        self.index = index
        self.x, self.y = x, y
        # Waypoints are visited in order; an empty list means there is no walking destination.
        self.path = []
        self.alive = True
        self.saved = False
        self.is_walking = False
        # Countdown values use seconds. The simulation subtracts delta_time until an effect expires.
        # เวลาคงเหลือใช้หน่วยวินาที และลดลงตามเวลาที่ผ่านไปในแต่ละเฟรม
        self.cooldown = 0.0
        self.dash = 0.0
        self.tired = 0.0
        self.slip_time = 0.0
        self.slip_velocity = (0.0, 0.0)
        self.slip_immune = 0.0
        # Carrying links work both ways: the carrier points to the passenger, and the passenger to the carrier.
        self.carrying = None
        self.carried_by = None
        self.fuel = False
        self.alone_time = 0.0
        self.panic = False
        self.wander_direction = (0.0, 0.0)
        self.wander_time = 0.0
        self.sign_time = 0.0
        # Random starting phases stop every character from swinging their legs in perfect synchronization.
        self.walk_phase = random.random() * 10
        self.moving = False
        self.facing = 1
        # health & animation state
        self.maximum_health = PERSON_TYPES[kind]["health"]
        self.health = float(self.maximum_health)
        self.hurt_time = 0.0            # red flash after taking damage
        self.invulnerable_time = 0.0    # short grace period after a car hit
        self.down_time = 0.0            # knocked down, can't move
        self.burn_time = 0.0            # on fire
        self.charring_level = 0.0           # 0..1 how burnt the body looks
        self.pose = 0.0                 # 0 = standing, pi/2 = lying flat
        self.fall_direction = 1
        self.death_time = 0.0
        self.death_cause = None
        self.drip_time = 0.0

    @property
    def information(self):
        return PERSON_TYPES[self.kind]

    @property
    # Only living, unsaved people who are not being carried can respond independently.
    def active(self):
        return self.alive and not self.saved and self.carried_by is None

    @property
    # Severe injury means remaining health is below 40% of starting health.
    def injured(self):
        return self.health < self.maximum_health * 0.4

    def speed(self):
        if self.down_time > 0:
            return 0.0
        # Start with the character speed, then multiply by injury, fire, sprint, fatigue, and carrying effects.
        # Multipliers combine: for example, injury and carrying give base_speed * 0.6 * 0.8.
        # ตัวคูณมีผลต่อเนื่องกัน เช่น บาดเจ็บและอุ้มคนจะเหลือความเร็ว 0.6 × 0.8 = 48% ของปกติ
        current_speed = self.information["speed"]
        if self.injured:
            current_speed *= 0.6
        if self.burn_time > 0:
            current_speed *= 1.25            # running while on fire
        if self.dash > 0:
            current_speed *= 2.2
        elif self.tired > 0:
            current_speed *= 0.55
        if self.carrying:
            current_speed *= 0.8
        return current_speed

    def set_target(self, target_x, target_y):
        """Plan waypoints so people only cross the road on the zebra crossing."""
        target_y = clamp(target_y, 16, WORLD_BOTTOM - 10)
        target_x = clamp(target_x, 12, SCREEN_WIDTH - 12)
        if in_road(target_y):
            target_x = clamp(target_x, CROSSING_START_X + 8, CROSSING_END_X - 8)
        waypoints = []
        # Classify start and destination by curb position so the route can include crossing-entry waypoints.
        start_side = "near" if self.y >= ROAD_BOTTOM else "far" if self.y <= ROAD_TOP else "road"
        destination_side = "near" if target_y >= ROAD_BOTTOM else "far" if target_y <= ROAD_TOP else "road"
        if start_side != destination_side:
            if start_side != "road" and not in_band(self.x):
                curb_y = ROAD_BOTTOM + 10 if start_side == "near" else ROAD_TOP - 10
                waypoints.append((clamp(self.x, CROSSING_START_X + 8, CROSSING_END_X - 8), curb_y))
            if destination_side != "road" and not in_band(target_x):
                curb_y = ROAD_BOTTOM + 10 if destination_side == "near" else ROAD_TOP - 10
                base_x = waypoints[-1][0] if waypoints else clamp(self.x, CROSSING_START_X + 8, CROSSING_END_X - 8)
                waypoints.append((base_x, curb_y))
        waypoints.append((target_x, target_y))
        self.path = waypoints


class Car:
    def __init__(self, lane, kind, level_settings):
        self.lane = lane
        self.direction = LANE_DIRECTION[lane]
        self.kind = kind
        vehicle_specification = VEHICLES[kind]
        self.length = vehicle_specification["length"]
        self.width = vehicle_specification["width"]
        self.height = vehicle_specification["height"]
        speed_multiplier = vehicle_specification["speed"]
        self.color = random.choice({
            "truck": TRUCK_COLORS,
            "moto": MOTORCYCLE_COLORS,
            "sidecar": SIDECAR_COLORS,
            "icecream": ICECREAM_COLORS,
            "tanker": [(230, 232, 228)],
        }.get(kind, CAR_COLORS))
        self.cargo = random.choice(["passenger", "crates", "bottles"])   # what's in the sidecar
        self.fuse = 0.0          # tanker: seconds until it blows up after a crash
        self.burnt = False
        self.skid_points = None  # last wheel positions, for skid marks
        # Actual speed = lane speed * level multiplier * vehicle multiplier * random variation of +/-10%.
        # ความเร็วจริงมาจากความเร็วเลน คูณความยาก คูณประเภทรถ แล้วสุ่มให้ต่างกันเล็กน้อย
        self.base_speed = LANE_SPEED[lane] * level_settings["speed"] * speed_multiplier * random.uniform(0.9, 1.1)
        self.speed = self.base_speed
        # Spawn beyond the incoming screen edge so the vehicle enters smoothly.
        self.x = -self.length if self.direction > 0 else SCREEN_WIDTH + self.length
        self.y = lane_center(lane)
        self.base_angle = 0.0 if self.direction > 0 else math.pi
        self.heading = self.base_angle
        self.lateral_speed = 0.0
        self.skid = 0.0          # sliding on blood
        self.stall = 0.0         # braking after hitting someone
        self.wreck = False       # crashed, blocking the road
        self.wreck_time = 0.0
        self.towed = False       # hooked by a drone
        self.lift = 0.0          # height while being carried away
        self.rider_color = random.choice([(200, 60, 50), (50, 120, 200), (230, 200, 60)])

    @property
    def angle(self):
        return self.heading

    def blocks(self, lane_index):
        """A wreck blocks every lane it overlaps; a moving car only its own lane."""
        if not self.wreck:
            return self.lane == lane_index
        # Overlap occurs when center separation is smaller than the sum of half-widths, with a small margin.
        return abs(lane_center(lane_index) - self.y) < self.width / 2 + LANE_HEIGHT / 2 - 6

    # Use the nearest ground corner for drawing order so a car can cover objects behind it.
    def depth(self):
        return max(corner[1] for corner in box_corners(self.x, self.y, self.length, self.width, self.angle))

    # Stationary wrecks and towed cars cannot hit people; moving or sliding cars can.
    def dangerous(self):
        return not self.wreck and not self.towed and (self.speed > 25 or self.skid > 0)

    def hits(self, person_x, person_y, radius=8):
        # Rotate the person by the negative car angle to express their position in the car frame.
        # Collision then becomes two simple bounds checks against a rectangle expanded by the person radius.
        # หมุนตำแหน่งคนกลับให้ตรงกับแนวรถก่อน จึงตรวจได้ง่ายว่าคนอยู่ในกรอบรถหรือไม่
        cosine_angle, sine_angle = math.cos(-self.angle), math.sin(-self.angle)
        delta_x = person_x - self.x
        delta_y = person_y - self.y
        local_x = delta_x * cosine_angle - delta_y * sine_angle
        local_y = delta_x * sine_angle + delta_y * cosine_angle
        return abs(local_x) < self.length / 2 + radius and abs(local_y) < self.width / 2 + radius


class Drone:
    """Tow drone: flies in, hooks a wrecked car, lifts it and flies away."""
    def __init__(self, car):
        self.car = car
        # Choose the nearer horizontal exit and start the tow drone outside the upper part of the scene.
        exit_side = -1 if car.x < SCREEN_WIDTH / 2 else 1
        self.x = car.x + exit_side * 420
        self.y = -60.0
        self.z = 150.0
        self.exit_x = -260 if exit_side < 0 else SCREEN_WIDTH + 260
        self.state = "fly"
        self.time_elapsed = 0.0
        self.cable_extension = 0.0
        self.done = False

    def update(self, delta_time):
        target_car = self.car
        self.time_elapsed += delta_time
        # Tow sequence: approach the car, lower the cable, lift the car, then carry it off-screen.
        # โดรนทำงานเป็นสถานะตามลำดับ: บินเข้า → เกี่ยวรถ → ยกรถ → บินออก
        if self.state == "fly":
            delta_x = target_car.x - self.x
            delta_y = target_car.y - self.y
            distance = math.hypot(delta_x, delta_y)
            # Distance this frame = speed * elapsed seconds. Normalize the target vector to obtain direction.
            step = 380 * delta_time
            # Ease toward the target height: add a fraction of the remaining difference each frame.
            # The fraction is capped at 1 to avoid overshooting on a long frame.
            # ค่อย ๆ ขยับเข้าหาเป้าหมายตามสัดส่วนของระยะที่เหลือ จึงเคลื่อนนุ่มขึ้นโดยไม่เลยเป้า
            self.z += (120 - self.z) * min(1.0, 2 * delta_time)
            if distance <= step:
                self.x, self.y = target_car.x, target_car.y
                self.state = "hook"
                self.time_elapsed = 0.0
            else:
                self.x += delta_x / distance * step
                self.y += delta_y / distance * step
        elif self.state == "hook":
            # Progress = elapsed / duration, capped at 1; this extends the cable fully over 0.6 seconds.
            self.cable_extension = min(1.0, self.time_elapsed / 0.6)
            if self.time_elapsed > 0.7:
                target_car.towed = True              # no longer blocks traffic
                self.state = "lift"
                self.time_elapsed = 0.0
        elif self.state == "lift":
            # Interpolate lift height over 0.8 seconds: progress 0 is the start and 1 is fully lifted.
            # ความคืบหน้า = เวลาที่ผ่านไป / เวลาทั้งหมด เมื่อได้ 1 แปลว่ายกเสร็จแล้ว
            lift_progress = min(1.0, self.time_elapsed / 0.8)
            target_car.lift = 70 * lift_progress
            self.z = 120 + 40 * lift_progress
            if lift_progress >= 1:
                self.state = "away"
                self.time_elapsed = 0.0
        else:  # away
            delta_x = self.exit_x - self.x
            delta_y = -120 - self.y
            distance = math.hypot(delta_x, delta_y) or 1
            # Accelerate from 80 world units/second, adding 300 per second, with a maximum speed of 320.
            fly_speed = min(320, 80 + self.time_elapsed * 300)
            self.x += delta_x / distance * fly_speed * delta_time
            self.y += delta_y / distance * fly_speed * delta_time
            self.z += 20 * delta_time
            target_car.lift += 20 * delta_time
            target_car.x, target_car.y = self.x, self.y
            if distance < 30 or self.x < -240 or self.x > SCREEN_WIDTH + 240:
                self.done = True


class Puddle:
    def __init__(self, x, y, radius=24, color=BLOOD, highlight_color=BLOOD_HIGHLIGHT):
        self.x, self.y, self.radius = x, y, radius
        self.color, self.highlight_color = color, highlight_color
        self.life = 10.0
        # Track cars already affected by this puddle so the same puddle does not repeatedly trigger one car.
        self.hit_car_identifiers = set()
        # Overlap several randomly offset circles to make an irregular puddle instead of a perfect circle.
        self.blobs = [
            (random.uniform(-radius * 0.5, radius * 0.5),
             random.uniform(-radius * 0.4, radius * 0.4),
             random.uniform(radius * 0.45, radius * 0.85))
            for _ in range(5)
        ]
        self.blobs.append((0, 0, radius * 0.8))


class Fire:
    def __init__(self, x, y, radius=55):
        self.x, self.y, self.radius = x, y, radius
        self.life = 4.0


class Particle:
    def __init__(self, x, y, z, velocity_x, velocity_y, velocity_z, color, size, life, gravity=500, shape="dot"):
        self.x, self.y, self.z = x, y, z
        self.velocity_x = velocity_x
        self.velocity_y = velocity_y
        self.velocity_z = velocity_z
        self.color, self.size = color, size
        # Keep both remaining and initial lifetime so rendering can compute a fade fraction.
        self.life = self.maximum_life = life
        # Vertical acceleration: positive gravity pulls particles down; negative gravity makes smoke or flames rise.
        # แรงโน้มถ่วงบวกดึงเศษวัตถุลง ส่วนค่าลบทำให้ควันหรือเปลวไฟลอยขึ้น
        self.gravity = gravity
        self.shape = shape                  # "dot", "chunk" (car part) or "wheel"
        self.angle = random.uniform(0, math.tau)
        self.spin = random.uniform(-12, 12)
