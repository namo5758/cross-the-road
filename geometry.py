"""Coordinate transforms and drawing primitives shared by the game."""

import math
import pygame

from game_config import (
    CROSSING_START_X,
    CROSSING_END_X,
    HEIGHT_SCALE,
    LANE_HEIGHT,
    ORIGIN_Y,
    ROAD_BOTTOM,
    ROAD_TOP,
    VERTICAL_SCALE,
)


# Keep a number inside an inclusive range: below minimum becomes minimum, above maximum becomes maximum.
# จำกัดค่าให้อยู่ในช่วง เช่น clamp(120, 0, 100) จะได้ 100 เพื่อไม่ให้หลุดขอบ
def clamp(value, minimum_value, maximum_value):
    return minimum_value if value < minimum_value else maximum_value if value > maximum_value else value


# Brightness adjustment: multiply each color channel by factor, then limit it to 0..255.
# A factor below 1 darkens the color; above 1 brightens it.
# คูณช่องสีด้วย 0.5 จะมืดลงครึ่งหนึ่ง และจำกัดผลลัพธ์ไม่ให้เกินช่วง 0 ถึง 255
def shade(color, factor):
    return tuple(max(0, min(255, int(channel * factor))) for channel in color[:3])


# Linear color interpolation: result = first + (second - first) * blend_ratio.
# Ratio 0 keeps the first color; ratio 1 uses the second color.
# ผสมสีตามสัดส่วน: 0 คือสีแรก 1 คือสีที่สอง และ 0.5 คือค่ากึ่งกลางของแต่ละช่องสี
def mix(first_color, second_color, blend_ratio):
    return tuple(int(first_color[index] + (second_color[index] - first_color[index]) * blend_ratio) for index in range(3))


# World-to-screen formula: screen_y = origin + ground_y * depth_scale - height * height_scale.
# Screen y grows downward, so subtracting height makes objects appear taller.
# แกน y บนจอเพิ่มลงด้านล่าง จึงต้องลบค่าความสูงเพื่อวาดวัตถุให้สูงขึ้น
def project(world_x, world_y, world_z=0.0):
    return world_x, ORIGIN_Y + world_y * VERTICAL_SCALE - world_z * HEIGHT_SCALE


# Undo the ground projection by removing the offset and dividing by the depth scale.
# This inverse assumes world_z = 0; a screen point alone cannot recover height.
# แปลงตำแหน่งเมาส์กลับเป็นตำแหน่งบนพื้น โดยสมมติว่าความสูงเป็นศูนย์
def unproject(screen_x, screen_y):
    return screen_x, (screen_y - ORIGIN_Y) / VERTICAL_SCALE


# Adding 0.5 selects the middle of a zero-based lane instead of its upper edge.
# เลนเริ่มนับจาก 0 การบวกครึ่งเลนทำให้ได้จุดกึ่งกลาง ไม่ใช่เส้นขอบเลน
def lane_center(lane_index):
    return ROAD_TOP + LANE_HEIGHT * (lane_index + 0.5)


# Floor division counts complete lane heights below ROAD_TOP; outside the road returns None.
def lane_of(world_y):
    return int((world_y - ROAD_TOP) // LANE_HEIGHT) if ROAD_TOP <= world_y < ROAD_BOTTOM else None


# Test whether a ground y coordinate is strictly between the two curbs.
def in_road(world_y):
    return ROAD_TOP < world_y < ROAD_BOTTOM


# Test whether an x coordinate lies within the zebra crossing, including its edges.
def in_band(world_x):
    return CROSSING_START_X <= world_x <= CROSSING_END_X


# Rotate each rectangle corner around its center using the 2D rotation matrix.
# x_new = x*cos(angle) - y*sin(angle); y_new = x*sin(angle) + y*cos(angle).
# Angles are in radians; pi radians is half a turn.
# หมุนจุดด้วย sin และ cos โดยมุมใช้เรเดียน เช่น pi เท่ากับ 180 องศา
def box_corners(center_x, center_y, length, width, angle):
    cosine_angle, sine_angle = math.cos(angle), math.sin(angle)
    half_length = length / 2
    half_width = width / 2
    return [
        (center_x + local_x * cosine_angle - local_y * sine_angle,
         center_y + local_x * sine_angle + local_y * cosine_angle)
        for local_x, local_y in (
            (half_length, half_width),
            (-half_length, half_width),
            (-half_length, -half_width),
            (half_length, -half_width)
        )
    ]


# Rotate a position relative to an object, then add the object center to obtain world coordinates.
def local(center_x, center_y, angle, local_x, local_y):
    cosine_angle, sine_angle = math.cos(angle), math.sin(angle)
    return center_x + local_x * cosine_angle - local_y * sine_angle, center_y + local_x * sine_angle + local_y * cosine_angle


def draw_box(surface, center_x, center_y, length, width, z_bottom, z_top, angle, color, top_color=None, outline=True):
    """Draw an extruded box, including camera-facing side faces and its top."""
    corners = box_corners(center_x, center_y, length, width, angle)
    for index in range(4):
        corner_start = corners[index]
        # Modulo wraps the final corner back to corner 0, closing the rectangle.
        corner_end = corners[(index + 1) % 4]
        # Swapping edge components and negating one creates a perpendicular direction (a face normal).
        normal_x = corner_end[1] - corner_start[1]
        normal_y = -(corner_end[0] - corner_start[0])
        midpoint_x = (corner_start[0] + corner_end[0]) / 2 - center_x
        midpoint_y = (corner_start[1] + corner_end[1]) / 2 - center_y
        # The dot product tests whether the normal points outward; reverse it if it points inward.
        # ผลคูณจุดใช้ตรวจทิศของเวกเตอร์ ถ้าหันเข้าด้านในก็กลับเครื่องหมายให้ชี้ออก
        if normal_x * midpoint_x + normal_y * midpoint_y < 0:
            normal_x, normal_y = -normal_x, -normal_y
        # hypot(x, y) = sqrt(x*x + y*y). Dividing by it produces a unit direction.
        # Using 1 for a zero length avoids division by zero.
        # หารแต่ละแกนด้วยระยะรวมเพื่อให้เหลือเฉพาะทิศทาง และป้องกันการหารด้วยศูนย์
        normal_length = math.hypot(normal_x, normal_y) or 1
        normal_x, normal_y = normal_x / normal_length, normal_y / normal_length
        # Only draw side faces pointing toward the camera; the normal also controls their shading.
        if normal_y > 0.01:
            quadrilateral = [
                project(corner_start[0], corner_start[1], z_bottom),
                project(corner_end[0], corner_end[1], z_bottom),
                project(corner_end[0], corner_end[1], z_top),
                project(corner_start[0], corner_start[1], z_top)
            ]
            pygame.draw.polygon(surface, shade(color, 0.64 + 0.16 * normal_x), quadrilateral)
    top_polygon = [project(corner[0], corner[1], z_top) for corner in corners]
    pygame.draw.polygon(surface, top_color or shade(color, 1.1), top_polygon)
    if outline:
        pygame.draw.polygon(surface, shade(color, 0.45), top_polygon, 1)
