"""Unit tests for core simulation behavior.

Run with: python -m unittest discover -s tests -v
"""

import sys
import unittest
from unittest.mock import MagicMock

# Simulation imports Pygame through geometry, but these tests exercise no drawing.
try:
    import pygame  # noqa: F401
except ModuleNotFoundError:
    sys.modules["pygame"] = MagicMock()

from entities import Particle, Person
from simulation import GameSimulation


class FakeSurface:
    def fill(self, *args, **kwargs):
        pass


class SimulationHarness(GameSimulation):
    """Minimal GameSimulation host without initializing the Pygame window."""

    def __init__(self):
        self.state = "lose"
        self.paused = False
        self.end_screen_timer = 0.0
        self.people = []
        self.blood_puddles = []
        self.fires = []
        self.particles = []
        self.impact_messages = []
        self.floating_messages = []
        self.toast_messages = []
        self.active_surface_shake_strength = 0.0
        self.flash_intensity = 0.0
        self.skid_mark_fade_timer = 0.0
        self.skid_mark_surface = FakeSurface()
        self.float_text_calls = []
        self.toast_calls = []

    def update_traffic(self, dt, prewarm=False):
        pass

    def animate_person(self, person, dt):
        pass

    def float_text(self, x, y, message, color):
        self.float_text_calls.append((x, y, message, color))

    def toast(self, message, color=None):
        self.toast_calls.append((message, color))


class ParticleSimulationTests(unittest.TestCase):
    def test_particle_stores_constructor_vy_as_lateral_speed(self):
        particle = Particle(
            x=10, y=20, z=100,
            vx=3, vy=-7, vz=0,
            col=(255, 255, 255), size=2, life=2, grav=0,
        )

        self.assertEqual(particle.vx, 3)
        self.assertEqual(particle.lateral_speed, -7)

    def test_update_moves_particle_on_independent_x_and_y_velocities(self):
        game = SimulationHarness()
        particle = Particle(
            x=10, y=20, z=100,
            vx=4, vy=-6, vz=0,
            col=(255, 255, 255), size=2, life=2, grav=0,
        )
        game.particles.append(particle)

        game.update(0.5)

        self.assertAlmostEqual(particle.x, 12)
        self.assertAlmostEqual(particle.y, 17)
        self.assertAlmostEqual(particle.life, 1.5)

    def test_update_removes_particle_after_its_lifetime_expires(self):
        game = SimulationHarness()
        particle = Particle(
            x=10, y=20, z=100,
            vx=0, vy=0, vz=0,
            col=(255, 255, 255), size=2, life=0.05, grav=0,
        )
        game.particles.append(particle)

        game.update(0.1)

        self.assertNotIn(particle, game.particles)


class PersonSimulationTests(unittest.TestCase):
    def test_save_marks_person_safe_and_stops_movement(self):
        game = SimulationHarness()
        person = Person("citizen", 500, 500, 0)
        person.go = True
        person.panic = True
        game.people = [person]

        game.save(person)

        self.assertTrue(person.saved)
        self.assertFalse(person.go)
        self.assertFalse(person.panic)
        self.assertEqual(len(person.path), 1)
        self.assertEqual(person.path[0][1], 40)
        self.assertEqual(len(game.float_text_calls), 1)

    def test_saving_carrier_also_saves_the_person_being_carried(self):
        game = SimulationHarness()
        carrier = Person("strong", 500, 500, 0)
        passenger = Person("citizen", 510, 500, 1)
        carrier.carrying = passenger
        passenger.carried_by = carrier
        game.people = [carrier, passenger]

        game.save(carrier)

        self.assertTrue(carrier.saved)
        self.assertTrue(passenger.saved)
        self.assertIsNone(carrier.carrying)
        self.assertIsNone(passenger.carried_by)


class DamageSimulationTests(unittest.TestCase):
    def test_car_damage_reduces_hp_and_creates_blood_puddle(self):
        game = SimulationHarness()
        person = Person("citizen", 500, 500, 0)
        game.people = [person]

        game.damage(person, 20, "car")

        self.assertEqual(person.hp, 80)
        self.assertEqual(person.hurt_t, 0.4)
        self.assertEqual(len(game.blood_puddles), 1)
        self.assertEqual(len(game.particles), 8)
        self.assertEqual(len(game.toast_calls), 1)

    def test_lethal_fire_damage_marks_person_dead(self):
        game = SimulationHarness()
        person = Person("citizen", 500, 500, 0)
        person.hp = 5
        game.people = [person]

        game.damage(person, 10, "fire")

        self.assertEqual(person.hp, 0)
        self.assertFalse(person.alive)
        self.assertEqual(person.death_kind, "fire")
        self.assertFalse(person.go)


if __name__ == "__main__":
    unittest.main()
