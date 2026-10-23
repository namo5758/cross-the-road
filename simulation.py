"""Simulation, collision, and outcome rules for Cross the Road.

GameSimulation mutates the Game state supplied by the coordinator. Rendering and
input stay out of this module so frame rules can be read top-to-bottom here.
"""

import math
import random

import pygame

from entities import Car, Drone, Fire, Particle, Puddle
from game_config import (ACCENT, BAD, BLOOD, BLOOD_HI, CW_X0, CW_X1, GOAL_Y,
                         GOOD, ICECREAM_GOO, LANES, ROAD_BOT, ROAD_TOP,
                         VEHICLES, W, WORLD_BOT)
from geometry import clamp, in_band, in_road, lane_center, local, mix, proj, shade


class GameSimulation:
    def update(self, dt):
        if self.state == "title" or self.paused:
            return
        if self.state == "play":
            self.elapsed_time += dt
        self.update_traffic(dt)
        for p in self.people:
            self.animate_person(p, dt)
        if self.state == "play":
            for p in self.people:
                self.update_person(p, dt)
            self.check_hits()
            self.check_end()
        else:
            self.end_screen_timer += dt
        for pd in self.blood_puddles:
            pd.life -= dt
        self.blood_puddles = [pd for pd in self.blood_puddles if pd.life > 0]
        for f in self.fires:
            f.life -= dt
            if random.random() < 0.6:
                a, r = random.uniform(0, math.tau), random.uniform(0, f.r * 0.8)
                self.particles.append(Particle(f.x + math.cos(a) * r, f.y + math.sin(a) * r * 0.6, 4,
                                               0, 0, random.uniform(40, 90),
                                               random.choice([(255, 150, 40), (255, 90, 30), (255, 210, 80)]),
                                               random.uniform(2, 4), 0.6, grav=-20))
        self.fires = [f for f in self.fires if f.life > 0]
        for q in self.particles:
            q.life -= dt
            q.x += q.vx * dt
            q.y += q.vy * dt
            q.z += q.vz * dt
            q.vz -= q.grav * dt
            q.ang += q.spin * dt
            if q.z < 0:
                if q.shape != "dot" and q.vz < -90:      # car parts bounce
                    q.z, q.vz = 0, -q.vz * 0.4
                    q.vx *= 0.6
                    q.vy *= 0.6
                    q.spin *= 0.6
                else:
                    q.z, q.vz = 0, 0
                    q.vx *= 0.5
                    q.vy *= 0.5
                    q.spin *= 0.5
        self.particles = [q for q in self.particles if q.life > 0]
        self.active_surface_shake_strength = max(0.0, self.active_surface_shake_strength - 45 * dt)
        self.flash_intensity = max(0.0, self.flash_intensity - 3 * dt)
        for im in self.impact_messages:
            im[3] -= dt
        self.impact_messages = [im for im in self.impact_messages if im[3] > 0]
        self.skid_mark_fade_timer += dt
        if self.skid_mark_fade_timer > 0.5:                      # skid marks slowly fade away
            self.skid_mark_fade_timer = 0
            self.skid_mark_surface.fill((255, 255, 255, 246), special_flags=pygame.BLEND_RGBA_MULT)
        for fl in self.floating_messages:
            fl[4] -= dt
            if fl[3]:
                fl[2] += 30 * dt
        self.floating_messages = [fl for fl in self.floating_messages if fl[4] > 0]
        for t in self.toast_messages:
            t[1] -= dt
        self.toast_messages = [t for t in self.toast_messages if t[1] > 0]

    def update_traffic(self, dt, prewarm=False):
        level_settings = self.current_level
        for i in range(LANES):
            self.lane_freeze_timers[i] = max(0.0, self.lane_freeze_timers[i] - dt)
            self.spawn_timers[i] -= dt
            if self.spawn_timers[i] <= 0:
                kind = random.choices(list(level_settings["mix"]), weights=list(level_settings["mix"].values()))[0]
                c = Car(i, kind, level_settings)
                edge_clear = all(not (o.blocks(i) and abs(o.x - c.x) < (o.length + c.length) / 2 + 40)
                                 for o in self.cars if not o.towed)
                if edge_clear:
                    self.cars.append(c)
                    self.spawn_timers[i] = random.uniform(*level_settings["gap"])
                else:
                    self.spawn_timers[i] = 0.3
        grandmas = [p for p in self.people if p.alive and not p.saved and p.kind == "grandma"
                    and ROAD_TOP - 20 < p.y < ROAD_BOT + 20] if not prewarm else []
        road = [o for o in self.cars if not o.towed]
        for c in self.cars:
            if c.towed:
                continue                                  # the drone moves it
            if c.wreck:
                c.wreck_t += dt
                if c.fuse > 0:
                    c.fuse -= dt
                    if random.random() < 0.6:            # leaking fuel sparks
                        self.particles.append(Particle(c.x + random.uniform(-c.length / 3, c.length / 3), c.y, 8,
                                                       random.uniform(-40, 40), random.uniform(-20, 20),
                                                       random.uniform(60, 140), random.choice([(255, 200, 60), (255, 120, 30)]),
                                                       2, 0.4))
                    if c.fuse <= 0:
                        c.burnt = True
                        c.col = (52, 48, 46)
                        self.explode(c.x, c.y, power=1.8)
                if random.random() < 0.25:
                    self.particles.append(Particle(c.x + random.uniform(-c.length / 4, c.length / 4), c.y, c.height,
                                                   random.uniform(-6, 6), 0, random.uniform(25, 45),
                                                   random.choice([(80, 80, 84), (110, 110, 114)]),
                                                   random.uniform(3, 6), 1.6, grav=-8))
                continue
            if c.skid > 0:
                # sliding sideways on blood: keeps going forward, drifts into the next lane
                c.skid -= dt
                c.speed *= (1 - 0.5 * dt)
                c.y = clamp(c.y + c.lateral_speed * dt, ROAD_TOP + c.width / 2 + 2, ROAD_BOT - c.width / 2 - 2)
                wobble = math.sin(c.skid * 18) * 0.08
                c.heading = math.atan2(c.lateral_speed * 0.6, c.dir * max(c.speed, 1)) + wobble
                if c.skid <= 0:
                    c.lateral_speed = 0
                    c.lane = min((c.lane, c.lane ^ 1), key=lambda L: abs(lane_center(L) - c.y))
            else:
                if c.stall > 0:
                    c.stall -= dt
                    target = 0
                else:
                    target = c.base_speed
                    if self.lane_freeze_timers[c.lane] > 0:
                        target = 0
                    for g in grandmas:
                        if abs(c.x - g.x) < 170 and abs(c.y - g.y) < 75:
                            target *= 0.35
                    gap = 1e9
                    ahead = None
                    for o in road:
                        if o is c or not o.blocks(c.lane):
                            continue
                        d = (o.x - c.x) * c.dir
                        if d > 0:
                            g_ = d - (o.length + c.length) / 2
                            if g_ < gap:
                                ahead, gap = o, g_
                    if ahead:
                        stop_dist = c.speed * c.speed / (2 * 480) + 16      # distance needed to stop
                        if gap < stop_dist + 30:
                            target = min(target, 0 if (gap < stop_dist or ahead.wreck) else ahead.speed * 0.9)
                dv = target - c.speed
                rate = 520 if dv < 0 else 200
                c.speed += clamp(dv, -rate * dt, rate * dt)
                # ease back into the lane and point straight again
                c.y += (lane_center(c.lane) - c.y) * min(1.0, 2.5 * dt)
                c.heading += (c.base_ang - c.heading) * min(1.0, 4 * dt)
            c.x += c.dir * c.speed * dt
            if (c.skid > 0 or (c.stall > 0 and c.speed > 30)) and not prewarm:
                self.skid_marks(c)
            else:
                c.skid_points = None
            # slippery blood
            if c.skid <= 0 and c.speed > 40:
                for pd in self.blood_puddles:
                    if id(c) in pd.hit:
                        continue
                    if math.hypot(c.x - pd.x, c.y - pd.y) < pd.r + c.width * 0.45:
                        pd.hit.add(id(c))
                        if pd.r < 20 and random.random() < 0.6:
                            continue              # small puddles only sometimes make a car slide
                        c.skid = 0.9
                        other = c.lane ^ 1
                        c.lateral_speed = (lane_center(other) - c.y) / 0.9 * random.uniform(0.8, 1.15)
                        self.float_text(c.x, c.y, "ลื่น!", ACCENT)
                        if not prewarm:
                            self.toast("รถลื่นคราบเลือด!", ACCENT)
                        break
        # crashes between cars
        for i, a in enumerate(road):
            for b in road[i + 1:]:
                if a.wreck and b.wreck:
                    continue
                if a.skid <= 0 and b.skid <= 0:
                    continue                      # normal traffic keeps its distance; only skids crash
                if (abs(a.x - b.x) < (a.length + b.length) / 2 - 6 and abs(a.y - b.y) < (a.width + b.width) / 2 - 4):
                    self.crash(a, b)
        for d in self.drones:
            d.update(dt)
        gone = {id(d.car) for d in self.drones if d.done}
        self.drones = [d for d in self.drones if not d.done]
        self.cars = [c for c in self.cars if id(c) not in gone and (c.wreck or c.towed or -c.length * 2 < c.x < W + c.length * 2)]

    def juice(self, shake=0.0, hitstop=0.0, flash=0.0):
        self.active_surface_shake_strength = max(self.active_surface_shake_strength, shake)
        self.hitstop_remaining = max(self.hitstop_remaining, hitstop)
        self.flash_intensity = max(self.flash_intensity, flash)

    def impact_text(self, x, y, text, col=ACCENT, size=1.0):
        stack = sum(1 for im in self.impact_messages if abs(im[0] - x) < 120 and abs(im[1] - y) < 80)
        self.impact_messages.append([x, y, text, 0.9, col, size, random.uniform(-12, 12), stack * 38])

    def debris(self, c, n=8):
        """Car parts flying off: body panels, glass and a wheel or two."""
        for i in range(n):
            a = random.uniform(0, math.tau)
            sp = random.uniform(80, 260)
            col = random.choice([c.col, shade(c.col, 0.7), (60, 62, 66)])
            self.particles.append(Particle(c.x, c.y, c.height * 0.6, math.cos(a) * sp, math.sin(a) * sp * 0.6,
                                           random.uniform(150, 320), col, random.uniform(4, 7),
                                           random.uniform(1.6, 2.6), grav=700, shape="chunk"))
        for _ in range(random.randint(1, 2)):
            a = random.uniform(0, math.tau)
            self.particles.append(Particle(c.x, c.y, 10, math.cos(a) * 200, math.sin(a) * 120, 260,
                                           (28, 28, 32), 6, 2.6, grav=700, shape="wheel"))
        for _ in range(10):
            a = random.uniform(0, math.tau)
            sp = random.uniform(60, 200)
            self.particles.append(Particle(c.x, c.y, c.height * 0.8, math.cos(a) * sp, math.sin(a) * sp * 0.6,
                                           random.uniform(60, 180), random.choice([(180, 220, 240), (230, 245, 255)]),
                                           2, 0.9))

    def skid_marks(self, c):
        pts = [local(c.x, c.y, c.ang, -c.length * 0.32, ly) for ly in (-c.width / 2 + 3, c.width / 2 - 3)]
        if c.skid_points:
            for a, b in zip(c.skid_points, pts):
                pygame.draw.line(self.skid_mark_surface, (22, 22, 26, 120), proj(*a), proj(*b), 4 if c.width > 30 else 2)
        c.skid_points = pts

    def crash(self, *cars):
        mx = sum(c.x for c in cars) / len(cars)
        my = sum(c.y for c in cars) / len(cars)
        for c in cars:
            if c.wreck or c.towed:
                continue
            c.wreck = True
            c.speed, c.skid, c.lateral_speed = 0, 0, 0
            c.heading += random.uniform(-0.3, 0.3)
            c.col = shade(c.col, 0.7)
            self.drones.append(Drone(c))
            self.debris(c)
            if c.kind == "icecream":
                for _ in range(4):                       # ice cream all over the road (slippery!)
                    col = random.choice(ICECREAM_GOO)
                    self.blood_puddles.append(Puddle(c.x + random.uniform(-50, 50), c.y + random.uniform(-25, 25),
                                               random.uniform(20, 28), col, shade(col, 1.15)))
                for _ in range(14):
                    a = random.uniform(0, math.tau)
                    self.particles.append(Particle(c.x, c.y, c.height + 20, math.cos(a) * 150, math.sin(a) * 90,
                                                   random.uniform(150, 280), random.choice(ICECREAM_GOO),
                                                   random.uniform(4, 7), 1.4))
                self.impact_text(c.x, c.y - 20, "ไอติมเละ!", (250, 190, 212), 0.9)
            elif c.kind == "tanker":
                c.fuse = 0.9                              # leaking... about to blow
                self.impact_text(c.x, c.y - 20, "น้ำมันรั่ว!", BAD, 0.9)
            elif c.kind in ("moto", "sidecar"):
                c.heading += random.uniform(0.6, 1.2) * random.choice([-1, 1])   # bike falls over
        self.juice(shake=11, hitstop=0.09, flash=0.35)
        self.impact_text(mx, my, "โครม!", ACCENT, 1.2)
        for _ in range(26):
            a = random.uniform(0, math.tau)
            sp = random.uniform(60, 220)
            self.particles.append(Particle(mx, my, 20, math.cos(a) * sp, math.sin(a) * sp * 0.6,
                                           random.uniform(80, 220),
                                           random.choice([(255, 220, 120), (200, 200, 205), (120, 170, 220), (60, 60, 64)]),
                                           random.uniform(2, 4), 0.8))
        self.toast("รถชนกัน! โดรนกำลังมายกออก", ACCENT)

    def update_person(self, p, dt):
        if not p.alive or p.carried_by:
            return
        p.cd = max(0.0, p.cd - dt)
        p.sign_t = max(0.0, p.sign_t - dt)
        p.slip_immune = max(0.0, p.slip_immune - dt)
        if p.dash > 0:
            p.dash -= dt
            if p.dash <= 0:
                p.tired = 1.2
        elif p.tired > 0:
            p.tired -= dt
        if p.down_t > 0:
            p.down_t -= dt
        old = (p.x, p.y)
        if p.slip_t > 0:
            p.slip_t -= dt
            p.x = clamp(p.x + p.slip_v[0] * dt, 10, W - 10)
            p.y = clamp(p.y + p.slip_v[1] * dt, 16, WORLD_BOT - 10)
            p.slip_v = (p.slip_v[0] * (1 - 3 * dt), p.slip_v[1] * (1 - 3 * dt))
        elif p.down_t > 0:
            pass
        elif p.saved:
            self.step_towards(p, dt, p.speed() * 0.7)
        else:
            # the kid panics when nobody is close
            if p.kind == "kid":
                near = any(q is not p and q.alive and math.hypot(q.x - p.x, q.y - p.y) < 75 for q in self.people)
                p.alone_t = 0 if near else p.alone_t + dt
                if p.alone_t > 2.0 and not p.panic:
                    p.panic = True
                    self.toast("เด็กอยู่คนเดียว ตกใจเดินมั่ว!", BAD)
                elif near and p.panic:
                    p.panic = False
                    p.path = []
            if p.panic:
                p.wander_t -= dt
                if p.wander_t <= 0:
                    a = random.uniform(0, math.tau)
                    p.wander = (math.cos(a), math.sin(a))
                    p.wander_t = random.uniform(0.4, 0.9)
                s = p.speed() * 0.6
                self.move_constrained(p, p.x + p.wander[0] * s * dt, p.y + p.wander[1] * s * dt)
            else:
                if p.go and not p.path:
                    self.plan_crossing(p)       # keep going after getting back up
                self.step_towards(p, dt, p.speed())
        p.moving = math.hypot(p.x - old[0], p.y - old[1]) > 0.05
        if p.moving:
            p.walk += dt * (1.6 if p.dash > 0 else 1)
            if abs(p.x - old[0]) > 0.05:
                p.facing = 1 if p.x > old[0] else -1
        # slipping on blood
        if p.slip_t <= 0 and p.slip_immune <= 0 and p.moving and p.down_t <= 0:
            for pd in self.blood_puddles:
                if math.hypot(p.x - pd.x, p.y - pd.y) < pd.r * 0.8:
                    dx, dy = p.x - old[0], p.y - old[1]
                    ln = math.hypot(dx, dy) or 1
                    p.slip_t = 0.45
                    p.slip_immune = 1.2
                    p.slip_v = (dx / ln * 190, dy / ln * 190)
                    p.path = []
                    self.float_text(p.x, p.y, "ลื่น!", ACCENT)
                    break
        # walking through fire sets you alight
        if not p.saved:
            for f in self.fires:
                if math.hypot(p.x - f.x, (p.y - f.y) * 1.3) < f.r * 0.7:
                    if p.burn_t <= 0:
                        self.toast(f"{p.info['name']}ติดไฟ!", BAD)
                    p.burn_t = max(p.burn_t, 1.2)
                    break
        # reached the safe zone
        if not p.saved and p.y < GOAL_Y - 6:
            p.burn_t = 0
            self.save(p)

    def step_towards(self, p, dt, speed):
        if not p.path:
            return
        tx, ty = p.path[0]
        dx, dy = tx - p.x, ty - p.y
        d = math.hypot(dx, dy)
        step = speed * dt
        if d <= step:
            self.move_constrained(p, tx, ty)
            p.path.pop(0)
        else:
            self.move_constrained(p, p.x + dx / d * step, p.y + dy / d * step)

    def move_constrained(self, p, nx, ny):
        nx = clamp(nx, 10, W - 10)
        ny = clamp(ny, 16, WORLD_BOT - 10)
        if p.saved:
            p.x, p.y = nx, min(ny, GOAL_Y - 8)
            return
        if in_road(ny):
            if not in_road(p.y) and not in_band(nx):
                ny = p.y                      # can't step off the curb outside the crossing
            elif in_road(p.y) and in_band(p.x):
                nx = clamp(nx, CW_X0 + 4, CW_X1 - 4)
        p.x, p.y = nx, ny

    def save(self, p):
        p.saved = True
        p.go = False
        p.go = False
        p.panic = False
        slot = sum(1 for q in self.people if q.saved)
        p.path = [(220 + (slot % 6) * 100 + random.uniform(-10, 10), 40 + (slot // 6) * 34)]
        self.float_text(p.x, p.y, "ปลอดภัย!", GOOD)
        if p.carrying:
            c = p.carrying
            p.carrying = None
            c.carried_by = None
            c.x, c.y = p.x + 12, p.y
            self.save(c)

    def check_hits(self):
        for c in self.cars:
            if not c.dangerous():
                continue
            for p in self.people:
                if (p.alive and not p.saved and p.carried_by is None and p.invuln <= 0
                        and c.hits(p.x, p.y, 7)):
                    self.car_hit(p, c)

    def car_hit(self, p, c):
        speed_f = clamp(c.speed / 180, 0.5, 1.4)
        dmg = VEHICLES[c.kind]["dmg"] * speed_f + (10 if c.skid > 0 else 0)
        self.juice(shake=5, hitstop=0.04)
        self.impact_text(p.x, p.y, "ปั้ก!", (255, 255, 255), 0.7)
        push = (c.dir * (140 + c.speed * 0.6), random.uniform(-70, 70))
        p.invuln = 1.6
        if c.skid <= 0:                      # the driver slams on the brakes
            c.speed *= 0.3
            c.stall = max(c.stall, 1.0)
        self.damage(p, dmg, "car", push)
        if p.fuel:                           # the fuel can bursts on impact
            p.fuel = False
            self.explode(p.x, p.y)

    def damage(self, p, amount, source, push=None):
        """source: 'car', 'fire' (explosion), 'burn' (on fire, per frame)."""
        if not p.alive or p.saved:
            return
        p.hp -= amount
        if source != "burn":
            p.hurt_t = 0.4
            self.float_text(p.x, p.y, f"-{int(amount)}", BAD)
            for _ in range(8):
                a = random.uniform(0, math.tau)
                sp = random.uniform(30, 120)
                self.particles.append(Particle(p.x, p.y, 18, math.cos(a) * sp, math.sin(a) * sp * 0.6,
                                               random.uniform(60, 160), random.choice([BLOOD, BLOOD_HI]),
                                               random.uniform(2, 3), 0.8))
        if source == "car":
            self.blood_puddles.append(Puddle(p.x, p.y, 15))
        if push:                              # knocked off your feet
            p.slip_t, p.slip_v = 0.4, push
            p.slip_immune = 1.0
            p.down_t = 1.1
            p.fall_dir = 1 if push[0] >= 0 else -1
            p.path = []
            p.panic = False
            if p.carrying:
                c = p.carrying
                p.carrying = None
                c.carried_by = None
                c.x, c.y = p.x + 14, p.y + 8
                c.down_t, c.fall_dir = 1.0, p.fall_dir
        if p.hp <= 0:
            self.die(p, source)
            return
        if source == "car":
            self.toast(f"{p.info['name']}โดนชน!  HP เหลือ {int(p.hp)}", BAD)
            if p.injured:
                self.float_text(p.x, p.y - 10, "บาดเจ็บหนัก", BAD)

    def die(self, p, source):
        p.hp = 0
        p.alive = False
        p.go = False
        p.path = []
        p.burn_t = 0
        p.death_t = 0.0
        p.death_kind = "fire" if source in ("fire", "burn") else "car"
        if p.death_kind == "car":
            self.blood_puddles.append(Puddle(p.x, p.y, 26))
            self.toast(f"{p.info['name']}เสียชีวิต", BAD)
        else:
            p.char = 1.0
            self.toast(f"{p.info['name']}ถูกไฟคลอกเสียชีวิต", BAD)
        if p.carrying:
            c = p.carrying
            p.carrying = None
            c.carried_by = None
            c.x, c.y = p.x + 16, p.y + 10
        if p.carried_by:
            p.carried_by.carrying = None
            p.carried_by = None
        if p.fuel:
            p.fuel = False
            self.explode(p.x, p.y)

    def explode(self, x, y, power=1.0):
        big = power > 1.2
        self.toast("รถขนน้ำมันระเบิด!" if big else "ถังน้ำมันระเบิด!", BAD)
        self.fires.append(Fire(x, y, 58 * power))
        self.juice(shake=16 * power, hitstop=0.12 * power, flash=0.6 if big else 0.45)
        self.impact_text(x, y, "ตูม!!", (255, 150, 40), 1.3 * power)
        R = 90 * min(power, 1.35)                     # people-damage radius (visuals stay big)
        for _ in range(int(60 * power)):
            a = random.uniform(0, math.tau)
            sp = random.uniform(60, 320) * power
            self.particles.append(Particle(x, y, 10, math.cos(a) * sp, math.sin(a) * sp * 0.6,
                                           random.uniform(100, 380),
                                           random.choice([(255, 210, 80), (255, 140, 30), (230, 70, 30), (90, 90, 90)]),
                                           random.uniform(3, 7), random.uniform(0.6, 1.3)))
        for q in self.people:
            d = math.hypot(q.x - x, q.y - y)
            if q.alive and not q.saved and d < R and q.carried_by is None:
                ln = d or 1
                push = ((q.x - x) / ln * 320, (q.y - y) / ln * 320)
                q.burn_t = max(q.burn_t, 1.5)
                chain = q.fuel
                q.fuel = False
                self.damage(q, 10 + 40 * (1 - d / R), "fire", push)
                if chain:
                    self.explode(q.x, q.y)
        for c in list(self.cars):
            if c.towed or c.wreck:
                continue
            d = math.hypot(c.x - x, c.y - y)
            if d < 80 * power:
                self.crash(c)
            elif d < 140 * power and c.skid <= 0:
                c.skid = 0.6
                c.lateral_speed = (c.y - y) / (d or 1) * 120

    def animate_person(self, p, dt):
        """Pose, hurt flash, burning and death animation (runs for alive and dead)."""
        p.hurt_t = max(0.0, p.hurt_t - dt)
        p.invuln = max(0.0, p.invuln - dt)
        bx, by = (p.carried_by.x, p.carried_by.y) if p.carried_by else (p.x, p.y)
        if not p.alive:
            p.death_t += dt
            p.pose += (math.pi / 2 - p.pose) * min(1.0, dt * 6)
            if p.death_kind == "fire" and p.death_t < 3.5 and random.random() < 0.4:
                self.particles.append(Particle(bx + random.uniform(-12, 12), by, 6, random.uniform(-8, 8), 0,
                                               random.uniform(20, 40), (70, 70, 74), random.uniform(3, 6),
                                               1.4, grav=-10))
            return
        lying = p.down_t > 0 or p.carried_by is not None
        target = math.pi / 2 if lying else (0.22 if (p.dash > 0 or p.burn_t > 0) and p.moving else 0.0)
        p.pose += (target - p.pose) * min(1.0, dt * (14 if lying else 6))
        if p.burn_t > 0 and not p.saved:
            p.burn_t -= dt
            p.char = min(1.0, p.char + dt * 0.2)
            if random.random() < 0.7:
                self.particles.append(Particle(bx + random.uniform(-7, 7), by + random.uniform(-3, 3),
                                               random.uniform(8, 30), random.uniform(-10, 10), 0,
                                               random.uniform(40, 80),
                                               random.choice([(255, 150, 40), (255, 90, 30), (255, 220, 90)]),
                                               random.uniform(2, 4), 0.45, grav=-30))
            self.damage(p, 8 * dt, "burn")
        elif p.injured and not p.saved:
            p.drip_t -= dt
            if p.drip_t <= 0:
                p.drip_t = random.uniform(0.3, 0.7)
                self.particles.append(Particle(bx + random.uniform(-4, 4), by, 14, 0, 0, 0,
                                               BLOOD, 2, 1.2))

    def check_end(self):
        saved = sum(p.saved for p in self.people)
        pending = sum(p.alive and not p.saved for p in self.people)
        target = self.current_level["target"]
        if saved + pending < target:
            self.state = "lose"
            self.end_screen_timer = 0
        elif pending == 0:
            self.state = "win"
            self.end_screen_timer = 0


