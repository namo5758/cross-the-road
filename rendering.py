"""Pygame presentation layer for Cross the Road.

GameRenderer reads the Game instance's state and draws it. It deliberately does
not advance simulation state or handle player input.
"""

import math
import random

import pygame

from fonts import load_font
from game_config import (ACCENT, BAD, BG, BLOOD_HI, GLASS, GOOD, H, HUD_Y, K,
                         LANE_H, MUTED, PANEL, PANEL_2, ROAD_TOP, SKIN, TEXT,
                         W, WHITE)
from geometry import box_corners, draw_box, local, mix, proj, shade


class GameRenderer:
    # ------------------------------------------------------------ drawing
    def draw(self):
        self.active_surface = s = self.world_canvas
        s.blit(self.ground_surface, (0, 0))
        s.blit(self.skid_mark_surface, (0, 0))
        self.draw_decals()
        s.blit(self.decal_surface, (0, 0))
        self.draw_frozen_lanes()

        items = []
        for c in self.cars:
            if not c.towed:
                items.append((c.depth(), 0, c))
        mx, my = pygame.mouse.get_pos()
        self.hover = self.person_at(mx, my) if self.state == "play" and my < HUD_Y else None
        for p in self.people:
            if p.alive and p.carried_by is None:
                items.append((p.y, 1, p))
            elif not p.alive and p.death_t < 10:
                items.append((p.y - 0.5, 1, p))
        for f in self.fires:
            items.append((f.y + 1, 2, f))
        items.sort(key=lambda it: it[0])
        for _, kind, obj in items:
            if kind == 0:
                self.draw_car(obj)
            elif kind == 1:
                self.draw_person(obj)
                if obj.carrying:
                    self.draw_person(obj.carrying, carried_on=obj)
            else:
                self.draw_fire(obj)
        for c in self.cars:
            if c.towed:
                self.draw_car(c)
        for d in sorted(self.drones, key=lambda d: d.y):
            self.draw_drone(d)
        for q in self.particles:
            a = q.life / q.max_life
            px, py = proj(q.x, q.y, q.z)
            if q.shape == "chunk":
                w, h = q.size, q.size * 0.6
                ca, sa = math.cos(q.ang), math.sin(q.ang)
                pts = [(px + dx * ca - dy * sa, py + dx * sa + dy * ca) for dx, dy in ((-w, -h), (w, -h), (w, h), (-w, h))]
                pygame.draw.polygon(s, q.col, pts)
                pygame.draw.polygon(s, shade(q.col, 0.5), pts, 1)
            elif q.shape == "wheel":
                pygame.draw.circle(s, q.col, (px, py), q.size)
                pygame.draw.circle(s, (150, 150, 156), (px + math.cos(q.ang) * 2, py + math.sin(q.ang) * 2), 2)
            else:
                pygame.draw.circle(s, q.col, (px, py), max(1, int(q.size * (0.5 + a * 0.5))))
        self.draw_floaters()
        self.draw_impacts()
        if self.flash_intensity > 0:
            self.flash_surface.fill((255, 250, 235, int(170 * self.flash_intensity)))
            s.blit(self.flash_surface, (0, 0))
        # shake the world, keep the HUD still
        self.active_surface = self.display_surface
        ox = oy = 0
        if self.active_surface_shake_strength > 0.5:
            ox = random.uniform(-self.active_surface_shake_strength, self.active_surface_shake_strength)
            oy = random.uniform(-self.active_surface_shake_strength, self.active_surface_shake_strength) * 0.7
        self.display_surface.fill(BG)
        self.display_surface.blit(self.world_canvas, (ox, oy), (0, 0, W, HUD_Y))
        s = self.display_surface
        self.draw_toasts()
        self.draw_hud()
        if self.state == "title":
            self.draw_title()
        elif self.state in ("win", "lose"):
            self.draw_end()
        elif self.paused:
            self.center_card(["หยุดชั่วคราว", "กด P เพื่อเล่นต่อ"])
        pygame.display.flip()

    def draw_decals(self):
        d = self.decal_surface
        d.fill((0, 0, 0, 0))
        for pd in self.blood_puddles:
            a = int(220 * min(1.0, pd.life / 3.0))
            for ox, oy, r in pd.blobs:
                cx, cy = proj(pd.x + ox, pd.y + oy)
                pygame.draw.ellipse(d, (*pd.col, a), (cx - r, cy - r * K, r * 2, r * 2 * K))
            cx, cy = proj(pd.x - pd.r * 0.2, pd.y - pd.r * 0.2)
            pygame.draw.ellipse(d, (*pd.hi, a // 2), (cx - 6, cy - 3, 12, 5))
        for f in self.fires:
            cx, cy = proj(f.x, f.y)
            pygame.draw.ellipse(d, (20, 16, 14, 170), (cx - f.r, cy - f.r * K * 0.75, f.r * 2, f.r * 2 * K * 0.75))
        for c in self.cars:
            pts = box_corners(c.x + 5, c.y + 7, c.length, c.width, c.ang)
            pygame.draw.polygon(d, (0, 0, 0, 70 if c.lift < 5 else 40), [proj(*pt) for pt in pts])
        for dr in self.drones:
            cx, cy = proj(dr.x, dr.y)
            pygame.draw.ellipse(d, (0, 0, 0, 50), (cx - 26, cy - 9, 52, 18))
        hover = getattr(self, "hover", None)
        for p in self.people:
            if not p.alive or p.carried_by:
                continue
            cx, cy = proj(p.x + 2, p.y + 2)
            pygame.draw.ellipse(d, (0, 0, 0, 80), (cx - 10, cy - 4, 20, 8))
            cx, cy = proj(p.x, p.y)
            if p is hover:
                pygame.draw.ellipse(d, (255, 255, 255, 200), (cx - 16, cy - 8, 32, 16), 2)
            if p.go and not p.saved:
                pygame.draw.ellipse(d, (*GOOD, 200), (cx - 13, cy - 6, 26, 12), 2)

    def draw_frozen_lanes(self):
        o = self.overlay_surface
        o.fill((0, 0, 0, 0))
        any_frozen = False
        for i, t in enumerate(self.lane_freeze_timers):
            if t <= 0:
                continue
            any_frozen = True
            y0, y1 = ROAD_TOP + LANE_H * i, ROAD_TOP + LANE_H * (i + 1)
            a = int(60 * min(1.0, t))
            pygame.draw.polygon(o, (230, 60, 50, a), [proj(0, y0), proj(W, y0), proj(W, y1), proj(0, y1)])
        if any_frozen:
            self.active_surface.blit(o, (0, 0))

    def draw_car(self, c):
        s = self.active_surface
        a = c.ang
        z = c.lift                                   # > 0 while a drone carries it
        glass = (40, 46, 52) if c.wreck else GLASS
        near = 1 if c.dir > 0 else -1          # local side that faces the camera
        if c.kind == "sidecar":
            # มอเตอร์ไซค์พ่วงข้าง: bike on one side, a tub with its own wheel on the other
            tx, ty = local(c.x, c.y, a, -2, 9 * near)
            draw_box(s, tx, ty, 14, 6, z, z + 9, a, (26, 26, 30), outline=False)          # tub wheel
            draw_box(s, tx, ty, 32, 18, z + 6, z + 17, a, c.col)                          # tub
            pygame.draw.polygon(s, shade(c.col, 1.25), [proj(*local(c.x, c.y, a, 12, 9 * near + d), z + 17) for d in (-9, 9)] + [proj(*local(c.x, c.y, a, 18, 9 * near), z + 21)])
            if not c.wreck:
                if c.cargo == "passenger":
                    px_, py_ = local(c.x, c.y, a, -4, 9 * near)
                    draw_box(s, px_, py_, 9, 9, z + 17, z + 28, a, (210, 120, 60))
                    pygame.draw.circle(s, SKIN, proj(px_, py_, z + 33), 5)
                elif c.cargo == "crates":
                    for i, ox in enumerate((-8, 4)):
                        cx_, cy_ = local(c.x, c.y, a, ox, 9 * near)
                        draw_box(s, cx_, cy_, 10, 12, z + 17, z + 26 + i * 4, a, (176, 130, 76))
                else:
                    for ox in (-10, -4, 2, 8):
                        bx_, by_ = local(c.x, c.y, a, ox, 9 * near)
                        draw_box(s, bx_, by_, 4, 4, z + 17, z + 29, a, (90, 170, 110), outline=False)
            bx_, by_ = local(c.x, c.y, a, 0, -9 * near)
            draw_box(s, bx_, by_, 38, 9, z + 4, z + 15, a, (40, 40, 46))                 # the bike
            if not c.wreck:
                rx, ry = local(c.x, c.y, a, -3, -9 * near)
                draw_box(s, rx, ry, 11, 10, z + 15, z + 32, a, c.rider)
                hx, hy = local(c.x, c.y, a, -1, -9 * near)
                pygame.draw.circle(s, (240, 240, 240), proj(hx, hy, z + 38), 6)
                pygame.draw.circle(s, (60, 60, 70), proj(hx, hy, z + 38), 6, 1)
            return
        if c.kind == "moto":
            draw_box(s, c.x, c.y, c.length, c.width * 0.6, z + 4, z + 15, a, c.col)
            if not c.wreck:                          # the rider jumps off after a crash
                rx, ry = local(c.x, c.y, a, -3, 0)
                draw_box(s, rx, ry, 11, 10, z + 15, z + 32, a, c.rider)
                hx, hy = local(c.x, c.y, a, -1, 0)
                pygame.draw.circle(s, (240, 240, 240), proj(hx, hy, z + 38), 6)
                pygame.draw.circle(s, (60, 60, 70), proj(hx, hy, z + 38), 6, 1)
            return
        for lx in (-c.length * 0.32, c.length * 0.32):
            for ly in (-c.width / 2 + 3, c.width / 2 - 3):
                wx, wy = local(c.x, c.y, a, lx, ly)
                draw_box(s, wx, wy, 15, 6, z, z + 10, a, (26, 26, 30), outline=False)
        if c.kind == "tanker":
            # รถขนน้ำมัน: red cab + silver tank with hazard sign
            for lx in (-c.length * 0.1, c.length * 0.08):
                for ly in (-c.width / 2 + 3, c.width / 2 - 3):
                    wx, wy = local(c.x, c.y, a, lx, ly)
                    draw_box(s, wx, wy, 15, 6, z, z + 10, a, (26, 26, 30), outline=False)
            cab = (52, 48, 46) if c.burnt else (200, 50, 40)
            fx, fy = local(c.x, c.y, a, c.length * 0.39, 0)
            draw_box(s, fx, fy, c.length * 0.2, c.width * 0.94, z + 6, z + c.height * 0.72, a, cab)
            gx, gy = local(c.x, c.y, a, c.length * 0.45, 0)
            draw_box(s, gx, gy, c.length * 0.08, c.width * 0.8, z + c.height * 0.42, z + c.height * 0.7, a, glass, top=shade(cab, 1.1), outline=False)
            kx, ky = local(c.x, c.y, a, -c.length * 0.12, 0)
            draw_box(s, kx, ky, c.length * 0.7, c.width * 0.4, z + 6, z + 12, a, (40, 40, 44), outline=False)    # chassis
            draw_box(s, kx, ky, c.length * 0.7, c.width * 0.9, z + 12, z + c.height, a, c.col, top=shade(c.col, 1.08))  # tank
            # stripe and ribs on the tank
            for lx in (-c.length * 0.38, -c.length * 0.12, c.length * 0.14):
                rx, ry = local(c.x, c.y, a, lx, c.width * 0.45 * near)
                pygame.draw.line(s, shade(c.col, 0.7), proj(rx, ry, z + 12), proj(rx, ry, z + c.height), 2)
            sx_, sy_ = local(c.x, c.y, a, -c.length * 0.12, c.width * 0.45 * near)
            mid = proj(sx_, sy_, z + c.height * 0.62)
            if not c.burnt:
                pygame.draw.line(s, (240, 140, 30), proj(*local(c.x, c.y, a, -c.length * 0.46, c.width * 0.45 * near), z + c.height * 0.35),
                                 proj(*local(c.x, c.y, a, c.length * 0.22, c.width * 0.45 * near), z + c.height * 0.35), 3)
                dia = [(mid[0], mid[1] - 8), (mid[0] + 8, mid[1]), (mid[0], mid[1] + 8), (mid[0] - 8, mid[1])]
                pygame.draw.polygon(s, (230, 60, 40), dia)
                pygame.draw.polygon(s, WHITE, dia, 1)
            if c.fuse > 0 and int(c.fuse * 12) % 2 == 0:                       # blinking warning
                tt = self.font_bold.render("!", True, BAD)
                s.blit(tt, tt.get_rect(center=proj(c.x, c.y, z + c.height + 22)))
        elif c.kind == "icecream":
            # รถไอติม: pastel van with a giant cone on the roof
            for lx in (-c.length * 0.32, c.length * 0.32):
                for ly in (-c.width / 2 + 3, c.width / 2 - 3):
                    wx, wy = local(c.x, c.y, a, lx, ly)
                    draw_box(s, wx, wy, 15, 6, z, z + 10, a, (26, 26, 30), outline=False)
            draw_box(s, c.x, c.y, c.length, c.width, z + 5, z + c.height * 0.8, a, c.col, top=(250, 250, 246))
            fx, fy = local(c.x, c.y, a, c.length * 0.4, 0)
            draw_box(s, fx, fy, c.length * 0.14, c.width * 0.82, z + c.height * 0.35, z + c.height * 0.72, a, glass, top=(250, 250, 246), outline=False)
            # striped awning over the serving window
            for i in range(5):
                lx0 = -c.length * 0.35 + i * c.length * 0.12
                p1 = local(c.x, c.y, a, lx0, c.width * 0.5 * near)
                p2 = local(c.x, c.y, a, lx0 + c.length * 0.12, c.width * 0.5 * near)
                col_ = (230, 70, 90) if i % 2 == 0 else (250, 250, 246)
                pygame.draw.polygon(s, col_, [proj(*p1, z + c.height * 0.72), proj(*p2, z + c.height * 0.72),
                                              proj(*p2, z + c.height * 0.58), proj(*p1, z + c.height * 0.58)])
            if not c.wreck:
                cx_, cy_ = local(c.x, c.y, a, -c.length * 0.1, 0)
                top = z + c.height * 0.8
                tip, l_, r_ = proj(cx_, cy_, top + 2), proj(cx_ - 9, cy_, top + 24), proj(cx_ + 9, cy_, top + 24)
                pygame.draw.polygon(s, (214, 160, 90), [tip, l_, r_])
                pygame.draw.polygon(s, (170, 120, 60), [tip, l_, r_], 1)
                sc_ = proj(cx_, cy_, top + 30)
                pygame.draw.circle(s, (250, 180, 205), sc_, 11)
                pygame.draw.circle(s, (252, 246, 232), (sc_[0] - 4, sc_[1] - 9), 7)
                pygame.draw.circle(s, (220, 40, 50), (sc_[0] + 2, sc_[1] - 16), 3)
        elif c.kind == "truck":
            fx, fy = local(c.x, c.y, a, c.length * 0.36, 0)
            draw_box(s, fx, fy, c.length * 0.26, c.width * 0.94, z + 6, z + c.height * 0.72, a, c.col)
            gx, gy = local(c.x, c.y, a, c.length * 0.43, 0)
            draw_box(s, gx, gy, c.length * 0.1, c.width * 0.8, z + c.height * 0.42, z + c.height * 0.7, a, glass, top=shade(c.col, 1.1), outline=False)
            bx, by = local(c.x, c.y, a, -c.length * 0.14, 0)
            draw_box(s, bx, by, c.length * 0.7, c.width, z + 8, z + c.height, a, shade((222, 220, 210), 0.75 if c.wreck else 1))
        else:
            draw_box(s, c.x, c.y, c.length, c.width, z + 5, z + c.height * 0.52, a, c.col)
            cx, cy = local(c.x, c.y, a, -c.length * 0.06, 0)
            roof = c.height * (0.85 if c.wreck else 1.0)  # crumpled roof
            draw_box(s, cx, cy, c.length * 0.5, c.width * 0.84, z + c.height * 0.52, z + roof, a, glass, top=shade(c.col, 1.15))
        if c.wreck:
            # dents and broken glass
            for lx, ly in ((c.length * 0.38, c.width * 0.2), (-c.length * 0.3, -c.width * 0.25), (c.length * 0.1, c.width * 0.3)):
                dx, dy = local(c.x, c.y, a, lx, ly)
                pygame.draw.circle(s, shade(c.col, 0.55), proj(dx, dy, z + c.height * 0.52), 4)
            return
        for ly in (-c.width * 0.3, c.width * 0.3):
            hx, hy = local(c.x, c.y, a, c.length / 2, ly)
            pygame.draw.circle(s, (255, 236, 160), proj(hx, hy, z + c.height * 0.33), 3)
            tx, ty = local(c.x, c.y, a, -c.length / 2, ly)
            pygame.draw.circle(s, (220, 40, 40), proj(tx, ty, z + c.height * 0.33), 3)

    def draw_drone(self, d):
        s = self.active_surface
        t = pygame.time.get_ticks() / 1000
        c = d.car
        # cable down to the car roof
        if d.state != "fly":
            top = proj(d.x, d.y, d.z)
            roof_z = c.lift + c.height
            bottom_z = d.z - (d.z - roof_z) * d.cable
            pygame.draw.line(s, (40, 40, 44), top, proj(d.x, d.y, bottom_z), 2)
            hook = proj(d.x, d.y, bottom_z)
            pygame.draw.circle(s, (230, 190, 40), hook, 3)
        # arms and rotors
        for ox, oy in ((-22, -16), (22, -16), (-22, 16), (22, 16)):
            pygame.draw.line(s, (50, 52, 58), proj(d.x, d.y, d.z + 6), proj(d.x + ox, d.y + oy, d.z + 8), 3)
            rx, ry = proj(d.x + ox, d.y + oy, d.z + 10)
            w = 16 + 3 * math.sin(t * 40 + ox)
            pygame.draw.ellipse(s, (170, 176, 186), (rx - w, ry - 3, w * 2, 6), 1)
            pygame.draw.line(s, (90, 94, 100), (rx - w * math.cos(t * 50), ry), (rx + w * math.cos(t * 50), ry), 2)
        draw_box(s, d.x, d.y, 28, 20, d.z, d.z + 9, 0, (240, 190, 40))
        draw_box(s, d.x, d.y, 14, 10, d.z + 9, d.z + 13, 0, (40, 42, 48))
        if int(t * 4) % 2 == 0:
            pygame.draw.circle(s, (255, 60, 50), proj(d.x + 14, d.y + 10, d.z + 6), 2)

    def draw_person(self, p, carried_on=None):
        """Stick-figure-in-2.5D: every body part is placed along a body axis that can tilt,
        so the same code draws standing, running, falling, lying, carried and dead people."""
        s = self.active_surface
        if carried_on:
            x, y, zb = carried_on.x + 2, carried_on.y, 30
        else:
            x, y, zb = p.x, p.y, 0
        k = p.kind
        sc = 0.76 if k == "kid" else 1.0
        col = mix(p.info["col"], (34, 28, 26), p.char)
        skin = mix(SKIN, (44, 34, 30), p.char)
        if p.hurt_t > 0 and int(p.hurt_t * 18) % 2 == 0:          # hit flash
            col, skin = mix(col, (255, 80, 70), 0.65), mix(skin, (255, 80, 70), 0.65)
        a = math.pi / 2 if carried_on else p.pose
        lying = a > 0.6
        fd = p.fall_dir if lying else p.facing
        alive_up = p.alive and not lying and not carried_on
        moving = alive_up and p.moving
        ph = p.walk * 10
        if moving and p.injured:                                    # limp: uneven bob, one stiff leg
            bob = max(0.0, math.sin(ph)) * 4
        else:
            bob = abs(math.sin(ph)) * 2 if moving else 0
        swing = math.sin(ph) * 4 if moving else 0
        if p.slip_t > 0 and alive_up:
            swing = 6
        sa, ca = math.sin(a), math.cos(a)

        def P(h, side=0.0):
            return proj(x + fd * sa * h + side * ca, y + side * sa * 0.6, zb + ca * (h + bob))

        bw = 18 if k == "strong" else 13 * sc
        # legs
        for side in (-1, 1):
            stiff = p.injured and side == 1 and moving
            sw = swing * side * (0.2 if stiff else 0.6)
            pygame.draw.line(s, mix((44, 46, 58), (30, 26, 24), p.char), P(0, side * 3 * sc + sw), P(11 * sc, side * 3 * sc), 3)
        # torso (capsule)
        hip, neck = P(11 * sc), P(25 * sc)
        pygame.draw.line(s, shade(col, 0.6), hip, neck, int(bw) + 2)
        pygame.draw.line(s, col, hip, neck, int(bw))
        for pt in (hip, neck):
            pygame.draw.circle(s, col, pt, int(bw / 2))
        if p.injured and p.alive:
            pygame.draw.circle(s, BLOOD_HI, P(18 * sc, 2), 3)
        # arms
        t = pygame.time.get_ticks() / 1000
        for side in (-1, 1):
            sh = P(23 * sc, side * (bw / 2 + 1))
            if p.burn_t > 0 and alive_up:                           # flailing while on fire
                hand = P(36 * sc + 3 * math.sin(t * 20 + side), side * (bw / 2 + 6))
            elif lying:
                hand = P(24 * sc, side * (bw / 2 + 9))
            else:
                hand = P(13 * sc, side * (bw / 2 + 2) - swing * side * 0.5)
            pygame.draw.line(s, shade(col, 0.8), sh, hand, 3)
        # head
        head = P(33 * sc)
        hr = int(7 * sc)
        if k == "grandma":
            pygame.draw.circle(s, mix((210, 210, 214), (40, 36, 34), p.char), P(36 * sc, -4 * fd), 5)
        pygame.draw.circle(s, skin, head, hr)
        pygame.draw.circle(s, shade(skin, 0.7), head, hr, 1)
        if k == "warden":
            pygame.draw.circle(s, mix((24, 50, 120), (30, 26, 24), p.char), P(39 * sc), 5)
        elif k == "runner":
            pygame.draw.line(s, (220, 40, 40), P(36 * sc, -hr), P(36 * sc, hr), 2)
        elif k == "kid":
            pygame.draw.circle(s, (60, 40, 30), P(38 * sc), 4)
        if p.injured and p.alive:                                    # head bandage
            pygame.draw.line(s, (240, 240, 240), P(35 * sc, -hr), P(35 * sc, hr), 3)
        if not p.alive:                                              # x_x
            for dx in (-3, 3):
                cx, cy = head[0] + dx, head[1] - 1
                pygame.draw.line(s, (40, 30, 30), (cx - 2, cy - 2), (cx + 2, cy + 2), 1)
                pygame.draw.line(s, (40, 30, 30), (cx - 2, cy + 2), (cx + 2, cy - 2), 1)
        # held items
        if p.fuel and not lying:
            jx = x + 10 * p.facing
            draw_box(s, jx, y + 2, 7, 6, zb + 6, zb + 17, 0, (206, 40, 32))
            pygame.draw.line(s, (40, 40, 40), proj(jx, y + 2, zb + 17), proj(jx, y + 2, zb + 20), 2)
        if k == "grandma" and alive_up:
            cx = head[0] + 10 * p.facing
            pygame.draw.line(s, (120, 80, 40), (cx, P(20)[1]), (cx + 2 * p.facing, P(0)[1]), 2)
        if k == "warden" and p.sign_t > 0 and alive_up:
            px_, py_ = neck[0] + bw / 2 + 4, neck[1]
            pygame.draw.line(s, (90, 90, 90), (px_, py_ + 14), (px_, py_ - 22), 2)
            pts = [(px_ + 9 * math.cos(math.pi / 8 + i * math.pi / 4), py_ - 30 + 9 * math.sin(math.pi / 8 + i * math.pi / 4)) for i in range(8)]
            pygame.draw.polygon(s, (210, 30, 30), pts)
            pygame.draw.polygon(s, WHITE, pts, 1)
        # flames on the body
        if p.burn_t > 0 and p.alive:
            for i, h in enumerate((6, 15, 24, 33)):
                bx_, by_ = P(h * sc, (i % 2 * 2 - 1) * 4)
                fh = 10 + 6 * math.sin(t * 14 + i * 1.7)
                pygame.draw.polygon(s, (255, 120, 30), [(bx_ - 5, by_), (bx_ + 5, by_), (bx_ + 1, by_ - fh)])
                pygame.draw.polygon(s, (255, 220, 90), [(bx_ - 2, by_), (bx_ + 2, by_), (bx_, by_ - fh * 0.55)])
        if carried_on or not p.alive:
            return
        # status above the head
        top = head[1] - hr - 8
        if p.down_t > 0:                                             # dizzy stars
            for i in range(3):
                ang = t * 6 + i * math.tau / 3
                pygame.draw.circle(s, ACCENT, (head[0] + math.cos(ang) * 10, head[1] - 10 + math.sin(ang) * 3), 2)
        elif p.panic:
            tt = self.font_bold.render("!", True, BAD)
            s.blit(tt, tt.get_rect(center=(head[0], top - 10)))
        elif p.saved:
            pygame.draw.lines(s, GOOD, False, [(head[0] - 5, top), (head[0] - 1, top + 4), (head[0] + 6, top - 4)], 2)
        elif p.go:                                                    # walking: green arrow up
            pygame.draw.polygon(s, GOOD, [(head[0] - 5, top - 8), (head[0] + 5, top - 8), (head[0], top - 15)])
        else:                                                         # waiting: pause bars
            pygame.draw.rect(s, ACCENT, (head[0] - 5, top - 15, 3, 8))
            pygame.draw.rect(s, ACCENT, (head[0] + 2, top - 15, 3, 8))
        show_bar = not p.saved and (p.hp < p.max_hp or p is getattr(self, "hover", None))
        if show_bar:
            frac = max(0.0, p.hp / p.max_hp)
            bwid = 28
            bx0, by0 = head[0] - bwid / 2, top - 2
            pygame.draw.rect(s, (20, 20, 24), (bx0 - 1, by0 - 1, bwid + 2, 6))
            hc = GOOD if frac > 0.6 else ACCENT if frac > 0.4 else BAD
            pygame.draw.rect(s, hc, (bx0, by0, bwid * frac, 4))
            if p is getattr(self, "hover", None):
                num = self.font_tiny.render(str((p.idx + 1) % 10), True, TEXT)
                s.blit(num, num.get_rect(midright=(bx0 - 3, by0 + 2)))
        if not p.saved and p.info["cd"] > 1:
            pygame.draw.circle(s, GOOD if p.cd <= 0 else (90, 94, 100), (head[0] + 18, top), 3)
        if p.tired > 0:
            tt = self.font_small.render("เหนื่อย", True, MUTED)
            s.blit(tt, tt.get_rect(center=(head[0], top - 12)))

    def draw_fire(self, f):
        s = self.active_surface
        t = pygame.time.get_ticks() / 1000
        for i in range(9):
            a = i * 2.4
            r = f.r * 0.55 * ((i % 3) / 3 + 0.3)
            fx, fy = f.x + math.cos(a) * r, f.y + math.sin(a) * r * 0.6
            h = 18 + 10 * math.sin(t * 9 + i) * min(1.0, f.life / 2)
            base = proj(fx, fy)
            tip = proj(fx, fy, h + 14)
            pygame.draw.polygon(s, (255, 120, 30), [(base[0] - 7, base[1]), (base[0] + 7, base[1]), tip])
            tip2 = proj(fx, fy, h)
            pygame.draw.polygon(s, (255, 220, 90), [(base[0] - 3, base[1]), (base[0] + 3, base[1]), tip2])

    def draw_floaters(self):
        for x, y, z, text, life, col in self.floating_messages:
            if not text:   # click marker
                cx, cy = proj(x, y)
                r = 14 * (1 - life / 0.5) + 4
                pygame.draw.ellipse(self.active_surface, col, (cx - r, cy - r * 0.5, r * 2, r), 1)
                continue
            t = self.font_bold.render(text, True, col)
            t.set_alpha(int(255 * min(1.0, life / 0.5)))
            self.active_surface.blit(t, t.get_rect(center=proj(x, y, z + 20)))

    def draw_impacts(self):
        if self.font_impact is None:
            self.font_impact = load_font(44, bold=True)
        for x, y, text, life, col, size, rot, oz in self.impact_messages:
            t = 1 - life / 0.9
            pop = size * (1.7 - 0.7 * min(1.0, t * 6))          # big, then settles
            img = self.font_impact.render(text, True, col)
            out = self.font_impact.render(text, True, (20, 16, 14))
            surf = pygame.Surface((img.get_width() + 6, img.get_height() + 6), pygame.SRCALPHA)
            for dx, dy in ((0, 3), (3, 0), (3, 6), (6, 3), (5, 5)):
                surf.blit(out, (dx, dy))
            surf.blit(img, (3, 3))
            surf = pygame.transform.rotozoom(surf, rot, pop * 0.6)
            surf.set_alpha(int(255 * min(1.0, life / 0.3)))
            self.active_surface.blit(surf, surf.get_rect(center=proj(x, y, 50 + oz + t * 30)))

    def draw_toasts(self):
        y = 64
        for text, life, col in self.toast_messages:
            t = self.font_bold.render(text, True, col)
            bg = pygame.Surface((t.get_width() + 24, t.get_height() + 8), pygame.SRCALPHA)
            bg.fill((15, 17, 22, int(200 * min(1.0, life / 0.4))))
            r = bg.get_rect(center=(W / 2, y))
            self.active_surface.blit(bg, r)
            t.set_alpha(int(255 * min(1.0, life / 0.4)))
            self.active_surface.blit(t, t.get_rect(center=r.center))
            y += r.height + 4

    # ------------------------------------------------------------ HUD
    def roster_rects(self):
        out = []
        x0 = 250
        for i, p in enumerate(self.people):
            out.append((p, pygame.Rect(x0 + (i % 5) * 54, HUD_Y + 14 + (i // 5) * 60, 50, 54)))
        return out

    def draw_hud(self):
        s = self.active_surface
        pygame.draw.rect(s, PANEL, (0, HUD_Y, W, H - HUD_Y))
        pygame.draw.line(s, PANEL_2, (0, HUD_Y), (W, HUD_Y), 2)
        saved = sum(p.saved for p in self.people)
        dead = sum(not p.alive for p in self.people)
        target = self.current_level["target"]
        s.blit(self.font_bold.render(self.current_level["name"], True, TEXT), (18, HUD_Y + 12))
        s.blit(self.font_regular.render(f"ข้ามสำเร็จ  {saved} / {target}", True, GOOD if saved >= target else TEXT), (18, HUD_Y + 44))
        s.blit(self.font_regular.render(f"เสียชีวิต  {dead}", True, BAD if dead else MUTED), (18, HUD_Y + 70))
        m, sec = divmod(int(self.elapsed_time), 60)
        s.blit(self.font_regular.render(f"เวลา  {m:02d}:{sec:02d}", True, MUTED), (18, HUD_Y + 96))
        # target bar
        bx, by, bw = 18, HUD_Y + 124, 200
        pygame.draw.rect(s, PANEL_2, (bx, by, bw, 8), border_radius=4)
        pygame.draw.rect(s, GOOD, (bx, by, bw * min(1, saved / 10), 8), border_radius=4)
        tx = bx + bw * target / 10
        pygame.draw.line(s, ACCENT, (tx, by - 3), (tx, by + 11), 2)

        # roster
        for p, r in self.roster_rects():
            pygame.draw.rect(s, PANEL_2, r, border_radius=6)
            if p.go and p.active:
                pygame.draw.rect(s, GOOD, r, 2, border_radius=6)
            if p is getattr(self, "hover", None):
                pygame.draw.rect(s, (200, 200, 200), r, 1, border_radius=6)
            col = mix(p.info["col"], (34, 28, 26), p.char) if p.alive else (70, 70, 76)
            pygame.draw.rect(s, col, (r.centerx - 7, r.y + 18, 14, 16), border_radius=4)
            pygame.draw.circle(s, SKIN if p.alive else (90, 90, 96), (r.centerx, r.y + 12), 6)
            key = self.font_tiny.render(str((p.idx + 1) % 10), True, GOOD if p.go and p.active else MUTED)
            s.blit(key, (r.x + 4, r.y + 2))
            if p.alive and not p.saved:
                frac = max(0.0, p.hp / p.max_hp)
                hc = GOOD if frac > 0.6 else ACCENT if frac > 0.4 else BAD
                pygame.draw.rect(s, (16, 18, 22), (r.x + 5, r.y + 37, r.w - 10, 4))
                pygame.draw.rect(s, hc, (r.x + 5, r.y + 37, (r.w - 10) * frac, 4))
                if p.burn_t > 0:
                    pygame.draw.rect(s, (255, 130, 40), r, 2, border_radius=6)
            if p.fuel:
                pygame.draw.rect(s, (206, 40, 32), (r.right - 12, r.y + 6, 7, 8))
            name = self.font_tiny.render(p.info["short"], True, MUTED)
            s.blit(name, name.get_rect(center=(r.centerx, r.bottom - 8)))
            if p.saved:
                pygame.draw.lines(s, GOOD, False, [(r.x + 6, r.y + 10), (r.x + 10, r.y + 14), (r.x + 17, r.y + 5)], 2)
            elif not p.alive:
                pygame.draw.line(s, BAD, (r.x + 8, r.y + 8), (r.right - 8, r.y + 40), 3)
                pygame.draw.line(s, BAD, (r.right - 8, r.y + 8), (r.x + 8, r.y + 40), 3)
            elif p.info["cd"] > 1 and p.cd > 0:
                frac = p.cd / p.info["cd"]
                pygame.draw.rect(s, (90, 94, 100), (r.x + 4, r.bottom - 3, (r.w - 8) * frac, 2))

        # info about the person under the mouse
        x = 538
        p = getattr(self, "hover", None)
        if p is None:
            mx, my = pygame.mouse.get_pos()
            p = next((q for q, r in self.roster_rects() if r.collidepoint(mx, my)), None)
        if p and p.alive:
            s.blit(self.font_bold.render(f"{(p.idx + 1) % 10}. {p.info['name']}" + ("  · ถือถังน้ำมัน!" if p.fuel else ""), True,
                                      BAD if p.fuel else ACCENT), (x, HUD_Y + 12))
            state = ("ปลอดภัยแล้ว" if p.saved else "กำลังไฟไหม้!" if p.burn_t > 0 else "ล้มอยู่" if p.down_t > 0
                     else "บาดเจ็บหนัก (เดินช้า)" if p.injured else "กำลังเดิน" if p.go else "รออยู่")
            frac = max(0.0, p.hp / p.max_hp)
            hc = GOOD if frac > 0.6 else ACCENT if frac > 0.4 else BAD
            s.blit(self.font_small.render(f"HP {int(max(0, p.hp))}/{p.max_hp}  ·  {state}", True, hc), (x, HUD_Y + 40))
            s.blit(self.font_regular.render(p.info["skill"], True, TEXT), (x, HUD_Y + 62))
            if p.info["cd"] > 1 and not p.saved:
                ready = p.cd <= 0
                txt = "คลิกขวา = ใช้ความสามารถ (พร้อม)" if ready else f"ใช้ได้อีกใน {p.cd:0.1f} วินาที"
                s.blit(self.font_small.render(txt, True, GOOD if ready else MUTED), (x + 300, HUD_Y + 40))
        else:
            s.blit(self.font_bold.render("คลิกที่คน = เดินข้าม / หยุด", True, ACCENT), (x, HUD_Y + 12))
            s.blit(self.font_regular.render("คลิกขวาที่คน = ใช้ความสามารถ", True, TEXT), (x, HUD_Y + 40))
            s.blit(self.font_small.render("ชี้เมาส์ที่คนเพื่อดู HP และความสามารถ", True, MUTED), (x, HUD_Y + 66))
        help1 = "คลิก = เดิน/หยุด   คลิกขวา = ความสามารถ   1-0 = ตามหมายเลข"
        help2 = "G = ทุกคนเดิน   Space = ทุกคนหยุด   P = พัก   R = เริ่มใหม่"
        s.blit(self.font_small.render(help1, True, MUTED), (x, HUD_Y + 104))
        s.blit(self.font_small.render(help2, True, MUTED), (x, HUD_Y + 124))

    def center_card(self, lines, sub=None, w=520):
        s = self.active_surface
        shade_ = pygame.Surface((W, H), pygame.SRCALPHA)
        shade_.fill((10, 12, 16, 150))
        s.blit(shade_, (0, 0))
        h = 70 + 34 * (len(lines) - 1) + (len(sub) * 26 + 20 if sub else 0) + 10
        r = pygame.Rect(0, 0, w, h)
        r.center = (W / 2, H / 2 - 40)
        pygame.draw.rect(s, PANEL, r, border_radius=12)
        pygame.draw.rect(s, PANEL_2, r, 2, border_radius=12)
        y = r.y + 24
        for i, ln in enumerate(lines):
            f = self.font_heading if i == 0 else self.font_regular
            t = f.render(ln, True, ACCENT if i == 0 else TEXT)
            s.blit(t, t.get_rect(midtop=(r.centerx, y)))
            y += 44 if i == 0 else 30
        if sub:
            y += 8
            for ln in sub:
                t = self.font_small.render(ln, True, MUTED)
                s.blit(t, (r.x + 34, y))
                y += 26
        return r

    def draw_title(self):
        self.center_card(
            ["ข้ามถนน", "พาคนข้ามทางม้าลายไปฝั่งปลอดภัยให้ได้มากที่สุด",
             f"ต้องรอดอย่างน้อย {self.current_level['target']} จาก 10 คน"],
            sub=["ตำรวจจราจร – ยกป้ายหยุดรถทีละเลน",
                 "นักวิ่ง – วิ่งเร็วชั่วครู่      คุณยาย – รถใกล้ ๆ ชะลอ",
                 "เด็ก – อยู่คนเดียวจะตกใจ      คนแข็งแรง – แบกคนอื่นได้",
                 "คนถือถังน้ำมัน (สีแดง) – ถ้าโดนชนจะระเบิด",
                 "ทุกคนมี HP: โดนชนจะล้มและบาดเจ็บ  ไฟไหม้ลด HP เรื่อย ๆ",
                 "คราบเลือดทำให้รถลื่นไปชนกัน แล้วโดรนจะมายกซากออก",
                 "คลิกที่คน = เดิน/หยุด   คลิกขวา = ใช้ความสามารถ",
                 "คลิกหรือกดปุ่มใดก็ได้เพื่อเริ่ม"],
            w=560)

    def draw_end(self):
        saved = sum(p.saved for p in self.people)
        if self.state == "win":
            stars = 3 if saved == 10 else 2 if saved >= 8 else 1
            m, sec = divmod(int(self.elapsed_time), 60)
            r = self.center_card(["ผ่านด่าน!", f"รอด {saved} / 10 คน   ·   เวลา {m:02d}:{sec:02d}", " "],
                                 sub=["N = ด่านถัดไป      R = เล่นด่านนี้อีกครั้ง"])
            for i in range(3):
                cx, cy = r.centerx + (i - 1) * 46, r.y + 116
                pts = [(cx + (16 if j % 2 == 0 else 7) * math.cos(-math.pi / 2 + j * math.pi / 5),
                        cy + (16 if j % 2 == 0 else 7) * math.sin(-math.pi / 2 + j * math.pi / 5)) for j in range(10)]
                pygame.draw.polygon(self.active_surface, ACCENT if i < stars else PANEL_2, pts)
        else:
            self.center_card(["ไม่ผ่าน", f"คนที่เหลือไม่พอ (ต้องรอด {self.current_level['target']} คน)"],
                             sub=["R = ลองอีกครั้ง"])


