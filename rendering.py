"""Pygame presentation layer for Cross the Road.

GameRenderer reads the Game instance's state and draws it. It deliberately does
not advance simulation state or handle player input.
"""

import math
import random

import pygame

from fonts import load_font
from game_config import (
    ACCENT_COLOR,
    BACKGROUND_COLOR,
    BAD_COLOR,
    BLOOD_HIGHLIGHT,
    GLASS_COLOR,
    GOOD_COLOR,
    HEADS_UP_DISPLAY_Y,
    LANE_HEIGHT,
    MUTED_COLOR,
    PANEL_2_COLOR,
    PANEL_COLOR,
    ROAD_TOP,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SKIN_COLOR,
    TEXT_COLOR,
    VERTICAL_SCALE,
    WHITE,
)
from geometry import box_corners, draw_box, local, mix, project, shade

ITEM_TYPE_CAR = 0
ITEM_TYPE_PERSON = 1
ITEM_TYPE_FIRE = 2


class GameRenderer:
    # ------------------------------------------------------------ drawing
    # Build a frame from back to front: ground, stains/shadows, depth-sorted objects, effects, then interface.
    def draw(self):
        self.active_surface = self.world_canvas
        surface = self.world_canvas
        surface.blit(self.ground_surface, (0, 0))
        surface.blit(self.skid_mark_surface, (0, 0))
        self.draw_decals()
        surface.blit(self.decal_surface, (0, 0))
        self.draw_frozen_lanes()

        render_items = []
        for car in self.cars:
            if not car.towed:
                render_items.append((car.depth(), ITEM_TYPE_CAR, car))

        mouse_x, mouse_y = pygame.mouse.get_pos()
        self.hover = self.person_at(mouse_x, mouse_y) if self.state == "play" and mouse_y < HEADS_UP_DISPLAY_Y else None

        for person in self.people:
            if person.alive and person.carried_by is None:
                render_items.append((person.y, ITEM_TYPE_PERSON, person))
            elif not person.alive and person.death_time < 10:
                render_items.append((person.y - 0.5, ITEM_TYPE_PERSON, person))

        for fire in self.fires:
            render_items.append((fire.y + 1, ITEM_TYPE_FIRE, fire))

        # Painter order: smaller ground depth is drawn first, letting nearer objects cover farther ones.
        # วาดของที่อยู่ไกลก่อน แล้ววาดของใกล้ทับ จึงดูเหมือนบังกันตามความลึก
        render_items.sort(key=lambda item: item[0])

        for _, item_type, entity in render_items:
            if item_type == ITEM_TYPE_CAR:
                self.draw_car(entity)
            elif item_type == ITEM_TYPE_PERSON:
                self.draw_person(entity)
                if entity.carrying:
                    self.draw_person(entity.carrying, carrier=entity)
            else:
                self.draw_fire(entity)

        for car in self.cars:
            if car.towed:
                self.draw_car(car)

        for drone in sorted(self.drones, key=lambda drone_candidate: drone_candidate.y):
            self.draw_drone(drone)

        for particle in self.particles:
            # Remaining / initial lifetime gives a 1-to-0 fraction used to shrink fading particles.
            alpha = particle.life / particle.maximum_life
            screen_x, screen_y = project(particle.x, particle.y, particle.z)
            if particle.shape == "chunk":
                width, height = particle.size, particle.size * 0.6
                cosine_angle, sine_angle = math.cos(particle.angle), math.sin(particle.angle)
                points = [
                    (screen_x + delta_x * cosine_angle - delta_y * sine_angle,
                     screen_y + delta_x * sine_angle + delta_y * cosine_angle)
                    for delta_x, delta_y in ((-width, -height), (width, -height), (width, height), (-width, height))
                ]
                pygame.draw.polygon(surface, particle.color, points)
                pygame.draw.polygon(surface, shade(particle.color, 0.5), points, 1)
            elif particle.shape == "wheel":
                pygame.draw.circle(surface, particle.color, (screen_x, screen_y), particle.size)
                pygame.draw.circle(
                    surface,
                    (150, 150, 156),
                    (screen_x + math.cos(particle.angle) * 2, screen_y + math.sin(particle.angle) * 2),
                    2
                )
            else:
                pygame.draw.circle(surface, particle.color, (screen_x, screen_y), max(1, int(particle.size * (0.5 + alpha * 0.5))))

        self.draw_floaters()
        self.draw_impacts()

        if self.flash_intensity > 0:
            self.flash_surface.fill((255, 250, 235, int(170 * self.flash_intensity)))
            surface.blit(self.flash_surface, (0, 0))

        # shake the world, keep the HUD still
        self.active_surface = self.display_surface
        offset_x = 0
        offset_y = 0
        if self.active_surface_shake_strength > 0.5:
            offset_x = random.uniform(-self.active_surface_shake_strength, self.active_surface_shake_strength)
            offset_y = random.uniform(-self.active_surface_shake_strength, self.active_surface_shake_strength) * 0.7

        self.display_surface.fill(BACKGROUND_COLOR)
        self.display_surface.blit(self.world_canvas, (offset_x, offset_y), (0, 0, SCREEN_WIDTH, HEADS_UP_DISPLAY_Y))

        self.draw_toasts()
        self.draw_heads_up_display()

        if self.state == "title":
            self.draw_title()
        elif self.state in ("win", "lose"):
            self.draw_end()
        elif self.paused:
            self.center_card(["หยุดชั่วคราว", "กด P เพื่อเล่นต่อ"])

        pygame.display.flip()

    def draw_decals(self):
        decal_surface = self.decal_surface
        decal_surface.fill((0, 0, 0, 0))

        for blood_puddle in self.blood_puddles:
            # Puddles stay at alpha 220 until their last three seconds, then fade linearly to zero.
            # คราบจะเริ่มจางในสามวินาทีสุดท้าย โดยลดความทึบตามเวลาที่เหลือ
            alpha = int(220 * min(1.0, blood_puddle.life / 3.0))
            for blob_x, blob_y, blob_radius in blood_puddle.blobs:
                center_x, center_y = project(blood_puddle.x + blob_x, blood_puddle.y + blob_y)
                pygame.draw.ellipse(
                    decal_surface,
                    (*blood_puddle.color, alpha),
                    (center_x - blob_radius, center_y - blob_radius * VERTICAL_SCALE, blob_radius * 2, blob_radius * 2 * VERTICAL_SCALE)
                )
            center_x, center_y = project(blood_puddle.x - blood_puddle.radius * 0.2, blood_puddle.y - blood_puddle.radius * 0.2)
            pygame.draw.ellipse(decal_surface, (*blood_puddle.highlight_color, alpha // 2), (center_x - 6, center_y - 3, 12, 5))

        for fire in self.fires:
            center_x, center_y = project(fire.x, fire.y)
            pygame.draw.ellipse(
                decal_surface,
                (20, 16, 14, 170),
                (center_x - fire.radius, center_y - fire.radius * VERTICAL_SCALE * 0.75, fire.radius * 2, fire.radius * 2 * VERTICAL_SCALE * 0.75)
            )

        for car in self.cars:
            corners = box_corners(car.x + 5, car.y + 7, car.length, car.width, car.angle)
            pygame.draw.polygon(decal_surface, (0, 0, 0, 70 if car.lift < 5 else 40), [project(*corner) for corner in corners])

        for drone in self.drones:
            center_x, center_y = project(drone.x, drone.y)
            pygame.draw.ellipse(decal_surface, (0, 0, 0, 50), (center_x - 26, center_y - 9, 52, 18))

        hover_person = getattr(self, "hover", None)
        for person in self.people:
            if not person.alive or person.carried_by:
                continue
            center_x, center_y = project(person.x + 2, person.y + 2)
            pygame.draw.ellipse(decal_surface, (0, 0, 0, 80), (center_x - 10, center_y - 4, 20, 8))
            center_x, center_y = project(person.x, person.y)
            # Gold rings show the group chosen with Shift-click.
            # วงสีทองแสดงคนในกลุ่มที่เลือก โดยยังใช้วงสีเขียวแสดงการเดินตามเดิม
            if person.active and person in self.selected_people:
                pygame.draw.ellipse(decal_surface, (*ACCENT_COLOR, 240), (center_x - 20, center_y - 10, 40, 20), 3)
            if person is hover_person:
                pygame.draw.ellipse(decal_surface, (255, 255, 255, 200), (center_x - 16, center_y - 8, 32, 16), 2)
            if person.is_walking and not person.saved:
                pygame.draw.ellipse(decal_surface, (*GOOD_COLOR, 200), (center_x - 13, center_y - 6, 26, 12), 2)

    def draw_frozen_lanes(self):
        overlay = self.overlay_surface
        overlay.fill((0, 0, 0, 0))
        any_frozen = False
        for lane_index, freeze_time in enumerate(self.lane_freeze_timers):
            if freeze_time <= 0:
                continue
            any_frozen = True
            lane_top_y = ROAD_TOP + LANE_HEIGHT * lane_index
            lane_bottom_y = ROAD_TOP + LANE_HEIGHT * (lane_index + 1)
            # Lane highlights fade during their final second; multiplying the fraction by 60 limits opacity.
            alpha = int(60 * min(1.0, freeze_time))
            pygame.draw.polygon(
                overlay,
                (230, 60, 50, alpha),
                [project(0, lane_top_y), project(SCREEN_WIDTH, lane_top_y), project(SCREEN_WIDTH, lane_bottom_y), project(0, lane_bottom_y)]
            )
        if any_frozen:
            self.active_surface.blit(overlay, (0, 0))

    # Build vehicle art from local offsets; local() rotates details with the car and project() adds visible height.
    # ประกอบรถจากชิ้นส่วนที่อ้างอิงตำแหน่งรถ เพื่อให้ทุกชิ้นหมุนและยกสูงไปพร้อมกัน
    def draw_car(self, car):
        surface = self.active_surface
        angle = car.angle
        lift_z = car.lift                                   # > 0 while a drone carries it
        glass_color = (40, 46, 52) if car.wreck else GLASS_COLOR
        camera_side = 1 if car.direction > 0 else -1          # local side that faces the camera

        if car.kind == "sidecar":
            # Motorcycle with sidecar: bike on one side, a tub with wheel on the other
            tub_x, tub_y = local(car.x, car.y, angle, -2, 9 * camera_side)
            draw_box(surface, tub_x, tub_y, 14, 6, lift_z, lift_z + 9, angle, (26, 26, 30), outline=False)          # tub wheel
            draw_box(surface, tub_x, tub_y, 32, 18, lift_z + 6, lift_z + 17, angle, car.color)                          # tub
            pygame.draw.polygon(
                surface,
                shade(car.color, 1.25),
                [project(*local(car.x, car.y, angle, 12, 9 * camera_side + offset), lift_z + 17) for offset in (-9, 9)] +
                [project(*local(car.x, car.y, angle, 18, 9 * camera_side), lift_z + 21)]
            )
            if not car.wreck:
                if car.cargo == "passenger":
                    passenger_x, passenger_y = local(car.x, car.y, angle, -4, 9 * camera_side)
                    draw_box(surface, passenger_x, passenger_y, 9, 9, lift_z + 17, lift_z + 28, angle, (210, 120, 60))
                    pygame.draw.circle(surface, SKIN_COLOR, project(passenger_x, passenger_y, lift_z + 33), 5)
                elif car.cargo == "crates":
                    for crate_index, crate_offset in enumerate((-8, 4)):
                        crate_x, crate_y = local(car.x, car.y, angle, crate_offset, 9 * camera_side)
                        draw_box(surface, crate_x, crate_y, 10, 12, lift_z + 17, lift_z + 26 + crate_index * 4, angle, (176, 130, 76))
                else:
                    for bottle_offset in (-10, -4, 2, 8):
                        bottle_x, bottle_y = local(car.x, car.y, angle, bottle_offset, 9 * camera_side)
                        draw_box(surface, bottle_x, bottle_y, 4, 4, lift_z + 17, lift_z + 29, angle, (90, 170, 110), outline=False)
            motorcycle_x, motorcycle_y = local(car.x, car.y, angle, 0, -9 * camera_side)
            draw_box(surface, motorcycle_x, motorcycle_y, 38, 9, lift_z + 4, lift_z + 15, angle, (40, 40, 46))                 # the bike
            if not car.wreck:
                rider_x, rider_y = local(car.x, car.y, angle, -3, -9 * camera_side)
                draw_box(surface, rider_x, rider_y, 11, 10, lift_z + 15, lift_z + 32, angle, car.rider_color)
                helmet_x, helmet_y = local(car.x, car.y, angle, -1, -9 * camera_side)
                pygame.draw.circle(surface, (240, 240, 240), project(helmet_x, helmet_y, lift_z + 38), 6)
                pygame.draw.circle(surface, (60, 60, 70), project(helmet_x, helmet_y, lift_z + 38), 6, 1)
            return

        if car.kind == "moto":
            draw_box(surface, car.x, car.y, car.length, car.width * 0.6, lift_z + 4, lift_z + 15, angle, car.color)
            if not car.wreck:
                rider_x, rider_y = local(car.x, car.y, angle, -3, 0)
                draw_box(surface, rider_x, rider_y, 11, 10, lift_z + 15, lift_z + 32, angle, car.rider_color)
                helmet_x, helmet_y = local(car.x, car.y, angle, -1, 0)
                pygame.draw.circle(surface, (240, 240, 240), project(helmet_x, helmet_y, lift_z + 38), 6)
                pygame.draw.circle(surface, (60, 60, 70), project(helmet_x, helmet_y, lift_z + 38), 6, 1)
            return

        for offset_along in (-car.length * 0.32, car.length * 0.32):
            for offset_across in (-car.width / 2 + 3, car.width / 2 - 3):
                wheel_x, wheel_y = local(car.x, car.y, angle, offset_along, offset_across)
                draw_box(surface, wheel_x, wheel_y, 15, 6, lift_z, lift_z + 10, angle, (26, 26, 30), outline=False)

        if car.kind == "tanker":
            # Fuel tanker: red cab + silver tank with hazard sign
            for offset_along in (-car.length * 0.1, car.length * 0.08):
                for offset_across in (-car.width / 2 + 3, car.width / 2 - 3):
                    wheel_x, wheel_y = local(car.x, car.y, angle, offset_along, offset_across)
                    draw_box(surface, wheel_x, wheel_y, 15, 6, lift_z, lift_z + 10, angle, (26, 26, 30), outline=False)
            cab_color = (52, 48, 46) if car.burnt else (200, 50, 40)
            front_x, front_y = local(car.x, car.y, angle, car.length * 0.39, 0)
            draw_box(surface, front_x, front_y, car.length * 0.2, car.width * 0.94, lift_z + 6, lift_z + car.height * 0.72, angle, cab_color)
            glass_x, glass_y = local(car.x, car.y, angle, car.length * 0.45, 0)
            draw_box(surface, glass_x, glass_y, car.length * 0.08, car.width * 0.8, lift_z + car.height * 0.42, lift_z + car.height * 0.7, angle, glass_color, top_color=shade(cab_color, 1.1), outline=False)
            chassis_x, chassis_y = local(car.x, car.y, angle, -car.length * 0.12, 0)
            draw_box(surface, chassis_x, chassis_y, car.length * 0.7, car.width * 0.4, lift_z + 6, lift_z + 12, angle, (40, 40, 44), outline=False)
            draw_box(surface, chassis_x, chassis_y, car.length * 0.7, car.width * 0.9, lift_z + 12, lift_z + car.height, angle, car.color, top_color=shade(car.color, 1.08))
            # stripe and ribs on the tank
            for offset_along in (-car.length * 0.38, -car.length * 0.12, car.length * 0.14):
                stripe_x, stripe_y = local(car.x, car.y, angle, offset_along, car.width * 0.45 * camera_side)
                pygame.draw.line(surface, shade(car.color, 0.7), project(stripe_x, stripe_y, lift_z + 12), project(stripe_x, stripe_y, lift_z + car.height), 2)
            side_x, side_y = local(car.x, car.y, angle, -car.length * 0.12, car.width * 0.45 * camera_side)
            stripe_midpoint = project(side_x, side_y, lift_z + car.height * 0.62)
            if not car.burnt:
                pygame.draw.line(
                    surface,
                    (240, 140, 30),
                    project(*local(car.x, car.y, angle, -car.length * 0.46, car.width * 0.45 * camera_side), lift_z + car.height * 0.35),
                    project(*local(car.x, car.y, angle, car.length * 0.22, car.width * 0.45 * camera_side), lift_z + car.height * 0.35),
                    3
                )
                diamond_points = [
                    (stripe_midpoint[0], stripe_midpoint[1] - 8),
                    (stripe_midpoint[0] + 8, stripe_midpoint[1]),
                    (stripe_midpoint[0], stripe_midpoint[1] + 8),
                    (stripe_midpoint[0] - 8, stripe_midpoint[1])
                ]
                pygame.draw.polygon(surface, (230, 60, 40), diamond_points)
                pygame.draw.polygon(surface, WHITE, diamond_points, 1)
            if car.fuse > 0 and int(car.fuse * 12) % 2 == 0:
                warning_text = self.font_bold.render("!", True, BAD_COLOR)
                surface.blit(warning_text, warning_text.get_rect(center=project(car.x, car.y, lift_z + car.height + 22)))
        elif car.kind == "icecream":
            # Ice cream van: pastel van with a giant cone on the roof
            for offset_along in (-car.length * 0.32, car.length * 0.32):
                for offset_across in (-car.width / 2 + 3, car.width / 2 - 3):
                    wheel_x, wheel_y = local(car.x, car.y, angle, offset_along, offset_across)
                    draw_box(surface, wheel_x, wheel_y, 15, 6, lift_z, lift_z + 10, angle, (26, 26, 30), outline=False)
            draw_box(surface, car.x, car.y, car.length, car.width, lift_z + 5, lift_z + car.height * 0.8, angle, car.color, top_color=(250, 250, 246))
            front_x, front_y = local(car.x, car.y, angle, car.length * 0.4, 0)
            draw_box(surface, front_x, front_y, car.length * 0.14, car.width * 0.82, lift_z + car.height * 0.35, lift_z + car.height * 0.72, angle, glass_color, top_color=(250, 250, 246), outline=False)
            # striped awning over serving window
            for awning_index in range(5):
                stripe_offset = -car.length * 0.35 + awning_index * car.length * 0.12
                stripe_start = local(car.x, car.y, angle, stripe_offset, car.width * 0.5 * camera_side)
                stripe_end = local(car.x, car.y, angle, stripe_offset + car.length * 0.12, car.width * 0.5 * camera_side)
                stripe_color = (230, 70, 90) if awning_index % 2 == 0 else (250, 250, 246)
                pygame.draw.polygon(
                    surface,
                    stripe_color,
                    [project(*stripe_start, lift_z + car.height * 0.72),
                     project(*stripe_end, lift_z + car.height * 0.72),
                     project(*stripe_end, lift_z + car.height * 0.58),
                     project(*stripe_start, lift_z + car.height * 0.58)]
                )
            if not car.wreck:
                cone_x, cone_y = local(car.x, car.y, angle, -car.length * 0.1, 0)
                roof_z = lift_z + car.height * 0.8
                cone_tip = project(cone_x, cone_y, roof_z + 2)
                cone_left = project(cone_x - 9, cone_y, roof_z + 24)
                cone_right = project(cone_x + 9, cone_y, roof_z + 24)
                pygame.draw.polygon(surface, (214, 160, 90), [cone_tip, cone_left, cone_right])
                pygame.draw.polygon(surface, (170, 120, 60), [cone_tip, cone_left, cone_right], 1)
                scoop_center = project(cone_x, cone_y, roof_z + 30)
                pygame.draw.circle(surface, (250, 180, 205), scoop_center, 11)
                pygame.draw.circle(surface, (252, 246, 232), (scoop_center[0] - 4, scoop_center[1] - 9), 7)
                pygame.draw.circle(surface, (220, 40, 50), (scoop_center[0] + 2, scoop_center[1] - 16), 3)
        elif car.kind == "truck":
            front_x, front_y = local(car.x, car.y, angle, car.length * 0.36, 0)
            draw_box(surface, front_x, front_y, car.length * 0.26, car.width * 0.94, lift_z + 6, lift_z + car.height * 0.72, angle, car.color)
            glass_x, glass_y = local(car.x, car.y, angle, car.length * 0.43, 0)
            draw_box(surface, glass_x, glass_y, car.length * 0.1, car.width * 0.8, lift_z + car.height * 0.42, lift_z + car.height * 0.7, angle, glass_color, top_color=shade(car.color, 1.1), outline=False)
            box_x, box_y = local(car.x, car.y, angle, -car.length * 0.14, 0)
            draw_box(surface, box_x, box_y, car.length * 0.7, car.width, lift_z + 8, lift_z + car.height, angle, shade((222, 220, 210), 0.75 if car.wreck else 1))
        else:
            draw_box(surface, car.x, car.y, car.length, car.width, lift_z + 5, lift_z + car.height * 0.52, angle, car.color)
            center_x, center_y = local(car.x, car.y, angle, -car.length * 0.06, 0)
            roof_height = car.height * (0.85 if car.wreck else 1.0)
            draw_box(surface, center_x, center_y, car.length * 0.5, car.width * 0.84, lift_z + car.height * 0.52, lift_z + roof_height, angle, glass_color, top_color=shade(car.color, 1.15))

        if car.wreck:
            # dents and broken glass
            for dent_along, dent_across in ((car.length * 0.38, car.width * 0.2), (-car.length * 0.3, -car.width * 0.25), (car.length * 0.1, car.width * 0.3)):
                dent_x, dent_y = local(car.x, car.y, angle, dent_along, dent_across)
                pygame.draw.circle(surface, shade(car.color, 0.55), project(dent_x, dent_y, lift_z + car.height * 0.52), 4)
            return

        for offset_across in (-car.width * 0.3, car.width * 0.3):
            headlight_x, headlight_y = local(car.x, car.y, angle, car.length / 2, offset_across)
            pygame.draw.circle(surface, (255, 236, 160), project(headlight_x, headlight_y, lift_z + car.height * 0.33), 3)
            taillight_x, taillight_y = local(car.x, car.y, angle, -car.length / 2, offset_across)
            pygame.draw.circle(surface, (220, 40, 40), project(taillight_x, taillight_y, lift_z + car.height * 0.33), 3)

    def draw_drone(self, drone):
        surface = self.active_surface
        time_seconds = pygame.time.get_ticks() / 1000
        car = drone.car

        # cable down to the car roof
        if drone.state != "fly":
            # Cable bottom interpolates from drone height to roof height as cable_extension goes from 0 to 1.
            top = project(drone.x, drone.y, drone.z)
            roof_z = car.lift + car.height
            bottom_z = drone.z - (drone.z - roof_z) * drone.cable_extension
            pygame.draw.line(surface, (40, 40, 44), top, project(drone.x, drone.y, bottom_z), 2)
            hook = project(drone.x, drone.y, bottom_z)
            pygame.draw.circle(surface, (230, 190, 40), hook, 3)

        # arms and rotors
        for offset_x, offset_y in ((-22, -16), (22, -16), (-22, 16), (22, 16)):
            pygame.draw.line(surface, (50, 52, 58), project(drone.x, drone.y, drone.z + 6), project(drone.x + offset_x, drone.y + offset_y, drone.z + 8), 3)
            rotor_x, rotor_y = project(drone.x + offset_x, drone.y + offset_y, drone.z + 10)
            # Sine oscillates between -1 and 1; width = 16 + 3*sin(...) simulates spinning rotor blades.
            # sin ให้ค่าขึ้นลงระหว่าง -1 กับ 1 ใช้เปลี่ยนความกว้างใบพัดให้ดูเหมือนกำลังหมุน
            rotor_width = 16 + 3 * math.sin(time_seconds * 40 + offset_x)
            pygame.draw.ellipse(surface, (170, 176, 186), (rotor_x - rotor_width, rotor_y - 3, rotor_width * 2, 6), 1)
            pygame.draw.line(
                surface,
                (90, 94, 100),
                (rotor_x - rotor_width * math.cos(time_seconds * 50), rotor_y),
                (rotor_x + rotor_width * math.cos(time_seconds * 50), rotor_y),
                2
            )
        draw_box(surface, drone.x, drone.y, 28, 20, drone.z, drone.z + 9, 0, (240, 190, 40))
        draw_box(surface, drone.x, drone.y, 14, 10, drone.z + 9, drone.z + 13, 0, (40, 42, 48))
        if int(time_seconds * 4) % 2 == 0:
            pygame.draw.circle(surface, (255, 60, 50), project(drone.x + 14, drone.y + 10, drone.z + 6), 2)

    def draw_fire(self, fire):
        surface = self.active_surface
        time_seconds = pygame.time.get_ticks() / 1000
        for index in range(9):
            angle = index * 2.4
            radius = fire.radius * 0.55 * ((index % 3) / 3 + 0.3)
            flame_x = fire.x + math.cos(angle) * radius
            flame_y = fire.y + math.sin(angle) * radius * 0.6
            # Time-varying sine gives flickering flame height; remaining lifetime reduces the oscillation near expiry.
            height = 18 + 10 * math.sin(time_seconds * 9 + index) * min(1.0, fire.life / 2)
            base = project(flame_x, flame_y)
            tip = project(flame_x, flame_y, height + 14)
            pygame.draw.polygon(surface, (255, 120, 30), [(base[0] - 7, base[1]), (base[0] + 7, base[1]), tip])
            tip2 = project(flame_x, flame_y, height)
            pygame.draw.polygon(surface, (255, 220, 90), [(base[0] - 3, base[1]), (base[0] + 3, base[1]), tip2])

    def draw_floaters(self):
        for source_x, source_y, height_z, text, life_time, text_color in self.floating_messages:
            if not text:
                center_x, center_y = project(source_x, source_y)
                radius = 14 * (1 - life_time / 0.5) + 4
                pygame.draw.ellipse(self.active_surface, text_color, (center_x - radius, center_y - radius * 0.5, radius * 2, radius), 1)
                continue
            text_surface = self.font_bold.render(text, True, text_color)
            # Alpha = 255 * capped lifetime fraction makes text fade only near the end of its life.
            text_surface.set_alpha(int(255 * min(1.0, life_time / 0.5)))
            self.active_surface.blit(text_surface, text_surface.get_rect(center=project(source_x, source_y, height_z + 20)))

    def draw_impacts(self):
        if self.font_impact is None:
            self.font_impact = load_font(44, bold=True)
        for source_x, source_y, text, life_time, text_color, size_scale, rotation_degrees, offset_z in self.impact_messages:
            # Animation progress = 1 - remaining/initial lifetime: 0 at creation and 1 at expiry.
            # ความคืบหน้าเริ่มจาก 0 และเพิ่มถึง 1 เมื่อหมดอายุ ใช้ควบคุมขนาดและตำแหน่งข้อความ
            progress = 1 - life_time / 0.9
            # The label starts enlarged and quickly settles to its requested scale over the first sixth of its life.
            pop = size_scale * (1.7 - 0.7 * min(1.0, progress * 6))
            image = self.font_impact.render(text, True, text_color)
            outline = self.font_impact.render(text, True, (20, 16, 14))
            rendered_surface = pygame.Surface((image.get_width() + 6, image.get_height() + 6), pygame.SRCALPHA)
            for offset_x, offset_y in ((0, 3), (3, 0), (3, 6), (6, 3), (5, 5)):
                rendered_surface.blit(outline, (offset_x, offset_y))
            rendered_surface.blit(image, (3, 3))
            rendered_surface = pygame.transform.rotozoom(rendered_surface, rotation_degrees, pop * 0.6)
            rendered_surface.set_alpha(int(255 * min(1.0, life_time / 0.3)))
            self.active_surface.blit(rendered_surface, rendered_surface.get_rect(center=project(source_x, source_y, 50 + offset_z + progress * 30)))

    def draw_toasts(self):
        y_offset = 64
        for text, life_time, text_color in self.toast_messages:
            text_surface = self.font_bold.render(text, True, text_color)
            background = pygame.Surface((text_surface.get_width() + 24, text_surface.get_height() + 8), pygame.SRCALPHA)
            background.fill((15, 17, 22, int(200 * min(1.0, life_time / 0.4))))
            rectangle = background.get_rect(center=(SCREEN_WIDTH / 2, y_offset))
            self.active_surface.blit(background, rectangle)
            text_surface.set_alpha(int(255 * min(1.0, life_time / 0.4)))
            self.active_surface.blit(text_surface, text_surface.get_rect(center=rectangle.center))
            y_offset += rectangle.height + 4

    def roster_rectangles(self):
        result = []
        left_margin = 250
        for index, person in enumerate(self.people):
            # Five columns per row: modulo selects a column and floor division selects a row.
            rectangle = pygame.Rect(left_margin + (index % 5) * 54, HEADS_UP_DISPLAY_Y + 14 + (index // 5) * 60, 50, 54)
            result.append((person, rectangle))
        return result

    def draw_heads_up_display(self):
        surface = self.active_surface
        pygame.draw.rect(surface, PANEL_COLOR, (0, HEADS_UP_DISPLAY_Y, SCREEN_WIDTH, SCREEN_HEIGHT - HEADS_UP_DISPLAY_Y))
        pygame.draw.line(surface, PANEL_2_COLOR, (0, HEADS_UP_DISPLAY_Y), (SCREEN_WIDTH, HEADS_UP_DISPLAY_Y), 2)
        saved_count = sum(person.saved for person in self.people)
        dead_count = sum(not person.alive for person in self.people)
        target = self.current_level["target"]
        surface.blit(self.font_bold.render(self.current_level["name"], True, TEXT_COLOR), (18, HEADS_UP_DISPLAY_Y + 12))
        surface.blit(self.font_regular.render(f"ข้ามสำเร็จ  {saved_count} / {target}", True, GOOD_COLOR if saved_count >= target else TEXT_COLOR), (18, HEADS_UP_DISPLAY_Y + 44))
        surface.blit(self.font_regular.render(f"เสียชีวิต  {dead_count}", True, BAD_COLOR if dead_count else MUTED_COLOR), (18, HEADS_UP_DISPLAY_Y + 70))
        # divmod(total_seconds, 60) returns whole minutes and the leftover seconds.
        minutes, seconds = divmod(int(self.elapsed_time), 60)
        surface.blit(self.font_regular.render(f"เวลา  {minutes:02d}:{seconds:02d}", True, MUTED_COLOR), (18, HEADS_UP_DISPLAY_Y + 96))

        # target bar
        bar_x, bar_y, bar_width = 18, HEADS_UP_DISPLAY_Y + 124, 200
        pygame.draw.rect(surface, PANEL_2_COLOR, (bar_x, bar_y, bar_width, 8), border_radius=4)
        pygame.draw.rect(surface, GOOD_COLOR, (bar_x, bar_y, bar_width * min(1, saved_count / 10), 8), border_radius=4)
        # Convert the target survivor count into a horizontal fraction of the bar, whose full length means ten people.
        target_marker_x = bar_x + bar_width * target / 10
        pygame.draw.line(surface, ACCENT_COLOR, (target_marker_x, bar_y - 3), (target_marker_x, bar_y + 11), 2)

        # roster
        for person, rectangle in self.roster_rectangles():
            pygame.draw.rect(surface, PANEL_2_COLOR, rectangle, border_radius=6)
            if person.active and person in self.selected_people:
                pygame.draw.rect(surface, ACCENT_COLOR, rectangle.inflate(4, 4), 2, border_radius=7)
            if person.is_walking and person.active:
                pygame.draw.rect(surface, GOOD_COLOR, rectangle, 2, border_radius=6)
            if person is getattr(self, "hover", None):
                pygame.draw.rect(surface, (200, 200, 200), rectangle, 1, border_radius=6)
            person_color = mix(person.information["color"], (34, 28, 26), person.charring_level) if person.alive else (70, 70, 76)
            pygame.draw.rect(surface, person_color, (rectangle.centerx - 7, rectangle.y + 18, 14, 16), border_radius=4)
            pygame.draw.circle(surface, SKIN_COLOR if person.alive else (90, 90, 96), (rectangle.centerx, rectangle.y + 12), 6)
            key_label = self.font_tiny.render(str((person.index + 1) % 10), True, GOOD_COLOR if person.is_walking and person.active else MUTED_COLOR)
            surface.blit(key_label, (rectangle.x + 4, rectangle.y + 2))
            if person.alive and not person.saved:
                # Health fraction = current / maximum; multiplying bar width by this fraction sets the filled length.
                # ความยาวแถบเลือด = ความกว้างเต็ม × (พลังชีวิตปัจจุบัน / พลังชีวิตสูงสุด)
                fraction = max(0.0, person.health / person.maximum_health)
                bar_color = GOOD_COLOR if fraction > 0.6 else ACCENT_COLOR if fraction > 0.4 else BAD_COLOR
                pygame.draw.rect(surface, (16, 18, 22), (rectangle.x + 5, rectangle.y + 37, rectangle.width - 10, 4))
                pygame.draw.rect(surface, bar_color, (rectangle.x + 5, rectangle.y + 37, (rectangle.width - 10) * fraction, 4))
                if person.burn_time > 0:
                    pygame.draw.rect(surface, (255, 130, 40), rectangle, 2, border_radius=6)
            if person.fuel:
                pygame.draw.rect(surface, (206, 40, 32), (rectangle.right - 12, rectangle.y + 6, 7, 8))
            short_name_label = self.font_tiny.render(person.information["short_name"], True, MUTED_COLOR)
            surface.blit(short_name_label, short_name_label.get_rect(center=(rectangle.centerx, rectangle.bottom - 8)))
            if person.saved:
                pygame.draw.lines(surface, GOOD_COLOR, False, [(rectangle.x + 6, rectangle.y + 10), (rectangle.x + 10, rectangle.y + 14), (rectangle.x + 17, rectangle.y + 5)], 2)
            elif not person.alive:
                pygame.draw.line(surface, BAD_COLOR, (rectangle.x + 8, rectangle.y + 8), (rectangle.right - 8, rectangle.y + 40), 3)
                pygame.draw.line(surface, BAD_COLOR, (rectangle.right - 8, rectangle.y + 8), (rectangle.x + 8, rectangle.y + 40), 3)
            elif person.information["cooldown"] > 1 and person.cooldown > 0:
                fraction = person.cooldown / person.information["cooldown"]
                pygame.draw.rect(surface, (90, 94, 100), (rectangle.x + 4, rectangle.bottom - 3, (rectangle.width - 8) * fraction, 2))

        # info about the person under the mouse
        left_information = 538
        hover_person = getattr(self, "hover", None)
        if hover_person is None:
            mouse_x, mouse_y = pygame.mouse.get_pos()
            hover_person = next((roster_person for roster_person, roster_rectangle in self.roster_rectangles() if roster_rectangle.collidepoint(mouse_x, mouse_y)), None)

        if hover_person and hover_person.alive:
            surface.blit(
                self.font_bold.render(
                    f"{(hover_person.index + 1) % 10}. {hover_person.information['name']}" + ("  · ถังน้ำมัน!" if hover_person.fuel else ""),
                    True,
                    BAD_COLOR if hover_person.fuel else ACCENT_COLOR
                ),
                (left_information, HEADS_UP_DISPLAY_Y + 12)
            )
            if hover_person.fuel:
                state_text = "ปลอดภัยแล้ว" if hover_person.saved else "กำลังไฟไหม้!"
            elif hover_person.down_time > 0:
                state_text = "ล้มอยู่"
            elif hover_person.injured:
                state_text = "บาดเจ็บหนัก (เดินช้า)"
            elif hover_person.is_walking:
                state_text = "กำลังเดิน"
            else:
                state_text = "รออยู่"
            fraction = max(0.0, hover_person.health / hover_person.maximum_health)
            bar_color = GOOD_COLOR if fraction > 0.6 else ACCENT_COLOR if fraction > 0.4 else BAD_COLOR
            surface.blit(self.font_small.render(f"HP {int(max(0, hover_person.health))}/{hover_person.maximum_health}  ·  {state_text}", True, bar_color), (left_information, HEADS_UP_DISPLAY_Y + 40))
            surface.blit(self.font_regular.render(hover_person.information["skill_description"], True, TEXT_COLOR), (left_information, HEADS_UP_DISPLAY_Y + 62))
            if hover_person.information["cooldown"] > 1 and not hover_person.saved:
                ready = hover_person.cooldown <= 0
                cooldown_text = "คลิกขวา = ใช้ความสามารถ (พร้อม)" if ready else f"ใช้ได้อีกใน {hover_person.cooldown:0.1f} วินาที"
                surface.blit(self.font_small.render(cooldown_text, True, GOOD_COLOR if ready else MUTED_COLOR), (left_information + 300, HEADS_UP_DISPLAY_Y + 40))
        else:
            surface.blit(self.font_bold.render("คลิกที่คน = เดินข้าม / หยุด", True, ACCENT_COLOR), (left_information, HEADS_UP_DISPLAY_Y + 12))
            surface.blit(self.font_regular.render("คลิกขวาที่คน = ใช้ความสามารถ", True, TEXT_COLOR), (left_information, HEADS_UP_DISPLAY_Y + 40))
            surface.blit(self.font_small.render("ชี้เมาส์ที่คนเพื่อดู HP และความสามารถ", True, MUTED_COLOR), (left_information, HEADS_UP_DISPLAY_Y + 66))

        help_text1 = "Shift+คลิก = เลือกกลุ่ม / คลิกซ้ำเอาออก | ปล่อย Shift = เดิน"
        selected_count = sum(person.active for person in self.selected_people)
        help_text2 = f"เลือก {selected_count} คน | Esc = ล้าง | G = เดินทุกคน | Space = หยุด | P = พัก | R = ใหม่"
        surface.blit(self.font_small.render(help_text1, True, MUTED_COLOR), (left_information, HEADS_UP_DISPLAY_Y + 104))
        surface.blit(self.font_small.render(help_text2, True, MUTED_COLOR), (left_information, HEADS_UP_DISPLAY_Y + 124))

    def center_card(self, lines, supporting_lines=None, width=520):
        surface = self.active_surface
        shade_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        shade_surface.fill((10, 12, 16, 150))
        surface.blit(shade_surface, (0, 0))
        # Card height combines fixed padding, title/body line spacing, and optional supporting-line space.
        card_height = 70 + 34 * (len(lines) - 1) + (len(supporting_lines) * 26 + 20 if supporting_lines else 0) + 10
        rectangle = pygame.Rect(0, 0, width, card_height)
        rectangle.center = (SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2 - 40)
        pygame.draw.rect(surface, PANEL_COLOR, rectangle, border_radius=12)
        pygame.draw.rect(surface, PANEL_2_COLOR, rectangle, 2, border_radius=12)
        current_y = rectangle.y + 24
        for index, line in enumerate(lines):
            font = self.font_heading if index == 0 else self.font_regular
            text = font.render(line, True, ACCENT_COLOR if index == 0 else TEXT_COLOR)
            surface.blit(text, text.get_rect(midtop=(rectangle.centerx, current_y)))
            current_y += 44 if index == 0 else 30
        if supporting_lines:
            current_y += 8
            for line in supporting_lines:
                text = self.font_small.render(line, True, MUTED_COLOR)
                surface.blit(text, (rectangle.x + 34, current_y))
                current_y += 26
        return rectangle

    def draw_title(self):
        self.center_card(
            ["ข้ามถนน", "พาคนข้ามทางม้าลายไปฝั่งปลอดภัยให้ได้มากที่สุด",
             f"ต้องรอดอย่างน้อย {self.current_level['target']} จาก 10 คน"],
            supporting_lines=["ตำรวจจราจร – ยกป้ายหยุดรถทีละเลน",
                 "นักวิ่ง – วิ่งเร็วชั่วครู่      คุณยาย – รถใกล้ ๆ ชะลอ",
                 "เด็ก – อยู่คนเดียวจะตกใจ      คนแข็งแรง – แบกคนอื่นได้",
                 "คนถือถังน้ำมัน (สีแดง) – ถ้าโดนชนจะระเบิด",
                 "ทุกคนมี HP: โดนรถชนจะกระเด็น ล้มลง แล้วลุกขึ้นมาเดินกะเผลก",
                 "ไฟไหม้จะลด HP ต่อเนื่องจนกว่าไฟจะดับ",
                 "คราบเลือดทำให้รถลื่นไปชนกัน แล้วโดรนจะมายกซากออก",
                 "คลิกที่คน = เดิน/หยุด   คลิกขวา = ใช้ความสามารถ",
                 "Shift+คลิกเลือกหลายคน ปล่อย Shift = ข้ามพร้อมกัน",
                 "คลิกซ้ำขณะกด Shift = เอาออกจากกลุ่ม   Esc = ล้างกลุ่ม",
                 "คลิกหรือกดปุ่มใดก็ได้เพื่อเริ่ม"],
            width=560
        )

    def draw_end(self):
        saved_count = sum(person.saved for person in self.people)
        if self.state == "win":
            stars = 3 if saved_count == 10 else 2 if saved_count >= 8 else 1
            minutes, seconds = divmod(int(self.elapsed_time), 60)
            rectangle = self.center_card(
                ["ผ่านด่าน!", f"รอด {saved_count} / 10 คน   ·   เวลา {minutes:02d}:{seconds:02d}", " "],
                supporting_lines=["N = ด่านถัดไป      R = เล่นด่านนี้อีกครั้ง"]
            )
            for star_index in range(3):
                center_x = rectangle.centerx + (star_index - 1) * 46
                center_y = rectangle.y + 116
                # A five-point star uses ten vertices, alternating outer radius 16 and inner radius 7 at pi/5 intervals.
                # ดาวห้าแฉกใช้สิบจุด โดยสลับรัศมียาวกับสั้นเพื่อสร้างปลายแฉกและร่องดาว
                points = [
                    (center_x + (16 if vertex % 2 == 0 else 7) * math.cos(-math.pi / 2 + vertex * math.pi / 5),
                     center_y + (16 if vertex % 2 == 0 else 7) * math.sin(-math.pi / 2 + vertex * math.pi / 5))
                    for vertex in range(10)
                ]
                pygame.draw.polygon(self.active_surface, ACCENT_COLOR if star_index < stars else PANEL_2_COLOR, points)
        else:
            self.center_card(
                ["ไม่ผ่าน", f"คนที่เหลือไม่พอ (ต้องรอด {self.current_level['target']} คน)"],
                supporting_lines=["R = ลองอีกครั้ง"]
            )

    def draw_person(self, person, carrier=None):
        """Stick-figure-in-2.5D: every body part is placed along a body axis that can tilt,
        so the same code draws standing, running, falling, lying, carried and dead people."""
        surface = self.active_surface
        if carrier:
            base_x, base_y, z_base = carrier.x + 2, carrier.y, 30
        else:
            base_x, base_y, z_base = person.x, person.y, 0
        person_kind = person.kind
        scale = 0.76 if person_kind == "kid" else 1.0
        # Blend clothing and skin toward dark burnt colors as charring_level increases from 0 to 1.
        body_color = mix(person.information["color"], (34, 28, 26), person.charring_level)
        skin_color = mix(SKIN_COLOR, (44, 34, 30), person.charring_level)
        if person.hurt_time > 0 and int(person.hurt_time * 18) % 2 == 0:          # hit flash
            body_color = mix(body_color, (255, 80, 70), 0.65)
            skin_color = mix(skin_color, (255, 80, 70), 0.65)
        pose_angle = math.pi / 2 if carrier else person.pose
        is_lying = pose_angle > 0.6
        facing_direction = person.fall_direction if is_lying else person.facing
        is_alive = person.alive and not is_lying and not carrier
        is_moving = is_alive and person.moving
        # A sine wave controls walking. Absolute sine bobs the body upward; signed sine swings opposing limbs.
        phase = person.walk_phase * 10
        if is_moving and person.injured:                                    # limp: uneven bob, one stiff leg
            bob_height = max(0.0, math.sin(phase)) * 4
        else:
            bob_height = abs(math.sin(phase)) * 2 if is_moving else 0
        swing_amount = math.sin(phase) * 4 if is_moving else 0
        if person.slip_time > 0 and is_alive:
            swing_amount = 6
        sine_angle, cosine_angle = math.sin(pose_angle), math.cos(pose_angle)

        # Tilt the body axis: sin(pose) moves height sideways and cos(pose) keeps the upright portion.
        # At pose 0 the body stands; at pi/2 its height becomes horizontal displacement.
        # เมื่อมุมเอียงเพิ่ม ความสูงจะเปลี่ยนเป็นระยะทางด้านข้าง จึงใช้สูตรเดียววาดได้ทั้งยืนและนอน
        def project_point(height, offset=0.0):
            return project(
                base_x + facing_direction * sine_angle * height + offset * cosine_angle,
                base_y + offset * sine_angle * 0.6,
                z_base + cosine_angle * (height + bob_height)
            )

        body_width = 18 if person_kind == "strong" else 13 * scale
        # legs
        for side in (-1, 1):
            is_stiff = person.injured and side == 1 and is_moving
            swing_component = swing_amount * side * (0.2 if is_stiff else 0.6)
            pygame.draw.line(
                surface,
                mix((44, 46, 58), (30, 26, 24), person.charring_level),
                project_point(0, side * 3 * scale + swing_component),
                project_point(11 * scale, side * 3 * scale),
                3
            )
        # torso (capsule)
        hip, neck = project_point(11 * scale), project_point(25 * scale)
        pygame.draw.line(surface, shade(body_color, 0.6), hip, neck, int(body_width) + 2)
        pygame.draw.line(surface, body_color, hip, neck, int(body_width))
        for point in (hip, neck):
            pygame.draw.circle(surface, body_color, point, int(body_width / 2))
        if person.injured and person.alive:
            pygame.draw.circle(surface, BLOOD_HIGHLIGHT, project_point(18 * scale, 2), 3)

        # arms
        time_seconds = pygame.time.get_ticks() / 1000
        for side in (-1, 1):
            shoulder = project_point(23 * scale, side * (body_width / 2 + 1))
            if person.burn_time > 0 and is_alive:                           # flailing while on fire
                hand = project_point(36 * scale + 3 * math.sin(time_seconds * 20 + side), side * (body_width / 2 + 6))
            elif is_lying:
                hand = project_point(24 * scale, side * (body_width / 2 + 9))
            else:
                hand = project_point(13 * scale, side * (body_width / 2 + 2) - swing_amount * side * 0.5)
            pygame.draw.line(surface, shade(body_color, 0.8), shoulder, hand, 3)

        # head
        head = project_point(33 * scale)
        head_radius = int(7 * scale)
        if person_kind == "grandma":
            pygame.draw.circle(surface, mix((210, 210, 214), (40, 36, 34), person.charring_level), project_point(36 * scale, -4 * facing_direction), 5)
        pygame.draw.circle(surface, skin_color, head, head_radius)
        pygame.draw.circle(surface, shade(skin_color, 0.7), head, head_radius, 1)
        if person_kind == "warden":
            pygame.draw.circle(surface, mix((24, 50, 120), (30, 26, 24), person.charring_level), project_point(39 * scale), 5)
        elif person_kind == "runner":
            pygame.draw.line(surface, (220, 40, 40), project_point(36 * scale, -head_radius), project_point(36 * scale, head_radius), 2)
        elif person_kind == "kid":
            pygame.draw.circle(surface, (60, 40, 30), project_point(38 * scale), 4)
        if person.injured and person.alive:                                    # head bandage
            pygame.draw.line(surface, (240, 240, 240), project_point(35 * scale, -head_radius), project_point(35 * scale, head_radius), 3)
        if not person.alive:                                              # x_x
            for delta_x in (-3, 3):
                center_x, center_y = head[0] + delta_x, head[1] - 1
                pygame.draw.line(surface, (40, 30, 30), (center_x - 2, center_y - 2), (center_x + 2, center_y + 2), 1)
                pygame.draw.line(surface, (40, 30, 30), (center_x - 2, center_y + 2), (center_x + 2, center_y - 2), 1)

        # held items
        if person.fuel and not is_lying:
            fuel_x = base_x + 10 * person.facing
            draw_box(surface, fuel_x, base_y + 2, 7, 6, z_base + 6, z_base + 17, 0, (206, 40, 32))
            pygame.draw.line(surface, (40, 40, 40), project(fuel_x, base_y + 2, z_base + 17), project(fuel_x, base_y + 2, z_base + 20), 2)
        if person_kind == "grandma" and is_alive:
            center_x = head[0] + 10 * person.facing
            pygame.draw.line(surface, (120, 80, 40), (center_x, project_point(20)[1]), (center_x + 2 * person.facing, project_point(0)[1]), 2)
        if person_kind == "warden" and person.sign_time > 0 and is_alive:
            point_x, point_y = neck[0] + body_width / 2 + 4, neck[1]
            pygame.draw.line(surface, (90, 90, 90), (point_x, point_y + 14), (point_x, point_y - 22), 2)
            # An octagon uses eight points spaced pi/4 radians apart; pi/8 rotates it to give the stop sign flat edges.
            # ป้ายหยุดมีแปดมุม วางแต่ละจุดห่างกัน 45 องศารอบวงกลม
            sign_points = [
                (point_x + 9 * math.cos(math.pi / 8 + vertex_index * math.pi / 4), point_y - 30 + 9 * math.sin(math.pi / 8 + vertex_index * math.pi / 4))
                for vertex_index in range(8)
            ]
            pygame.draw.polygon(surface, (210, 30, 30), sign_points)
            pygame.draw.polygon(surface, WHITE, sign_points, 1)

        # flames on the body
        if person.burn_time > 0 and person.alive:
            for index, height in enumerate((6, 15, 24, 33)):
                flame_x, flame_y = project_point(height * scale, (index % 2 * 2 - 1) * 4)
                flame_height = 10 + 6 * math.sin(time_seconds * 14 + index * 1.7)
                pygame.draw.polygon(surface, (255, 120, 30), [(flame_x - 5, flame_y), (flame_x + 5, flame_y), (flame_x + 1, flame_y - flame_height)])
                pygame.draw.polygon(surface, (255, 220, 90), [(flame_x - 2, flame_y), (flame_x + 2, flame_y), (flame_x, flame_y - flame_height * 0.55)])

        if carrier or not person.alive:
            return

        # status above the head
        status_top = head[1] - head_radius - 8
        if person.down_time > 0:                                             # dizzy stars
            for index in range(3):
                # Three dizzy stars are separated by one third of a full turn; cosine/sine move them around the head.
                spin_angle = time_seconds * 6 + index * math.tau / 3
                pygame.draw.circle(surface, ACCENT_COLOR, (head[0] + math.cos(spin_angle) * 10, head[1] - 10 + math.sin(spin_angle) * 3), 2)
        elif person.panic:
            warning_text = self.font_bold.render("!", True, BAD_COLOR)
            surface.blit(warning_text, warning_text.get_rect(center=(head[0], status_top - 10)))
        elif person.saved:
            pygame.draw.lines(surface, GOOD_COLOR, False, [(head[0] - 5, status_top), (head[0] - 1, status_top + 4), (head[0] + 6, status_top - 4)], 2)
        elif person.is_walking:                                              # walking: green arrow up
            pygame.draw.polygon(surface, GOOD_COLOR, [(head[0] - 5, status_top - 8), (head[0] + 5, status_top - 8), (head[0], status_top - 15)])
        else:                                                                # waiting: pause bars
            pygame.draw.rect(surface, ACCENT_COLOR, (head[0] - 5, status_top - 15, 3, 8))
            pygame.draw.rect(surface, ACCENT_COLOR, (head[0] + 2, status_top - 15, 3, 8))

        show_bar = not person.saved and (person.health < person.maximum_health or person is getattr(self, "hover", None))
        if show_bar:
            fraction = max(0.0, person.health / person.maximum_health)
            bar_width = 28
            bar_x, bar_y = head[0] - bar_width / 2, status_top - 2
            pygame.draw.rect(surface, (20, 20, 24), (bar_x - 1, bar_y - 1, bar_width + 2, 6))
            health_color = GOOD_COLOR if fraction > 0.6 else ACCENT_COLOR if fraction > 0.4 else BAD_COLOR
            pygame.draw.rect(surface, health_color, (bar_x, bar_y, bar_width * fraction, 4))
            if person is getattr(self, "hover", None):
                number_surface = self.font_tiny.render(str((person.index + 1) % 10), True, TEXT_COLOR)
                surface.blit(number_surface, number_surface.get_rect(midright=(bar_x - 3, bar_y + 2)))

        if not person.saved and person.information["cooldown"] > 1:
            pygame.draw.circle(surface, GOOD_COLOR if person.cooldown <= 0 else (90, 94, 100), (head[0] + 18, status_top), 3)

        if person.tired > 0:
            tired_text = self.font_small.render("เหนื่อย", True, MUTED_COLOR)
            surface.blit(tired_text, tired_text.get_rect(center=(head[0], status_top - 12)))
