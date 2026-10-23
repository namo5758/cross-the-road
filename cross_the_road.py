#!/usr/bin/env python3
"""
ข้ามถนน (Cross the Road) — 2.5D demo in pygame

พาคน 10 คนข้ามทางม้าลายไปฝั่งปลอดภัย แต่ละคนมีความสามารถไม่เหมือนกัน
ถ้าโดนรถชนจะทิ้งคราบเลือดไว้บนถนน รถที่วิ่งผ่านจะลื่นไถลออกนอกเลน
ถ้าไปชนคันอื่นจะกลายเป็นซากขวางถนน แล้วโดรนจะบินมายกออกไป

ทุกคนมี HP — โดนรถชนจะกระเด็น ล้มลง แล้วลุกขึ้นมาเดินกะเผลก
ถ้า HP หมดถึงจะตาย  ไฟไหม้จะลด HP ต่อเนื่องจนกว่าไฟจะดับ

Controls (ง่าย ๆ)
  คลิกซ้ายที่คน           เดินข้ามถนน / หยุดรอ
  คลิกขวาที่คน           ใช้ความสามารถ
  1-9, 0                 เดิน / หยุด ตามหมายเลขคน  (Shift+เลข = ใช้ความสามารถ)
  G                      ทุกคนเดิน
  Space                  ทุกคนหยุด
  P                      หยุดเกมชั่วคราว
  R                      เริ่มด่านใหม่
  N                      ไปด่านถัดไป (หลังผ่านด่าน)

Run:  pip install pygame   then   python cross_the_road.py
"""
import math
import random
import sys

import pygame

from entities import Person
from fonts import load_font
from game_config import (ACCENT, ASPHALT, ASPHALT_SPECK, BG, CW_X0, CW_X1, FPS,
                         GOAL_LINE, GOAL_PAVE, GOAL_Y, GOOD, H, HUD_Y, LANES,
                         LANE_DIR, LANE_H, LEVELS, MUTED, PAVE, PAVE_LINE,
                         ROAD_BOT, ROAD_TOP, ROSTER, SLAB_FRONT, TEXT, W, WHITE,
                         WORLD_BOT, YELLOW)
from geometry import clamp, draw_box, lane_of, proj, shade
from rendering import GameRenderer
from simulation import GameSimulation

# ---------------------------------------------------------------- settings
# ---------------------------------------------------------------- game
class Game(GameSimulation, GameRenderer):
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("ข้ามถนน · Cross the Road (2.5D demo)")
        self.display_surface = pygame.display.set_mode((W, H))
        self.world_canvas = pygame.Surface((W, H))        # the world is drawn here, then shaken onto the display
        self.active_surface = self.display_surface
        self.font_impact = None
        self.clock = pygame.time.Clock()
        self.font_tiny = load_font(13)
        self.font_small = load_font(15)
        self.font_regular = load_font(18)
        self.font_bold = load_font(20, bold=True)
        self.font_large = load_font(40, bold=True)
        self.font_heading = load_font(26, bold=True)
        self.ground_surface = self.build_ground()
        self.decal_surface = pygame.Surface((W, HUD_Y), pygame.SRCALPHA)
        self.overlay_surface = pygame.Surface((W, HUD_Y), pygame.SRCALPHA)
        self.flash_surface = pygame.Surface((W, HUD_Y), pygame.SRCALPHA)
        self.skid_mark_surface = pygame.Surface((W, HUD_Y), pygame.SRCALPHA)   # tyre skid marks
        self.level_index = 0
        self.state = "title"
        self.reset()

    # ------------------------------------------------------------ setup
    def reset(self):
        self.current_level = LEVELS[self.level_index]
        self.people = []
        kinds = ROSTER[:]
        random.shuffle(kinds)
        for i, k in enumerate(kinds):
            col, row = i % 5, i // 5
            p = Person(k, 360 + col * 76 + random.uniform(-8, 8), 520 + row * 48 + random.uniform(-6, 6), i)
            self.people.append(p)
        citizens = [p for p in self.people if p.kind == "citizen"]
        for p in citizens:
            p.fuel = random.random() < 0.3
        if not any(p.fuel for p in citizens):
            random.choice(citizens).fuel = True
        self.cars = []
        self.drones = []
        self.spawn_timers = [random.uniform(0, 1.5) for _ in range(LANES)]
        self.lane_freeze_timers = [0.0] * LANES
        self.blood_puddles, self.fires, self.particles = [], [], []
        self.floating_messages, self.toast_messages = [], []
        self.impact_messages = []          # big "โครม!" words
        self.active_surface_shake_strength = 0.0           # screen shake strength in pixels
        self.hitstop_remaining = 0.0         # short slow-motion right after a big hit
        self.flash_intensity = 0.0           # white flash 0..1
        self.skid_mark_surface.fill((0, 0, 0, 0))
        self.skid_mark_fade_timer = 0.0
        self.elapsed_time = 0.0
        self.paused = False
        self.end_screen_timer = 0.0
        # pre-warm traffic so the road is busy from the first frame
        for _ in range(int(6 / (1 / 60))):
            self.update_traffic(1 / 60, prewarm=True)

    def toast(self, text, col=TEXT):
        for t in self.toast_messages:
            if t[0] == text:          # same message again: just keep it on screen longer
                t[1] = 2.4
                return
        self.toast_messages.append([text, 2.4, col])
        self.toast_messages = self.toast_messages[-3:]

    def float_text(self, x, y, text, col):
        self.floating_messages.append([x, y, 40.0, text, 1.2, col])

    # ------------------------------------------------------------ ground art
    def build_ground(self):
        g = pygame.Surface((W, HUD_Y))
        g.fill(BG)
        rnd = random.Random(7)
        # shophouses along the far side
        x = -20
        while x < W + 20:
            bw = rnd.randint(90, 150)
            col = rnd.choice([(196, 160, 120), (170, 186, 196), (214, 196, 150),
                              (186, 140, 130), (150, 170, 150), (210, 210, 200)])
            h = rnd.randint(70, 140)
            draw_box(g, x + bw / 2, -30, bw - 4, 56, 0, h, 0, col, outline=False)
            fy0, fy1 = proj(0, -2, h)[1], proj(0, -2, 0)[1]
            for wy in range(int(max(fy0, 0)) + 6, int(fy1) - 14, 16):
                for wx in range(int(x + 10), int(x + bw - 18), 22):
                    pygame.draw.rect(g, shade(col, 0.55), (wx, wy, 12, 8))
            pygame.draw.rect(g, shade(col, 0.4), (x + bw / 2 - 14, fy1 - 14, 28, 14))  # door
            x += bw
        # far sidewalk = safe zone
        pygame.draw.polygon(g, GOAL_PAVE, [proj(0, 0), proj(W, 0), proj(W, ROAD_TOP), proj(0, ROAD_TOP)])
        for yy in range(0, ROAD_TOP, 24):
            pygame.draw.line(g, GOAL_LINE, proj(0, yy), proj(W, yy))
        for xx in range(0, W, 40):
            pygame.draw.line(g, GOAL_LINE, proj(xx, 0), proj(xx, ROAD_TOP))
        # trees
        for tx in (70, 250, 770, 950):
            draw_box(g, tx, 14, 8, 8, 0, 34, 0, (110, 80, 50), outline=False)
            for ox, oz, r in ((-8, 40, 16), (8, 42, 15), (0, 52, 17)):
                c = proj(tx + ox, 14, oz)
                pygame.draw.circle(g, (60, 130, 70), c, r)
                pygame.draw.circle(g, (80, 156, 86), (c[0] - 4, c[1] - 4), r * 0.55)
        # far curb (front face visible)
        draw_box(g, W / 2, ROAD_TOP - 4, W + 40, 8, 0, 6, 0, (215, 210, 200), outline=False)
        # road
        pygame.draw.polygon(g, ASPHALT, [proj(0, ROAD_TOP), proj(W, ROAD_TOP), proj(W, ROAD_BOT), proj(0, ROAD_BOT)])
        for _ in range(1600):
            sx, sy = proj(rnd.uniform(0, W), rnd.uniform(ROAD_TOP, ROAD_BOT))
            g.set_at((int(sx), int(sy)), ASPHALT_SPECK)
        # lane markings
        for i in range(1, LANES):
            yy = ROAD_TOP + LANE_H * i
            if LANE_DIR[i - 1] != LANE_DIR[i]:
                for off in (-3, 3):  # double yellow centre line
                    for seg in ((0, CW_X0 - 40), (CW_X1 + 40, W)):
                        pygame.draw.line(g, YELLOW, proj(seg[0], yy + off), proj(seg[1], yy + off), 2)
            else:
                for xx in range(0, W, 60):
                    if CW_X0 - 40 < xx < CW_X1 + 20:
                        continue
                    pygame.draw.line(g, WHITE, proj(xx, yy), proj(xx + 30, yy), 2)
        # stop lines before the crossing
        pygame.draw.line(g, WHITE, proj(CW_X0 - 30, ROAD_TOP + 2), proj(CW_X0 - 30, ROAD_TOP + LANE_H * 2), 4)
        pygame.draw.line(g, WHITE, proj(CW_X1 + 30, ROAD_TOP + LANE_H * 2), proj(CW_X1 + 30, ROAD_BOT - 2), 4)
        # zebra crossing
        yy = ROAD_TOP + 8
        while yy + 12 < ROAD_BOT - 4:
            pygame.draw.polygon(g, WHITE, [proj(CW_X0, yy), proj(CW_X1, yy), proj(CW_X1, yy + 13), proj(CW_X0, yy + 13)])
            yy += 24
        # near sidewalk
        pygame.draw.polygon(g, PAVE, [proj(0, ROAD_BOT), proj(W, ROAD_BOT), proj(W, WORLD_BOT), proj(0, WORLD_BOT)])
        for yy in range(ROAD_BOT, WORLD_BOT, 24):
            pygame.draw.line(g, PAVE_LINE, proj(0, yy), proj(W, yy))
        for xx in range(0, W, 40):
            pygame.draw.line(g, PAVE_LINE, proj(xx, ROAD_BOT), proj(xx, WORLD_BOT))
        pygame.draw.line(g, (226, 222, 212), proj(0, ROAD_BOT), proj(W, ROAD_BOT), 3)
        # front of the sidewalk slab
        y0 = proj(0, WORLD_BOT)[1]
        pygame.draw.rect(g, SLAB_FRONT, (0, y0, W, HUD_Y - y0))
        # painted labels
        lab = self_font(22).render("ฝั่งปลอดภัย  SAFE ZONE", True, (140, 176, 130))
        g.blit(lab, lab.get_rect(center=proj(W / 2, 92)))
        lab = self_font(18).render("จุดเริ่มต้น", True, (176, 168, 150))
        g.blit(lab, (16, proj(0, WORLD_BOT - 22)[1]))
        return g

    # ------------------------------------------------------------ input
    def person_at(self, sx, sy, radius=28):
        best, bd = None, radius
        for p in sorted(self.people, key=lambda q: -q.y):
            if not p.active:
                continue
            cx, cy = proj(p.x, p.y, 18)
            d = math.hypot(cx - sx, cy - sy)
            if d < bd:
                best, bd = p, d
        return best

    # One-click control:  left-click a person = walk across / stop,
    # right-click a person = use their ability.  Keys 1-0 do the same as left-click.
    def toggle_go(self, p):
        if not p.active:
            return
        p.go = not p.go
        if p.go:
            self.plan_crossing(p)
            self.float_text(p.x, p.y, "ไป!", GOOD)
        else:
            p.path = []
            self.float_text(p.x, p.y, "หยุด", ACCENT)

    def plan_crossing(self, p):
        """Walk to the safe zone, using the zebra crossing."""
        tx = clamp(p.x, CW_X0 + 14, CW_X1 - 14)
        p.set_target(tx, GOAL_Y - 30)

    def set_all(self, go):
        for p in self.people:
            if p.active and p.go != go:
                p.go = go
                if go:
                    self.plan_crossing(p)
                else:
                    p.path = []
        self.toast("ทุกคนเดิน!" if go else "ทุกคนหยุด!", GOOD if go else ACCENT)

    def use_ability(self, p):
        if not p.active or p.down_t > 0:
            return
        if p.cd > 0:
            self.float_text(p.x, p.y, f"รอ {p.cd:0.0f} วิ", MUTED)
            return
        k = p.kind
        if k == "warden":
            lane = lane_of(p.y)
            if lane is None:
                lane = LANES - 1 if p.y >= ROAD_BOT else 0
            lanes = [lane] + ([lane - 1] if lane > 0 and p.y < ROAD_BOT else [])
            for L in lanes:                     # his lane and the one ahead of him
                self.lane_freeze_timers[L] = 3.0
            p.sign_t = 3.0
            p.cd = p.info["cd"]
            self.toast("ตำรวจจราจรยกป้ายหยุด · เลน " + ", ".join(str(L + 1) for L in sorted(lanes)), ACCENT)
        elif k == "runner":
            p.dash = 1.4
            p.cd = p.info["cd"]
            if not p.go:
                p.go = True
                self.plan_crossing(p)
            self.float_text(p.x, p.y, "วิ่ง!", GOOD)
        elif k == "strong":
            p.cd = p.info["cd"]
            if p.carrying:
                c = p.carrying
                c.carried_by = None
                p.carrying = None
                c.x, c.y = p.x + 14, p.y + 4
                c.path, c.go = [], False
                self.float_text(p.x, p.y, "วางลง", TEXT)
            else:
                cands = [q for q in self.people if q is not p and q.active and q.carrying is None
                         and math.hypot(q.x - p.x, q.y - p.y) < 60]
                if cands:
                    c = min(cands, key=lambda q: math.hypot(q.x - p.x, q.y - p.y))
                    c.carried_by = p
                    c.down_t = 0
                    c.path, c.go = [], False
                    c.panic = False
                    p.carrying = c
                    self.float_text(p.x, p.y, f"แบก{c.info['name']}", TEXT)
                else:
                    self.float_text(p.x, p.y, "ไม่มีใครอยู่ใกล้", MUTED)
        else:
            self.float_text(p.x, p.y, "ความสามารถติดตัว", MUTED)

    def handle_event(self, e):
        if e.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        if self.state == "title":
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
                self.state = "play"
            return
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_r:
                self.reset()
                self.state = "play"
            elif e.key == pygame.K_n and self.state == "win":
                self.level_index = (self.level_index + 1) % len(LEVELS)
                self.reset()
                self.state = "play"
            elif e.key == pygame.K_p and self.state == "play":
                self.paused = not self.paused
        if self.state != "play" or self.paused:
            return
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_g:
                self.set_all(True)
            elif e.key == pygame.K_SPACE:
                self.set_all(False)
            elif pygame.K_0 <= e.key <= pygame.K_9:
                slot = (e.key - pygame.K_1) % 10          # 1..9 -> 0..8, 0 -> 9
                if slot < len(self.people):
                    p = self.people[slot]
                    if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                        self.use_ability(p)
                    else:
                        self.toggle_go(p)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button in (1, 3):
            if e.pos[1] >= HUD_Y:
                p = next((q for q, r in self.roster_rects() if r.collidepoint(e.pos)), None)
            else:
                p = self.person_at(*e.pos)
            if p:
                if e.button == 1:
                    self.toggle_go(p)
                else:
                    self.use_ability(p)

    # ------------------------------------------------------------ update
    # ------------------------------------------------------------ loop
    def run(self):
        while True:
            dt = min(self.clock.tick(FPS) / 1000, 1 / 30)
            for e in pygame.event.get():
                self.handle_event(e)
            if self.hitstop_remaining > 0:                        # freeze-frame feel on big hits
                self.hitstop_remaining -= dt
                dt *= 0.1
            self.update(dt)
            self.draw()


def self_font(size):
    return load_font(size, bold=True)


if __name__ == "__main__":
    Game().run()
