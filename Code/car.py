# =============================================================================
# car.py -- the simulated car: kinematics, LiDAR sensing, rendering.
#
# One Car per driver (player, AI opponent, or one of the 30 evolution
# agents). Every car shares the same constant speed and steering authority;
# the only difference between them is who produces the steering signal.
# =============================================================================
import math
import pygame
from settings import (
    SPRITE_RED_F1, SPRITE_YELLOW_F1, SPRITE_BLACK_F1, SPRITE_GREEN_F1,
    COLOR_GOLD_AURA, COLOR_RAY_SAFE, COLOR_RAY_ALERT, COLOR_WRECK,
    font_subtitle, MAX_RAY_LENGTH
)

class Car:
    """A single race car: 7-ray LiDAR, constant-speed kinematics, kill rules.

    Fitness and lap bookkeeping also live here, but they are written by the
    track (compute_fitness / update_race_events), not by the car. The car
    only owns the state and the rules that end its run: stall, donut,
    reverse travel and collision.
    """
    def __init__(self, sprite_type="black", spawn_index=0, name="Driver", is_last_champion=False):
        self.name = name
        self.spawn_index = spawn_index
        self.sprite_type = sprite_type
        self.is_last_champion = is_last_champion
        # 7-Ray LiDAR: Front & sharp angled rays for early apex detection
        self.sensor_angles = [-90.0, -50.0, -20.0, 0.0, 20.0, 50.0, 90.0]
        self.sensor_readings = [1.0] * 7
        self.ray_endpoints = []
        # Lap counter tracking (updated by track.compute_fitness; HUD display
        # only, does not influence physics or the fitness formula)
        self.checkpoints_passed = 0
        self.last_closest_idx = 0
        # Figure-8 race events (updated by Figure8CircuitTrack.update_race_events)
        self.reverse_accum = 0.0   # accumulated reverse travel, px (killed at threshold)
        self.gates_hit = set()     # gates passed since the last start-line pass
        self.gate_credits = 0      # total gate passages (fitness gradient only)
        self.line_credits = 0      # start-line passes holding BOTH gates == full laps
        self.shortcut_credits = 0  # start-line passes holding ONE gate == single loop
        self.line_prev_along = None  # signed offset from the finish-line plane, prev frame
        self._f8_real_idx = 0      # true nearest path idx, cached per frame
        self._setup_livery()

    def _setup_livery(self):
        """Pick sprite + name-tag colour from this car's role in the field.

        Red = last generation's champion, yellow = current leader,
        green = showcase replay, black = ordinary evolution agent.
        """
        if self.sprite_type == "green":
            self.base_sprite, self.tag_color = SPRITE_GREEN_F1, (80, 200, 120)
        elif self.is_last_champion or self.sprite_type == "red":
            self.base_sprite, self.tag_color = SPRITE_RED_F1, (255, 107, 107)
        elif self.sprite_type == "yellow":
            self.base_sprite, self.tag_color = SPRITE_YELLOW_F1, (241, 196, 15)
        else:
            self.base_sprite, self.tag_color = SPRITE_BLACK_F1, (180, 190, 200)

    def reset(self, track, curriculum_idx=None):
        """Put the car back on its start slot and clear all race bookkeeping.

        `curriculum_idx` is the rolling spawn point used while training the
        spline circuit; in race modes it is None and the car starts on the
        real start/finish line.
        """
        self.last_dist = 0.0
        self.stall_counter = 0
        self.total_degrees_turned = 0.0
        self.checkpoints_passed = 0
        self.reverse_accum = 0.0
        self.gates_hit = set()
        self.gate_credits = 0
        self.line_credits = 0
        self.shortcut_credits = 0
        self.lap_base_cp = 0
        # Signed along-track offset from the finish-line plane, previous frame.
        # None = "not measured yet" (spawn frame), so the very first evaluation
        # only seeds it and never credits a lap.
        self.line_prev_along = None

        # In race mode, curriculum_idx is None (spawns at legitimate start line)
        if curriculum_idx is not None and hasattr(track, "compute_curriculum_spawn"):
            self.pos_x, self.pos_y, self.angle = track.compute_curriculum_spawn(self.spawn_index, curriculum_idx)
            self.last_closest_idx = int(curriculum_idx)
        else:
            self.pos_x, self.pos_y = track.compute_spawn_pos(self.spawn_index)
            self.angle = track.spawn_angle
            self.last_closest_idx = getattr(track, "start_idx", 0)

        # The figure-8 resync target must MATCH the tracker seed. If it stays
        # 0 while last_closest_idx is start_idx (14), every compute_fitness
        # call that takes the resync branch rewinds the tracker to 0 and the
        # next call re-credits the 14 checkpoints behind the spawn -- fitness
        # and lap climbed by themselves in WAITING/COUNTDOWN.
        self._f8_real_idx = self.last_closest_idx

        self.speed = 4.3  # Permanent speed
        self.is_alive = True
        self.total_distance = 0.0
        self.time_alive = 0

        self.prev_polar_angle = math.atan2(self.pos_y - track.center[1], self.pos_x - track.center[0])
        self.total_angle_traversed = 0.0

        self.rotated_sprite = pygame.transform.rotate(self.base_sprite, -self.angle)
        self.rect = self.rotated_sprite.get_rect(center=(int(self.pos_x), int(self.pos_y)))
        self.ray_endpoints, self.sensor_readings = track.cast_rays(self, self.sensor_angles, MAX_RAY_LENGTH)

    def update(self, steering_action, track):
        """Advance one physics frame and apply every rule that can end a run.

        Order matters: steer -> move -> reverse check -> per-track race
        events -> stall -> donut -> collision -> re-cast the LiDAR. Each
        rule returns immediately when it fires, so a dead car never keeps
        moving or scoring.
        """
        if not self.is_alive:
            return

        turn_rate = 4.8  # Responsive steering authority for tight corners
        d_angle = max(-1.0, min(1.0, steering_action)) * turn_rate
        self.angle += d_angle
        self.total_degrees_turned += abs(d_angle)

        rad = math.radians(self.angle)
        self.pos_x += math.sin(rad) * self.speed
        self.pos_y -= math.cos(rad) * self.speed
        self.total_distance += self.speed
        self.time_alive += 1

        curr_polar_angle = math.atan2(self.pos_y - track.center[1], self.pos_x - track.center[0])
        d_theta = curr_polar_angle - self.prev_polar_angle
        if d_theta < -math.pi: d_theta += 2 * math.pi
        elif d_theta > math.pi: d_theta -= 2 * math.pi
        self.total_angle_traversed += d_theta
        self.prev_polar_angle = curr_polar_angle

        # 1. Backwards driving check (Ring Circuit)
        if track.id == "ring_gp" and self.total_angle_traversed < -0.35:
            self.is_alive = False
            return

        # 1b. Per-frame race events (figure-8: reverse kill, gates, lap line)
        track.update_race_events(self)
        if not self.is_alive:
            return

        # 2. Stall detection
        if self.total_distance - self.last_dist < 1.0:
            self.stall_counter += 1
            if self.stall_counter > 60:
                self.is_alive = False
                return
        else:
            self.stall_counter = 0
            self.last_dist = self.total_distance

        # 3. Anti-Donut Ratio: turned too much without moving forward
        if self.total_degrees_turned > 450.0 and self.total_distance < 150.0:
            self.is_alive = False
            return

        self.rotated_sprite = pygame.transform.rotate(self.base_sprite, -self.angle)
        self.rect = self.rotated_sprite.get_rect(center=(int(self.pos_x), int(self.pos_y)))

        if track.check_collision(self):
            self.is_alive = False
            return

        self.ray_endpoints, self.sensor_readings = track.cast_rays(self, self.sensor_angles, MAX_RAY_LENGTH)

    def draw(self, surface, is_leader=False, show_rays=False):
        """Render the car (and optionally its LiDAR) with its role tag.

        Wrecked cars become a grey dot with a red cross, so a crash stays
        readable after the sprite stops meaning anything.
        """
        if self.is_alive:
            if self.is_last_champion:
                sprite_to_draw = SPRITE_RED_F1
                if is_leader:
                    aura_radius = 28 + int(math.sin(self.time_alive * 0.15) * 3)
                    aura_surf = pygame.Surface((aura_radius * 2, aura_radius * 2), pygame.SRCALPHA)
                    pygame.draw.circle(aura_surf, (*COLOR_GOLD_AURA, 90), (aura_radius, aura_radius), aura_radius)
                    pygame.draw.circle(aura_surf, (*COLOR_GOLD_AURA, 180), (aura_radius, aura_radius), aura_radius, 2)
                    surface.blit(aura_surf, (int(self.pos_x - aura_radius), int(self.pos_y - aura_radius)))
                    tag_color, tag_text = (241, 196, 15), "[#1] DEFENDING CHAMPION"
                else:
                    tag_color, tag_text = (255, 107, 107), "Last Champion"
            elif is_leader:
                sprite_to_draw = SPRITE_YELLOW_F1
                tag_color, tag_text = (241, 196, 15), "[#1] CURRENT LEADER"
            else:
                sprite_to_draw = self.base_sprite
                tag_color, tag_text = self.tag_color, self.name

            if show_rays:
                for i, ep in enumerate(self.ray_endpoints):
                    color = COLOR_RAY_ALERT if self.sensor_readings[i] < 0.28 else (COLOR_GOLD_AURA if is_leader else COLOR_RAY_SAFE)
                    pygame.draw.line(surface, color, (int(self.pos_x), int(self.pos_y)), ep, 1)

            rotated = pygame.transform.rotate(sprite_to_draw, -self.angle)
            rect = rotated.get_rect(center=(int(self.pos_x), int(self.pos_y)))
            surface.blit(rotated, rect.topleft)

            tag = font_subtitle.render(tag_text, True, tag_color)
            surface.blit(tag, (rect.centerx - tag.get_width() // 2, rect.top - 18))
        else:
            pygame.draw.circle(surface, COLOR_WRECK, (int(self.pos_x), int(self.pos_y)), 7)
            px, py = int(self.pos_x), int(self.pos_y)
            pygame.draw.line(surface, COLOR_RAY_ALERT, (px - 5, py - 5), (px + 5, py + 5), 2)
            pygame.draw.line(surface, COLOR_RAY_ALERT, (px + 5, py - 5), (px - 5, py + 5), 2)
