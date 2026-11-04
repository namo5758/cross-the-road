"""Simulation, collision, and outcome rules for Cross the Road.

GameSimulation mutates the Game state supplied by the coordinator. Rendering and
input stay out of this module so frame rules can be read top-to-bottom here.
"""

import math
import random

import pygame

from entities import Car, Drone, Fire, Particle, Puddle
from game_config import (
    ACCENT_COLOR,
    BAD_COLOR,
    BLOOD,
    BLOOD_HIGHLIGHT,
    CROSSING_START_X,
    CROSSING_END_X,
    GOAL_Y,
    GOOD_COLOR,
    ICECREAM_GOO,
    LANES,
    ROAD_BOTTOM,
    ROAD_TOP,
    SCREEN_WIDTH,
    VEHICLES,
    WORLD_BOTTOM,
)
from geometry import clamp, in_band, in_road, lane_center, local, project, shade


class GameSimulation:
    # One simulation frame: update traffic and animation, then active gameplay, then temporary effects.
    # delta_time is elapsed seconds; speed * delta_time gives movement for this frame.
    # ระยะที่เคลื่อนในเฟรมนี้ = ความเร็ว × เวลาที่ผ่านไป เช่น 60 หน่วย/วินาที × 1/60 วินาที = 1 หน่วย
    def update(self, delta_time):
        if self.state == "title" or self.paused:
            return
        if self.state == "play":
            self.elapsed_time += delta_time
        self.update_traffic(delta_time)
        for person in self.people:
            self.animate_person(person, delta_time)
        if self.state == "play":
            for person in self.people:
                self.update_person(person, delta_time)
            self.check_hits()
            self.check_end()
        else:
            self.end_screen_timer += delta_time

        for puddle in self.blood_puddles:
            puddle.life -= delta_time
        self.blood_puddles = [puddle for puddle in self.blood_puddles if puddle.life > 0]

        for fire in self.fires:
            fire.life -= delta_time
            if random.random() < 0.6:
                angle = random.uniform(0, math.tau)
                radius = random.uniform(0, fire.radius * 0.8)
                self.particles.append(Particle(
                    fire.x + math.cos(angle) * radius,
                    fire.y + math.sin(angle) * radius * 0.6,
                    4,
                    0,
                    0,
                    random.uniform(40, 90),
                    random.choice([(255, 150, 40), (255, 90, 30), (255, 210, 80)]),
                    random.uniform(2, 4),
                    0.6,
                    gravity=-20
                ))
        self.fires = [fire for fire in self.fires if fire.life > 0]

        for particle in self.particles:
            particle.life -= delta_time
            # Euler integration: position += velocity * time, then vertical velocity -= gravity * time.
            # อัปเดตตำแหน่งจากความเร็วก่อน แล้วปรับความเร็วแนวดิ่งด้วยแรงโน้มถ่วง
            particle.x += particle.velocity_x * delta_time
            particle.y += particle.velocity_y * delta_time
            particle.z += particle.velocity_z * delta_time
            particle.velocity_z -= particle.gravity * delta_time
            particle.angle += particle.spin * delta_time
            if particle.z < 0:
                if particle.shape != "dot" and particle.velocity_z < -90:      # car parts bounce
                    # Reverse the downward velocity and keep 40% for a smaller bounce; reduce horizontal motion too.
                    particle.z, particle.velocity_z = 0, -particle.velocity_z * 0.4
                    particle.velocity_x *= 0.6
                    particle.velocity_y *= 0.6
                    particle.spin *= 0.6
                else:
                    particle.z, particle.velocity_z = 0, 0
                    particle.velocity_x *= 0.5
                    particle.velocity_y *= 0.5
                    particle.spin *= 0.5
        self.particles = [particle for particle in self.particles if particle.life > 0]

        self.active_surface_shake_strength = max(0.0, self.active_surface_shake_strength - 45 * delta_time)
        self.flash_intensity = max(0.0, self.flash_intensity - 3 * delta_time)

        for impact_message in self.impact_messages:
            impact_message[3] -= delta_time
        self.impact_messages = [impact_message for impact_message in self.impact_messages if impact_message[3] > 0]

        self.skid_mark_fade_timer += delta_time
        if self.skid_mark_fade_timer > 0.5:                      # skid marks slowly fade away
            self.skid_mark_fade_timer = 0
            # Multiplicative fading scales alpha by 246/255 every half-second while keeping the color channels unchanged.
            self.skid_mark_surface.fill((255, 255, 255, 246), special_flags=pygame.BLEND_RGBA_MULT)

        for floater in self.floating_messages:
            floater[4] -= delta_time
            if floater[3]:
                floater[2] += 30 * delta_time
        self.floating_messages = [floater for floater in self.floating_messages if floater[4] > 0]

        for toast_entry in self.toast_messages:
            toast_entry[1] -= delta_time
        self.toast_messages = [toast_entry for toast_entry in self.toast_messages if toast_entry[1] > 0]

    def update_traffic(self, delta_time, pre_warm=False):
        level_settings = self.current_level
        for lane_index in range(LANES):
            self.lane_freeze_timers[lane_index] = max(0.0, self.lane_freeze_timers[lane_index] - delta_time)
            self.spawn_timers[lane_index] -= delta_time
            if self.spawn_timers[lane_index] <= 0:
                # Weighted selection: chance of a kind = its mix weight / sum of all mix weights.
                # โอกาสสุ่มรถแต่ละชนิด = น้ำหนักของชนิดนั้น / ผลรวมน้ำหนักรถทั้งหมด
                vehicle_kind = random.choices(list(level_settings["mix"]), weights=list(level_settings["mix"].values()))[0]
                new_car = Car(lane_index, vehicle_kind, level_settings)
                # A new vehicle needs center separation >= half both lengths + 40 units of entry clearance.
                edge_clear = all(
                    not (other_car.blocks(lane_index) and abs(other_car.x - new_car.x) < (other_car.length + new_car.length) / 2 + 40)
                    for other_car in self.cars if not other_car.towed
                )
                if edge_clear:
                    self.cars.append(new_car)
                    self.spawn_timers[lane_index] = random.uniform(*level_settings["gap"])
                else:
                    self.spawn_timers[lane_index] = 0.3

        grandmothers = [
            person for person in self.people
            if person.alive and not person.saved and person.kind == "grandma"
            and ROAD_TOP - 20 < person.y < ROAD_BOTTOM + 20
        ] if not pre_warm else []

        active_road_cars = [car for car in self.cars if not car.towed]
        for car in self.cars:
            if car.towed:
                continue                                  # the drone moves it
            if car.wreck:
                car.wreck_time += delta_time
                if car.fuse > 0:
                    car.fuse -= delta_time
                    if random.random() < 0.6:            # leaking fuel sparks
                        self.particles.append(Particle(
                            car.x + random.uniform(-car.length / 3, car.length / 3),
                            car.y,
                            8,
                            random.uniform(-40, 40),
                            random.uniform(-20, 20),
                            random.uniform(60, 140),
                            random.choice([(255, 200, 60), (255, 120, 30)]),
                            2,
                            0.4
                        ))
                    if car.fuse <= 0:
                        car.burnt = True
                        car.color = (52, 48, 46)
                        self.explode(car.x, car.y, power=1.8)
                if random.random() < 0.25:
                    self.particles.append(Particle(
                        car.x + random.uniform(-car.length / 4, car.length / 4),
                        car.y,
                        car.height,
                        random.uniform(-6, 6),
                        0,
                        random.uniform(25, 45),
                        random.choice([(80, 80, 84), (110, 110, 114)]),
                        random.uniform(3, 6),
                        1.6,
                        gravity=-8
                    ))
                continue

            if car.skid > 0:
                # sliding sideways on blood: keeps going forward, drifts into the next lane
                car.skid -= delta_time
                car.speed *= (1 - 0.5 * delta_time)
                car.y = clamp(car.y + car.lateral_speed * delta_time, ROAD_TOP + car.width / 2 + 2, ROAD_BOTTOM - car.width / 2 - 2)
                wobble = math.sin(car.skid * 18) * 0.08
                # atan2(sideways_speed, forward_speed) turns the car toward its movement; sine adds skid wobble.
                car.heading = math.atan2(car.lateral_speed * 0.6, car.direction * max(car.speed, 1)) + wobble
                if car.skid <= 0:
                    car.lateral_speed = 0
                    # Bitwise XOR with 1 swaps paired lanes: 0 <-> 1 and 2 <-> 3. Choose the closer lane center.
                    # XOR ด้วย 1 ใช้สลับเลนคู่กัน เช่น 0 กับ 1 และ 2 กับ 3 แล้วเลือกเลนที่อยู่ใกล้กว่า
                    car.lane = min((car.lane, car.lane ^ 1), key=lambda lane_index: abs(lane_center(lane_index) - car.y))
            else:
                if car.stall > 0:
                    car.stall -= delta_time
                    target_speed = 0
                else:
                    target_speed = car.base_speed
                    if self.lane_freeze_timers[car.lane] > 0:
                        target_speed = 0
                    for grandmother in grandmothers:
                        if abs(car.x - grandmother.x) < 170 and abs(car.y - grandmother.y) < 75:
                            target_speed *= 0.35
                    gap = 1e9
                    ahead_car = None
                    for other_car in active_road_cars:
                        if other_car is car or not other_car.blocks(car.lane):
                            continue
                        # Multiply by direction so a positive distance always means ahead, even for left-moving cars.
                        distance_ahead = (other_car.x - car.x) * car.direction
                        if distance_ahead > 0:
                            # Front-to-back clearance = center distance - half the combined vehicle lengths.
                            gap_distance = distance_ahead - (other_car.length + car.length) / 2
                            if gap_distance < gap:
                                ahead_car, gap = other_car, gap_distance
                    if ahead_car:
                        # Braking formula d = v^2 / (2*a), using deceleration 480, plus a 16-unit safety margin.
                        # ระยะเบรกใช้สูตร v² / (2a): รถเร็วขึ้นสองเท่าจะต้องใช้ระยะเบรกสี่เท่า เมื่อความหน่วงเท่าเดิม
                        stop_distance = car.speed * car.speed / (2 * 480) + 16      # distance needed to stop
                        if gap < stop_distance + 30:
                            target_speed = min(target_speed, 0 if (gap < stop_distance or ahead_car.wreck) else ahead_car.speed * 0.9)
                # Approach target speed with a per-frame acceleration limit; braking is stronger than acceleration.
                speed_delta = target_speed - car.speed
                rate = 520 if speed_delta < 0 else 200
                car.speed += clamp(speed_delta, -rate * delta_time, rate * delta_time)
                # ease back into the lane and point straight again
                # Easing formula: current += (target - current) * fraction. Capping the fraction prevents overshoot.
                # นำระยะที่ยังห่างจากเป้าหมายมาคูณสัดส่วน แล้วบวกกลับเข้าตำแหน่งปัจจุบัน
                car.y += (lane_center(car.lane) - car.y) * min(1.0, 2.5 * delta_time)
                car.heading += (car.base_angle - car.heading) * min(1.0, 4 * delta_time)
            car.x += car.direction * car.speed * delta_time
            if (car.skid > 0 or (car.stall > 0 and car.speed > 30)) and not pre_warm:
                self.skid_marks(car)
            else:
                car.skid_points = None

            # slippery blood
            if car.skid <= 0 and car.speed > 40:
                for puddle in self.blood_puddles:
                    if id(car) in puddle.hit_car_identifiers:
                        continue
                    if math.hypot(car.x - puddle.x, car.y - puddle.y) < puddle.radius + car.width * 0.45:
                        puddle.hit_car_identifiers.add(id(car))
                        if puddle.radius < 20 and random.random() < 0.6:
                            continue              # small puddles only sometimes make a car slide
                        car.skid = 0.9
                        other_lane = car.lane ^ 1
                        # Sideways speed = distance to the paired lane / skid duration, with a small random multiplier.
                        car.lateral_speed = (lane_center(other_lane) - car.y) / 0.9 * random.uniform(0.8, 1.15)
                        self.float_text(car.x, car.y, "ลื่น!", ACCENT_COLOR)
                        if not pre_warm:
                            self.toast("รถลื่นคราบเลือด!", ACCENT_COLOR)
                        break

        # crashes between cars
        for first_index, first_car in enumerate(active_road_cars):
            # Compare each car pair once by taking only cars after the current index.
            # ตรวจรถแต่ละคู่ครั้งเดียว เช่น ตรวจคู่ A-B แล้วไม่ต้องตรวจ B-A ซ้ำ
            for second_car in active_road_cars[first_index + 1:]:
                if first_car.wreck and second_car.wreck:
                    continue
                if first_car.skid <= 0 and second_car.skid <= 0:
                    continue                      # normal traffic keeps its distance; only skids crash
                if (abs(first_car.x - second_car.x) < (first_car.length + second_car.length) / 2 - 6 and abs(first_car.y - second_car.y) < (first_car.width + second_car.width) / 2 - 4):
                    self.crash(first_car, second_car)

        for drone in self.drones:
            drone.update(delta_time)
        done_car_identifiers = {id(drone.car) for drone in self.drones if drone.done}
        self.drones = [drone for drone in self.drones if not drone.done]
        self.cars = [
            car for car in self.cars
            if id(car) not in done_car_identifiers and (car.wreck or car.towed or -car.length * 2 < car.x < SCREEN_WIDTH + car.length * 2)
        ]

    # Combine impact effects by taking the strongest active value, so weaker hits do not cancel stronger ones.
    def juice(self, shake_strength=0.0, hitstop_seconds=0.0, flash_intensity=0.0):
        self.active_surface_shake_strength = max(self.active_surface_shake_strength, shake_strength)
        self.hitstop_remaining = max(self.hitstop_remaining, hitstop_seconds)
        self.flash_intensity = max(self.flash_intensity, flash_intensity)

    def impact_text(self, world_x, world_y, text, color=ACCENT_COLOR, size=1.0):
        # Count nearby impact labels and shift the new one upward by 38 units per label to reduce overlap.
        stack = sum(1 for impact_message in self.impact_messages if abs(impact_message[0] - world_x) < 120 and abs(impact_message[1] - world_y) < 80)
        self.impact_messages.append([world_x, world_y, text, 0.9, color, size, random.uniform(-12, 12), stack * 38])

    # Particles spread outward with velocity components cos(angle)*speed and sin(angle)*speed.
    # The y component is compressed for the scene style; upward velocity makes debris arc.
    def debris(self, car, count=8):
        """Car parts flying off: body panels, glass and a wheel or two."""
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            speed_value = random.uniform(80, 260)
            particle_color = random.choice([car.color, shade(car.color, 0.7), (60, 62, 66)])
            self.particles.append(Particle(
                car.x,
                car.y,
                car.height * 0.6,
                math.cos(angle) * speed_value,
                math.sin(angle) * speed_value * 0.6,
                random.uniform(150, 320),
                particle_color,
                random.uniform(4, 7),
                random.uniform(1.6, 2.6),
                gravity=700,
                shape="chunk"
            ))
        for _ in range(random.randint(1, 2)):
            angle = random.uniform(0, math.tau)
            self.particles.append(Particle(
                car.x,
                car.y,
                10,
                math.cos(angle) * 200,
                math.sin(angle) * 120,
                260,
                (28, 28, 32),
                6,
                2.6,
                gravity=700,
                shape="wheel"
            ))
        for _ in range(10):
            angle = random.uniform(0, math.tau)
            speed_value = random.uniform(60, 200)
            self.particles.append(Particle(
                car.x,
                car.y,
                car.height * 0.8,
                math.cos(angle) * speed_value,
                math.sin(angle) * speed_value * 0.6,
                random.uniform(60, 180),
                random.choice([(180, 220, 240), (230, 245, 255)]),
                2,
                0.9
            ))

    # Join each wheel position to its previous-frame position to draw continuous tire trails.
    def skid_marks(self, car):
        points = [local(car.x, car.y, car.angle, -car.length * 0.32, local_y) for local_y in (-car.width / 2 + 3, car.width / 2 - 3)]
        if car.skid_points:
            for old_point, new_point in zip(car.skid_points, points):
                pygame.draw.line(self.skid_mark_surface, (22, 22, 26, 120), project(*old_point), project(*new_point), 4 if car.width > 30 else 2)
        car.skid_points = points

    def crash(self, *cars):
        # Crash center = average of the involved car centers; shared debris and messages appear here.
        mean_x = sum(car.x for car in cars) / len(cars)
        mean_y = sum(car.y for car in cars) / len(cars)
        for car in cars:
            if car.wreck or car.towed:
                continue
            car.wreck = True
            car.speed, car.skid, car.lateral_speed = 0, 0, 0
            car.heading += random.uniform(-0.3, 0.3)
            car.color = shade(car.color, 0.7)
            self.drones.append(Drone(car))
            self.debris(car)
            if car.kind == "icecream":
                for _ in range(4):                       # ice cream all over the road (slippery!)
                    goo_color = random.choice(ICECREAM_GOO)
                    self.blood_puddles.append(Puddle(
                        car.x + random.uniform(-50, 50),
                        car.y + random.uniform(-25, 25),
                        random.uniform(20, 28),
                        goo_color,
                        shade(goo_color, 1.15)
                    ))
                for _ in range(14):
                    angle = random.uniform(0, math.tau)
                    self.particles.append(Particle(
                        car.x,
                        car.y,
                        car.height + 20,
                        math.cos(angle) * 150,
                        math.sin(angle) * 90,
                        random.uniform(150, 280),
                        random.choice(ICECREAM_GOO),
                        random.uniform(4, 7),
                        1.4
                    ))
                self.impact_text(car.x, car.y - 20, "ไอติมเละ!", (250, 190, 212), 0.9)
            elif car.kind == "tanker":
                car.fuse = 0.9                              # leaking... about to blow
                self.impact_text(car.x, car.y - 20, "น้ำมันรั่ว!", BAD_COLOR, 0.9)
            elif car.kind in ("moto", "sidecar"):
                car.heading += random.uniform(0.6, 1.2) * random.choice([-1, 1])   # bike falls over
        self.juice(shake_strength=11, hitstop_seconds=0.09, flash_intensity=0.35)
        self.impact_text(mean_x, mean_y, "โครม!", ACCENT_COLOR, 1.2)
        for _ in range(26):
            angle = random.uniform(0, math.tau)
            speed_value = random.uniform(60, 220)
            self.particles.append(Particle(
                mean_x,
                mean_y,
                20,
                math.cos(angle) * speed_value,
                math.sin(angle) * speed_value * 0.6,
                random.uniform(80, 220),
                random.choice([(255, 220, 120), (200, 200, 205), (120, 170, 220), (60, 60, 64)]),
                random.uniform(2, 4),
                0.8
            ))
        self.toast("รถชนกัน! โดรนกำลังมายกออก", ACCENT_COLOR)

    def update_person(self, person, delta_time):
        if not person.alive or person.carried_by:
            return
        person.cooldown = max(0.0, person.cooldown - delta_time)
        person.sign_time = max(0.0, person.sign_time - delta_time)
        person.slip_immune = max(0.0, person.slip_immune - delta_time)
        if person.dash > 0:
            person.dash -= delta_time
            if person.dash <= 0:
                person.tired = 1.2
        elif person.tired > 0:
            person.tired -= delta_time
        if person.down_time > 0:
            person.down_time -= delta_time
        old_position = (person.x, person.y)

        if person.slip_time > 0:
            person.slip_time -= delta_time
            person.x = clamp(person.x + person.slip_velocity[0] * delta_time, 10, SCREEN_WIDTH - 10)
            person.y = clamp(person.y + person.slip_velocity[1] * delta_time, 16, WORLD_BOTTOM - 10)
            # Reduce sliding velocity by a time-scaled fraction to model friction.
            # ลดความเร็วลื่นลงทีละเฟรมเพื่อเลียนแบบแรงเสียดทาน
            person.slip_velocity = (person.slip_velocity[0] * (1 - 3 * delta_time), person.slip_velocity[1] * (1 - 3 * delta_time))
        elif person.down_time > 0:
            pass
        elif person.saved:
            self.step_towards(person, delta_time, person.speed() * 0.7)
        else:
            # the kid panics when nobody is close
            if person.kind == "kid":
                near = any(
                    other_person is not person and other_person.alive and math.hypot(other_person.x - person.x, other_person.y - person.y) < 75
                    for other_person in self.people
                )
                # Reset the timer when somebody is near; otherwise accumulate seconds until the child panics.
                person.alone_time = 0 if near else person.alone_time + delta_time
                if person.alone_time > 2.0 and not person.panic:
                    person.panic = True
                    self.toast("เด็กอยู่คนเดียว ตกใจเดินมั่ว!", BAD_COLOR)
                elif near and person.panic:
                    person.panic = False
                    person.path = []
            if person.panic:
                person.wander_time -= delta_time
                if person.wander_time <= 0:
                    wander_angle = random.uniform(0, math.tau)
                    # cos(angle), sin(angle) form a unit vector, giving a random direction without changing walking speed.
                    person.wander_direction = (math.cos(wander_angle), math.sin(wander_angle))
                    person.wander_time = random.uniform(0.4, 0.9)
                walk_speed = person.speed() * 0.6
                self.move_constrained(
                    person,
                    person.x + person.wander_direction[0] * walk_speed * delta_time,
                    person.y + person.wander_direction[1] * walk_speed * delta_time
                )
            else:
                if person.is_walking and not person.path:
                    self.plan_crossing(person)       # keep going after getting back up
                self.step_towards(person, delta_time, person.speed())

        person.moving = math.hypot(person.x - old_position[0], person.y - old_position[1]) > 0.05
        if person.moving:
            person.walk_phase += delta_time * (1.6 if person.dash > 0 else 1)
            if abs(person.x - old_position[0]) > 0.05:
                person.facing = 1 if person.x > old_position[0] else -1

        # slipping on blood
        if person.slip_time <= 0 and person.slip_immune <= 0 and person.moving and person.down_time <= 0:
            for puddle in self.blood_puddles:
                if math.hypot(person.x - puddle.x, person.y - puddle.y) < puddle.radius * 0.8:
                    delta_x, delta_y = person.x - old_position[0], person.y - old_position[1]
                    # Normalize the latest movement direction, then multiply by 190 to set slipping speed.
                    # Use 1 for a zero distance to avoid division by zero.
                    distance = math.hypot(delta_x, delta_y) or 1
                    person.slip_time = 0.45
                    person.slip_immune = 1.2
                    person.slip_velocity = (delta_x / distance * 190, delta_y / distance * 190)
                    person.path = []
                    self.float_text(person.x, person.y, "ลื่น!", ACCENT_COLOR)
                    break

        # walking through fire sets you alight
        if not person.saved:
            for fire in self.fires:
                if math.hypot(person.x - fire.x, (person.y - fire.y) * 1.3) < fire.radius * 0.7:
                    if person.burn_time <= 0:
                        self.toast(f"{person.information['name']}ติดไฟ!", BAD_COLOR)
                    person.burn_time = max(person.burn_time, 1.2)
                    break

        # reached the safe zone
        if not person.saved and person.y < GOAL_Y - 6:
            person.burn_time = 0
            self.save(person)

    def step_towards(self, person, delta_time, speed_value):
        if not person.path:
            return
        target_x, target_y = person.path[0]
        delta_x = target_x - person.x
        delta_y = target_y - person.y
        distance = math.hypot(delta_x, delta_y)
        # Maximum distance this frame = speed * seconds. Snap to nearby waypoints to avoid walking past them.
        step = speed_value * delta_time
        if distance <= step:
            self.move_constrained(person, target_x, target_y)
            person.path.pop(0)
        else:
            # Divide the target vector by its length to get direction, then multiply by this frame distance.
            # หารระยะในแต่ละแกนด้วยระยะรวมเพื่อหาทิศ แล้วคูณระยะที่เดินได้ในเฟรมนี้
            self.move_constrained(person, person.x + delta_x / distance * step, person.y + delta_y / distance * step)

    # Keep people inside world bounds and prevent road entry outside the zebra crossing.
    def move_constrained(self, person, next_x, next_y):
        next_x = clamp(next_x, 10, SCREEN_WIDTH - 10)
        next_y = clamp(next_y, 16, WORLD_BOTTOM - 10)
        if person.saved:
            person.x, person.y = next_x, min(next_y, GOAL_Y - 8)
            return
        if in_road(next_y):
            if not in_road(person.y) and not in_band(next_x):
                next_y = person.y                      # can't step off the curb outside the crossing
            elif in_road(person.y) and in_band(person.x):
                next_x = clamp(next_x, CROSSING_START_X + 4, CROSSING_END_X - 4)
        person.x, person.y = next_x, next_y

    def save(self, person):
        person.saved = True
        person.is_walking = False
        person.panic = False
        # Count saved people, then use modulo and floor division to arrange them in rows of six.
        saved_slot = sum(1 for other_person in self.people if other_person.saved)
        person.path = [(220 + (saved_slot % 6) * 100 + random.uniform(-10, 10), 40 + (saved_slot // 6) * 34)]
        self.float_text(person.x, person.y, "ปลอดภัย!", GOOD_COLOR)
        if person.carrying:
            carried_person = person.carrying
            person.carrying = None
            carried_person.carried_by = None
            carried_person.x, carried_person.y = person.x + 12, person.y
            self.save(carried_person)

    def check_hits(self):
        for car in self.cars:
            if not car.dangerous():
                continue
            for person in self.people:
                if (person.alive and not person.saved and person.carried_by is None and person.invulnerable_time <= 0
                        and car.hits(person.x, person.y, 7)):
                    self.car_hit(person, car)

    def car_hit(self, person, car):
        # Scale base hit damage by speed/180, limited to 0.5..1.4; skidding adds 10 extra damage.
        speed_factor = clamp(car.speed / 180, 0.5, 1.4)
        damage_amount = VEHICLES[car.kind]["damage"] * speed_factor + (10 if car.skid > 0 else 0)
        self.juice(shake_strength=5, hitstop_seconds=0.04)
        self.impact_text(person.x, person.y, "ปั้ก!", (255, 255, 255), 0.7)
        push_velocity = (car.direction * (140 + car.speed * 0.6), random.uniform(-70, 70))
        person.invulnerable_time = 1.6
        if car.skid <= 0:                      # the driver slams on the brakes
            car.speed *= 0.3
            car.stall = max(car.stall, 1.0)
        self.damage(person, damage_amount, "car", push_velocity)
        if person.fuel:                           # the fuel can bursts on impact
            person.fuel = False
            self.explode(person.x, person.y)

    def damage(self, person, amount, source, push_velocity=None):
        """source: 'car', 'fire' (explosion), 'burn' (on fire, per frame)."""
        if not person.alive or person.saved:
            return
        person.health -= amount
        if source != "burn":
            person.hurt_time = 0.4
            self.float_text(person.x, person.y, f"-{int(amount)}", BAD_COLOR)
            for _ in range(8):
                angle = random.uniform(0, math.tau)
                speed_value = random.uniform(30, 120)
                self.particles.append(Particle(
                    person.x,
                    person.y,
                    18,
                    math.cos(angle) * speed_value,
                    math.sin(angle) * speed_value * 0.6,
                    random.uniform(60, 160),
                    random.choice([BLOOD, BLOOD_HIGHLIGHT]),
                    random.uniform(2, 3),
                    0.8
                ))
        if source == "car":
            self.blood_puddles.append(Puddle(person.x, person.y, 15))
        if push_velocity:                              # knocked off your feet
            person.slip_time = 0.4
            person.slip_velocity = push_velocity
            person.slip_immune = 1.0
            person.down_time = 1.1
            person.fall_direction = 1 if push_velocity[0] >= 0 else -1
            person.path = []
            person.panic = False
            if person.carrying:
                carried_person = person.carrying
                person.carrying = None
                carried_person.carried_by = None
                carried_person.x = person.x + 14
                carried_person.y = person.y + 8
                carried_person.down_time = 1.0
                carried_person.fall_direction = person.fall_direction
        if person.health <= 0:
            self.die(person, source)
            return
        if source == "car":
            self.toast(f"{person.information['name']}โดนชน!  HP เหลือ {int(person.health)}", BAD_COLOR)
            if person.injured:
                self.float_text(person.x, person.y - 10, "บาดเจ็บหนัก", BAD_COLOR)

    def die(self, person, source):
        person.health = 0
        person.alive = False
        person.is_walking = False
        person.path = []
        person.burn_time = 0
        person.death_time = 0.0
        person.death_cause = "fire" if source in ("fire", "burn") else "car"
        if person.death_cause == "car":
            self.blood_puddles.append(Puddle(person.x, person.y, 26))
            self.toast(f"{person.information['name']}เสียชีวิต", BAD_COLOR)
        else:
            person.charring_level = 1.0
            self.toast(f"{person.information['name']}ถูกไฟคลอกเสียชีวิต", BAD_COLOR)
        if person.carrying:
            carried_person = person.carrying
            person.carrying = None
            carried_person.carried_by = None
            carried_person.x = person.x + 16
            carried_person.y = person.y + 10
        if person.carried_by:
            person.carried_by.carrying = None
            person.carried_by = None
        if person.fuel:
            person.fuel = False
            self.explode(person.x, person.y)

    def explode(self, world_x, world_y, power=1.0):
        is_big = power > 1.2
        self.toast("รถขนน้ำมันระเบิด!" if is_big else "ถังน้ำมันระเบิด!", BAD_COLOR)
        self.fires.append(Fire(world_x, world_y, 58 * power))
        self.juice(shake_strength=16 * power, hitstop_seconds=0.12 * power, flash_intensity=0.6 if is_big else 0.45)
        self.impact_text(world_x, world_y, "ตูม!!", (255, 150, 40), 1.3 * power)
        # Explosion power increases the damage radius, but the radius multiplier is capped at 1.35.
        blast_radius = 90 * min(power, 1.35)                     # people-damage radius (visuals stay big)
        for _ in range(int(60 * power)):
            angle = random.uniform(0, math.tau)
            speed_value = random.uniform(60, 320) * power
            self.particles.append(Particle(
                world_x,
                world_y,
                10,
                math.cos(angle) * speed_value,
                math.sin(angle) * speed_value * 0.6,
                random.uniform(100, 380),
                random.choice([(255, 210, 80), (255, 140, 30), (230, 70, 30), (90, 90, 90)]),
                random.uniform(3, 7),
                random.uniform(0.6, 1.3)
            ))
        for person in self.people:
            distance = math.hypot(person.x - world_x, person.y - world_y)
            if person.alive and not person.saved and distance < blast_radius and person.carried_by is None:
                line_distance = distance or 1
                # Normalize the direction away from the explosion and multiply by 320 for outward knockback.
                push_velocity = ((person.x - world_x) / line_distance * 320, (person.y - world_y) / line_distance * 320)
                person.burn_time = max(person.burn_time, 1.5)
                had_fuel = person.fuel
                person.fuel = False
                # Linear damage falloff: 50 at the center, approaching 10 at the edge of the blast radius.
                # ยิ่งไกลจากจุดระเบิดยิ่งเสียพลังชีวิตน้อย: กลางวงเสีย 50 และใกล้ขอบวงเสียประมาณ 10
                self.damage(person, 10 + 40 * (1 - distance / blast_radius), "fire", push_velocity)
                if had_fuel:
                    self.explode(person.x, person.y)
        for car in list(self.cars):
            if car.towed or car.wreck:
                continue
            distance = math.hypot(car.x - world_x, car.y - world_y)
            if distance < 80 * power:
                self.crash(car)
            elif distance < 140 * power and car.skid <= 0:
                car.skid = 0.6
                car.lateral_speed = (car.y - world_y) / (distance or 1) * 120

    def animate_person(self, person, delta_time):
        """Pose, hurt flash, burning and death animation (runs for alive and dead)."""
        person.hurt_time = max(0.0, person.hurt_time - delta_time)
        person.invulnerable_time = max(0.0, person.invulnerable_time - delta_time)
        if person.carried_by:
            body_x, body_y = person.carried_by.x, person.carried_by.y
        else:
            body_x, body_y = person.x, person.y
        if not person.alive:
            person.death_time += delta_time
            person.pose += (math.pi / 2 - person.pose) * min(1.0, delta_time * 6)
            if person.death_cause == "fire" and person.death_time < 3.5 and random.random() < 0.4:
                self.particles.append(Particle(
                    body_x + random.uniform(-12, 12),
                    body_y,
                    6,
                    random.uniform(-8, 8),
                    0,
                    random.uniform(20, 40),
                    (70, 70, 74),
                    random.uniform(3, 6),
                    1.4,
                    gravity=-10
                ))
            return
        is_lying = person.down_time > 0 or person.carried_by is not None
        # Body angles use radians: 0 is upright and pi/2 is lying down. Ease toward the target pose.
        target_pose = math.pi / 2 if is_lying else (0.22 if (person.dash > 0 or person.burn_time > 0) and person.moving else 0.0)
        person.pose += (target_pose - person.pose) * min(1.0, delta_time * (14 if is_lying else 6))
        if person.burn_time > 0 and not person.saved:
            person.burn_time -= delta_time
            person.charring_level = min(1.0, person.charring_level + delta_time * 0.2)
            if random.random() < 0.7:
                self.particles.append(Particle(
                    body_x + random.uniform(-7, 7),
                    body_y + random.uniform(-3, 3),
                    random.uniform(8, 30),
                    random.uniform(-10, 10),
                    0,
                    random.uniform(40, 80),
                    random.choice([(255, 150, 40), (255, 90, 30), (255, 220, 90)]),
                    random.uniform(2, 4),
                    0.45,
                    gravity=-30
                ))
            # Burn damage is 8 health per second; multiplying by delta_time makes damage follow simulated time.
            # ไฟลดพลังชีวิต 8 หน่วยต่อวินาที จึงคูณเวลาต่อเฟรมเพื่อให้ความเสียหายตรงกับเวลาในเกม
            self.damage(person, 8 * delta_time, "burn")
        elif person.injured and not person.saved:
            person.drip_time -= delta_time
            if person.drip_time <= 0:
                person.drip_time = random.uniform(0.3, 0.7)
                self.particles.append(Particle(
                    body_x + random.uniform(-4, 4),
                    body_y,
                    14,
                    0,
                    0,
                    0,
                    BLOOD,
                    2,
                    1.2
                ))

    def check_end(self):
        # Booleans count as 1 or 0 in sum. Lose when even all remaining survivors cannot reach the target.
        # Otherwise finish with a win once nobody is left to cross.
        # แพ้เมื่อจำนวนคนที่ยังช่วยได้รวมกับคนที่รอดไม่ถึงเป้าหมาย ชนะเมื่อไม่มีคนเหลือให้ข้ามและไม่เข้าเงื่อนไขแพ้
        saved_count = sum(person.saved for person in self.people)
        pending_count = sum(person.alive and not person.saved for person in self.people)
        target_count = self.current_level["target"]
        if saved_count + pending_count < target_count:
            self.state = "lose"
            self.end_screen_timer = 0
        elif pending_count == 0:
            self.state = "win"
            self.end_screen_timer = 0
