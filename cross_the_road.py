#!/usr/bin/env python3
"""
ข้ามถนน (Cross the Road) — 2.5D

พาคน 10 คนข้ามทางม้าลายไปฝั่งปลอดภัย แต่ละคนมีความสามารถไม่เหมือนกัน
ถ้าโดนรถชนจะทิ้งคราบเลือดไว้บนถนน รถที่วิ่งผ่านจะลื่นไถลออกนอกเลน
ถ้าไปชนคันอื่นจะกลายเป็นซากขวางถนน แล้วโดรนจะบินมายกออกไป

ทุกคนมี HP — โดนรถชนจะกระเด็น ล้มลง แล้วลุกขึ้นมาเดินกะเผลก
ถ้า HP หมดถึงจะตาย  ไฟไหม้จะลด HP ต่อเนื่องจนกว่าไฟจะดับ

Controls:
  คลิกซ้ายที่คน           เดินข้ามถนน / หยุดรอ
  Shift + คลิกซ้าย        เลือกหลายคน แล้วปล่อย Shift เพื่อเริ่มข้ามพร้อมกัน
  Escape                 ยกเลิกการเลือกกลุ่ม
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
from game_config import (
    ACCENT_COLOR,
    ASPHALT,
    ASPHALT_SPECK,
    BACKGROUND_COLOR,
    CROSSING_START_X,
    CROSSING_END_X,
    FRAMES_PER_SECOND,
    GOAL_LINE_COLOR,
    GOAL_Y,
    GOOD_COLOR,
    HEADS_UP_DISPLAY_Y,
    LANE_DIRECTION,
    LANE_HEIGHT,
    LANES,
    LEVELS,
    MUTED_COLOR,
    PAVEMENT_COLOR,
    PAVEMENT_LINE_COLOR,
    ROAD_BOTTOM,
    ROAD_TOP,
    ROSTER,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SLAB_FRONT_COLOR,
    TEXT_COLOR,
    WHITE,
    WORLD_BOTTOM,
    YELLOW,
)
from geometry import clamp, draw_box, lane_of, project, shade
from rendering import GameRenderer
from simulation import GameSimulation


# ---------------------------------------------------------------- game
# Combine simulation rules and drawing methods on one shared game state; this class owns setup and input.
class Game(GameSimulation, GameRenderer):
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("ข้ามถนน · Cross the Road (2.5D demo)")
        # The display is the visible window; the world canvas is an off-screen image used for camera shake.
        self.display_surface = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.world_canvas = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))        # drawn here, then shaken onto display
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
        # Transparent layers hold ground stains, lane highlights, flashes, and persistent tire marks.
        # An alpha channel controls transparency: 0 is invisible and 255 is opaque.
        # วาดลงภาพพักก่อนนำไปแสดงจริง ส่วน alpha คือความทึบ: 0 โปร่งใส และ 255 ทึบเต็มที่
        self.decal_surface = pygame.Surface((SCREEN_WIDTH, HEADS_UP_DISPLAY_Y), pygame.SRCALPHA)
        self.overlay_surface = pygame.Surface((SCREEN_WIDTH, HEADS_UP_DISPLAY_Y), pygame.SRCALPHA)
        self.flash_surface = pygame.Surface((SCREEN_WIDTH, HEADS_UP_DISPLAY_Y), pygame.SRCALPHA)
        self.skid_mark_surface = pygame.Surface((SCREEN_WIDTH, HEADS_UP_DISPLAY_Y), pygame.SRCALPHA)   # tyre skid marks
        self.level_index = 0
        self.state = "title"
        self.reset()

    # ------------------------------------------------------------ setup
    def reset(self):
        self.current_level = LEVELS[self.level_index]
        self.people = []
        self.selected_people = set()
        self.selection_pending = False
        character_kinds = ROSTER[:]
        random.shuffle(character_kinds)
        # enumerate supplies both the character number and its type from the shuffled roster.
        for index, kind in enumerate(character_kinds):
            # Grid layout: index % 5 gives columns 0..4; index // 5 gives the row.
            # Small random offsets keep the starting crowd from looking perfectly aligned.
            # เครื่องหมาย % หาเศษเพื่อเลือกคอลัมน์ ส่วน // หารปัดลงเพื่อเลือกแถว
            column = index % 5
            row_index = index // 5
            person = Person(
                kind,
                360 + column * 76 + random.uniform(-8, 8),
                520 + row_index * 48 + random.uniform(-6, 6),
                index
            )
            self.people.append(person)

        citizens = [person for person in self.people if person.kind == "citizen"]
        for person in citizens:
            person.fuel = random.random() < 0.3
        # If random assignment gave nobody fuel, choose one citizen so every level includes this mechanic.
        if not any(person.fuel for person in citizens):
            random.choice(citizens).fuel = True

        self.cars = []
        self.drones = []
        self.spawn_timers = [random.uniform(0, 1.5) for _ in range(LANES)]
        self.lane_freeze_timers = [0.0] * LANES
        self.blood_puddles = []
        self.fires = []
        self.particles = []
        self.floating_messages = []
        self.toast_messages = []
        self.impact_messages = []                          # big impact word popups
        self.active_surface_shake_strength = 0.0           # screen shake strength in pixels
        self.hitstop_remaining = 0.0                       # slow-motion freeze on big hits
        self.flash_intensity = 0.0                         # screen flash
        self.skid_mark_surface.fill((0, 0, 0, 0))
        self.skid_mark_fade_timer = 0.0
        self.elapsed_time = 0.0
        self.paused = False
        self.end_screen_timer = 0.0

        # pre-warm traffic so the road is busy from the very first frame
        # Run 6 / (1/60) = 360 traffic steps before play, simulating six seconds of incoming cars.
        # จำลองรถล่วงหน้า 360 รอบ เท่ากับเวลาในเกม 6 วินาที เพื่อให้เริ่มมาแล้วถนนมีรถทันที
        for _ in range(int(6 / (1 / 60))):
            self.update_traffic(1 / 60, pre_warm=True)

    def toast(self, text, color=TEXT_COLOR):
        for toast_item in self.toast_messages:
            if toast_item[0] == text:          # same message again: prolong display
                toast_item[1] = 2.4
                return
        # Toast record: [text, remaining_seconds, color]. Keep only the three most recent messages.
        self.toast_messages.append([text, 2.4, color])
        self.toast_messages = self.toast_messages[-3:]

    def float_text(self, world_x, world_y, text, color):
        # Floating-text record: [world_x, world_y, height, text, remaining_seconds, color].
        self.floating_messages.append([world_x, world_y, 40.0, text, 1.2, color])

    # ------------------------------------------------------------ ground art
    def build_ground(self):
        ground_surface = pygame.Surface((SCREEN_WIDTH, HEADS_UP_DISPLAY_Y))
        ground_surface.fill(BACKGROUND_COLOR)
        # A separate seeded generator repeats its random sequence each rebuild.
        # Only calls through random_seed are repeatable; calls through random still vary.
        # กำหนด seed ให้สุ่มซ้ำได้เฉพาะตัวสร้างนี้ ส่วน random ปกติยังเปลี่ยนได้ในแต่ละครั้ง
        random_seed = random.Random(7)

        # shophouses along the far side
        building_x = -20
        while building_x < SCREEN_WIDTH + 20:
            house_width = random_seed.randint(90, 150)
            house_color = random.choice([
                (196, 160, 120), (170, 186, 196), (214, 196, 150),
                (186, 140, 130), (150, 170, 150), (210, 210, 200)
            ])
            house_height = random_seed.randint(70, 140)
            draw_box(
                ground_surface,
                building_x + house_width / 2,
                -30,
                house_width - 4,
                56,
                0,
                house_height,
                0,
                house_color,
                outline=False
            )
            far_top_y = project(0, -2, house_height)[1]
            far_bottom_y = project(0, -2, 0)[1]
            for window_y in range(int(max(far_top_y, 0)) + 6, int(far_bottom_y) - 14, 16):
                for window_x in range(int(building_x + 10), int(building_x + house_width - 18), 22):
                    pygame.draw.rect(ground_surface, shade(house_color, 0.55), (window_x, window_y, 12, 8))
            pygame.draw.rect(ground_surface, shade(house_color, 0.4), (building_x + house_width / 2 - 14, far_bottom_y - 14, 28, 14))  # door
            building_x += house_width

        # far sidewalk = safe zone
        pygame.draw.polygon(
            ground_surface,
            GOAL_LINE_COLOR,
            [project(0, 0), project(SCREEN_WIDTH, 0), project(SCREEN_WIDTH, ROAD_TOP), project(0, ROAD_TOP)]
        )
        for grid_y in range(0, ROAD_TOP, 24):
            pygame.draw.line(ground_surface, GOAL_LINE_COLOR, project(0, grid_y), project(SCREEN_WIDTH, grid_y))
        for grid_x in range(0, SCREEN_WIDTH, 40):
            pygame.draw.line(ground_surface, GOAL_LINE_COLOR, project(grid_x, 0), project(grid_x, ROAD_TOP))

        # trees
        for tree_x in (70, 250, 770, 950):
            draw_box(ground_surface, tree_x, 14, 8, 8, 0, 34, 0, (110, 80, 50), outline=False)
            for offset_x, offset_z, radius in ((-8, 40, 16), (8, 42, 15), (0, 52, 17)):
                screen_position = project(tree_x + offset_x, 14, offset_z)
                pygame.draw.circle(ground_surface, (60, 130, 70), screen_position, radius)
                pygame.draw.circle(ground_surface, (80, 156, 86), (screen_position[0] - 4, screen_position[1] - 4), radius * 0.55)

        # far curb (front face visible)
        draw_box(ground_surface, SCREEN_WIDTH / 2, ROAD_TOP - 4, SCREEN_WIDTH + 40, 8, 0, 6, 0, (215, 210, 200), outline=False)

        # road
        pygame.draw.polygon(
            ground_surface,
            ASPHALT,
            [project(0, ROAD_TOP), project(SCREEN_WIDTH, ROAD_TOP), project(SCREEN_WIDTH, ROAD_BOTTOM), project(0, ROAD_BOTTOM)]
        )
        for _ in range(1600):
            speck_x, speck_y = project(random.uniform(0, SCREEN_WIDTH), random_seed.uniform(ROAD_TOP, ROAD_BOTTOM))
            ground_surface.set_at((int(speck_x), int(speck_y)), ASPHALT_SPECK)

        # lane markings
        for lane_index in range(1, LANES):
            marking_y = ROAD_TOP + LANE_HEIGHT * lane_index
            # Opposing traffic directions get a double yellow divider; matching directions get dashed white lines.
            if LANE_DIRECTION[lane_index - 1] != LANE_DIRECTION[lane_index]:
                for line_offset in (-3, 3):  # double yellow centre line
                    for segment in ((0, CROSSING_START_X - 40), (CROSSING_END_X + 40, SCREEN_WIDTH)):
                        pygame.draw.line(ground_surface, YELLOW, project(segment[0], marking_y + line_offset), project(segment[1], marking_y + line_offset), 2)
            else:
                for grid_x in range(0, SCREEN_WIDTH, 60):
                    if CROSSING_START_X - 40 < grid_x < CROSSING_END_X + 20:
                        continue
                    pygame.draw.line(ground_surface, WHITE, project(grid_x, marking_y), project(grid_x + 30, marking_y), 2)

        # stop lines before the crossing
        pygame.draw.line(ground_surface, WHITE, project(CROSSING_START_X - 30, ROAD_TOP + 2), project(CROSSING_START_X - 30, ROAD_TOP + LANE_HEIGHT * 2), 4)
        pygame.draw.line(ground_surface, WHITE, project(CROSSING_END_X + 30, ROAD_TOP + LANE_HEIGHT * 2), project(CROSSING_END_X + 30, ROAD_BOTTOM - 2), 4)

        # zebra crossing
        zebra_y = ROAD_TOP + 8
        while zebra_y + 12 < ROAD_BOTTOM - 4:
            pygame.draw.polygon(
                ground_surface,
                WHITE,
                [project(CROSSING_START_X, zebra_y), project(CROSSING_END_X, zebra_y), project(CROSSING_END_X, zebra_y + 13), project(CROSSING_START_X, zebra_y + 13)]
            )
            zebra_y += 24

        # near sidewalk
        pygame.draw.polygon(
            ground_surface,
            PAVEMENT_COLOR,
            [project(0, ROAD_BOTTOM), project(SCREEN_WIDTH, ROAD_BOTTOM), project(SCREEN_WIDTH, WORLD_BOTTOM), project(0, WORLD_BOTTOM)]
        )
        for grid_y in range(ROAD_BOTTOM, WORLD_BOTTOM, 24):
            pygame.draw.line(ground_surface, PAVEMENT_LINE_COLOR, project(0, grid_y), project(SCREEN_WIDTH, grid_y))
        for grid_x in range(0, SCREEN_WIDTH, 40):
            pygame.draw.line(ground_surface, PAVEMENT_LINE_COLOR, project(grid_x, ROAD_BOTTOM), project(grid_x, WORLD_BOTTOM))
        pygame.draw.line(ground_surface, (226, 222, 212), project(0, ROAD_BOTTOM), project(SCREEN_WIDTH, ROAD_BOTTOM), 3)

        # front of the sidewalk slab
        slab_y = project(0, WORLD_BOTTOM)[1]
        pygame.draw.rect(ground_surface, SLAB_FRONT_COLOR, (0, slab_y, SCREEN_WIDTH, HEADS_UP_DISPLAY_Y - slab_y))

        # painted labels
        label_safe = load_font(22, bold=True).render("ฝั่งปลอดภัย  SAFE ZONE", True, (140, 176, 130))
        ground_surface.blit(label_safe, label_safe.get_rect(center=project(SCREEN_WIDTH / 2, 92)))
        label_start = load_font(18, bold=True).render("จุดเริ่มต้น", True, (176, 168, 150))
        ground_surface.blit(label_start, (16, project(0, WORLD_BOTTOM - 22)[1]))
        return ground_surface

    # ------------------------------------------------------------ input
    def person_at(self, screen_x, screen_y, pick_radius=28):
        closest_person = None
        closest_distance = pick_radius
        # Pick the nearest person within the click radius; checking frontmost people first helps resolve ties.
        for person in sorted(self.people, key=lambda candidate: -candidate.y):
            if not person.active:
                continue
            projected_x, projected_y = project(person.x, person.y, 18)
            # Measure the straight-line distance between the mouse click and the projected person position.
            distance = math.hypot(projected_x - screen_x, projected_y - screen_y)
            if distance < closest_distance:
                closest_person = person
                closest_distance = distance
        return closest_person

    # One-click control: left-click a person = walk across / stop,
    # right-click a person = use ability. Keys 1-0 do the same as left-click.
    def toggle_go(self, person):
        if not person.active:
            return
        person.is_walking = not person.is_walking
        if person.is_walking:
            self.plan_crossing(person)
            self.float_text(person.x, person.y, "ไป!", GOOD_COLOR)
        else:
            person.path = []
            self.float_text(person.x, person.y, "หยุด", ACCENT_COLOR)

    def plan_crossing(self, person):
        """Walk to the safe zone, using the zebra crossing."""
        target_x = clamp(person.x, CROSSING_START_X + 14, CROSSING_END_X - 14)
        person.set_target(target_x, GOAL_Y - 30)

    def toggle_person_selection(self, person):
        # Shift-click changes membership without issuing a movement command yet.
        # กดซ้ำเพื่อนำคนออกจากกลุ่ม โดยยังไม่สั่งเดินจนกว่าจะปล่อย Shift
        if not person.active:
            return
        self.selection_pending = True
        if person in self.selected_people:
            self.selected_people.remove(person)
        else:
            self.selected_people.add(person)

    def start_selected_crossing(self):
        # Start everyone together; each character keeps their own walking speed.
        # ข้ามคนที่ตาย ข้ามสำเร็จ หรือถูกอุ้มไปแล้ว และเริ่มเดินในเฟรมเดียวกัน
        self.selection_pending = False
        self.selected_people = {person for person in self.selected_people if person.active}
        for person in self.people:
            if person in self.selected_people:
                person.is_walking = True
                self.plan_crossing(person)
        if self.selected_people:
            self.toast(f"กลุ่ม {len(self.selected_people)} คนเริ่มข้าม!", GOOD_COLOR)

    def set_all(self, should_walk):
        for person in self.people:
            if person.active and person.is_walking != should_walk:
                person.is_walking = should_walk
                if should_walk:
                    self.plan_crossing(person)
                else:
                    person.path = []
        self.toast("ทุกคนเดิน!" if should_walk else "ทุกคนหยุด!", GOOD_COLOR if should_walk else ACCENT_COLOR)

    def use_ability(self, person):
        if not person.active or person.down_time > 0:
            return
        if person.cooldown > 0:
            self.float_text(person.x, person.y, f"รอ {person.cooldown:0.0f} วิ", MUTED_COLOR)
            return

        person_kind = person.kind
        if person_kind == "warden":
            lane = lane_of(person.y)
            if lane is None:
                lane = LANES - 1 if person.y >= ROAD_BOTTOM else 0
            # The officer stops the current lane and, when allowed, its neighboring lane for three seconds.
            target_lanes = [lane] + ([lane - 1] if lane > 0 and person.y < ROAD_BOTTOM else [])
            for lane_index in target_lanes:
                self.lane_freeze_timers[lane_index] = 3.0
            person.sign_time = 3.0
            person.cooldown = person.information["cooldown"]
            self.toast("ตำรวจจราจรยกป้ายหยุด · เลน " + ", ".join(str(lane_index + 1) for lane_index in sorted(target_lanes)), ACCENT_COLOR)
        elif person_kind == "runner":
            person.dash = 1.4
            person.cooldown = person.information["cooldown"]
            if not person.is_walking:
                person.is_walking = True
                self.plan_crossing(person)
            self.float_text(person.x, person.y, "วิ่ง!", GOOD_COLOR)
        elif person_kind == "strong":
            person.cooldown = person.information["cooldown"]
            if person.carrying:
                carried_person = person.carrying
                carried_person.carried_by = None
                person.carrying = None
                carried_person.x = person.x + 14
                carried_person.y = person.y + 4
                carried_person.path = []
                carried_person.is_walking = False
                self.float_text(person.x, person.y, "วางลง", TEXT_COLOR)
            else:
                candidates = [
                    other_person for other_person in self.people
                    if other_person is not person and other_person.active and other_person.carrying is None
                    and math.hypot(other_person.x - person.x, other_person.y - person.y) < 60
                ]
                if candidates:
                    # Choose the candidate with the smallest straight-line distance from the strong character.
                    carried_person = min(candidates, key=lambda other: math.hypot(other.x - person.x, other.y - person.y))
                    carried_person.carried_by = person
                    carried_person.down_time = 0
                    carried_person.path = []
                    carried_person.is_walking = False
                    carried_person.panic = False
                    person.carrying = carried_person
                    self.float_text(person.x, person.y, f"แบก{carried_person.information['name']}", TEXT_COLOR)
                else:
                    self.float_text(person.x, person.y, "ไม่มีใครอยู่ใกล้", MUTED_COLOR)
        else:
            self.float_text(person.x, person.y, "ความสามารถติดตัว", MUTED_COLOR)

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        if self.state == "title":
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
                self.state = "play"
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_r:
                self.reset()
                self.state = "play"
            elif event.key == pygame.K_n and self.state == "win":
                self.level_index = (self.level_index + 1) % len(LEVELS)
                self.reset()
                self.state = "play"
            elif event.key == pygame.K_p and self.state == "play":
                self.paused = not self.paused
                self.selection_pending = False

        if self.state != "play" or self.paused:
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.selected_people.clear()
                self.selection_pending = False
            elif event.key == pygame.K_g:
                self.set_all(True)
            elif event.key == pygame.K_SPACE:
                self.set_all(False)
            elif pygame.K_0 <= event.key <= pygame.K_9:
                # Convert keys 1..9,0 to indexes 0..9; modulo makes key 0 wrap to the final person.
                # แปลงปุ่ม 1 ถึง 9 และ 0 ให้เป็นลำดับคน 0 ถึง 9 โดยใช้เศษจากการหารช่วยวนลำดับ
                person_index = (event.key - pygame.K_1) % 10          # 1..9 -> 0..8, 0 -> 9
                if person_index < len(self.people):
                    person = self.people[person_index]
                    if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                        self.use_ability(person)
                    else:
                        self.toggle_go(person)
        elif event.type == pygame.KEYUP and event.key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
            # With both Shift keys held, wait until the final Shift key is released.
            # หากกด Shift ทั้งสองข้าง ต้องปล่อยทั้งคู่ก่อนจึงสั่งกลุ่มเดิน
            released_modifier = pygame.KMOD_LSHIFT if event.key == pygame.K_LSHIFT else pygame.KMOD_RSHIFT
            remaining_modifiers = getattr(event, "mod", pygame.key.get_mods()) & ~released_modifier
            if self.selection_pending and not remaining_modifiers & pygame.KMOD_SHIFT:
                self.start_selected_crossing()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
            if event.pos[1] >= HEADS_UP_DISPLAY_Y:
                person = next((other_person for other_person, rectangle in self.roster_rectangles() if rectangle.collidepoint(event.pos)), None)
            else:
                person = self.person_at(*event.pos)
            if person:
                if event.button == 1:
                    if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                        self.toggle_person_selection(person)
                    else:
                        self.toggle_go(person)
                else:
                    self.use_ability(person)

    # ------------------------------------------------------------ loop
    def run(self):
        while True:
            # Clock returns milliseconds: divide by 1000 for seconds and cap at 1/30.
            # The cap limits movement jumps after a slow frame, discarding excess real time.
            # แปลงมิลลิวินาทีเป็นวินาที และจำกัดเวลาต่อเฟรมไม่ให้ตัวละครกระโดดไกลเมื่อเกมช้า
            delta_time = min(self.clock.tick(FRAMES_PER_SECOND) / 1000, 1 / 30)
            for event in pygame.event.get():
                self.handle_event(event)
            if self.hitstop_remaining > 0:                        # freeze-frame feel on big hits
                self.hitstop_remaining -= delta_time
                # Use 10% of the normal simulation step during hitstop to create a brief slow-motion impact.
                delta_time *= 0.1
            self.update(delta_time)
            self.draw()


if __name__ == "__main__":
    Game().run()
