"""Coordinate transforms and drawing primitives shared by the game."""

import math

import pygame

from game_config import CW_X0, CW_X1, HS, K, LANE_H, OY, ROAD_BOT, ROAD_TOP


def clamp(value, low, high):
    return low if value < low else high if value > high else value


def shade(color, factor):
    return tuple(max(0, min(255, int(value * factor))) for value in color[:3])


def mix(first, second, amount):
    return tuple(int(first[index] + (second[index] - first[index]) * amount) for index in range(3))


def proj(x, y, z=0.0):
    return x, OY + y * K - z * HS


def unproj(screen_x, screen_y):
    return screen_x, (screen_y - OY) / K


def lane_center(index):
    return ROAD_TOP + LANE_H * (index + 0.5)


def lane_of(y):
    return int((y - ROAD_TOP) // LANE_H) if ROAD_TOP <= y < ROAD_BOT else None


def in_road(y):
    return ROAD_TOP < y < ROAD_BOT


def in_band(x):
    return CW_X0 <= x <= CW_X1


def box_corners(cx, cy, length, width, angle):
    cos_angle, sin_angle = math.cos(angle), math.sin(angle)
    return [(cx + local_x * cos_angle - local_y * sin_angle,
             cy + local_x * sin_angle + local_y * cos_angle)
            for local_x, local_y in ((length / 2, width / 2), (-length / 2, width / 2),
                                     (-length / 2, -width / 2), (length / 2, -width / 2))]


def local(cx, cy, angle, local_x, local_y):
    cos_angle, sin_angle = math.cos(angle), math.sin(angle)
    return cx + local_x * cos_angle - local_y * sin_angle, cy + local_x * sin_angle + local_y * cos_angle


def draw_box(surface, cx, cy, length, width, z0, z1, angle, color, top=None, outline=True):
    """Draw an extruded box, including camera-facing side faces and its top."""
    points = box_corners(cx, cy, length, width, angle)
    for index in range(4):
        first, second = points[index], points[(index + 1) % 4]
        normal_x, normal_y = second[1] - first[1], -(second[0] - first[0])
        midpoint_x, midpoint_y = (first[0] + second[0]) / 2 - cx, (first[1] + second[1]) / 2 - cy
        if normal_x * midpoint_x + normal_y * midpoint_y < 0:
            normal_x, normal_y = -normal_x, -normal_y
        normal_length = math.hypot(normal_x, normal_y) or 1
        normal_x, normal_y = normal_x / normal_length, normal_y / normal_length
        if normal_y > 0.01:
            quad = [proj(first[0], first[1], z0), proj(second[0], second[1], z0),
                    proj(second[0], second[1], z1), proj(first[0], first[1], z1)]
            pygame.draw.polygon(surface, shade(color, 0.64 + 0.16 * normal_x), quad)
    top_polygon = [proj(point[0], point[1], z1) for point in points]
    pygame.draw.polygon(surface, top or shade(color, 1.1), top_polygon)
    if outline:
        pygame.draw.polygon(surface, shade(color, 0.45), top_polygon, 1)
