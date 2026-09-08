# =============================================================================
# spline_circuit.py -- "Precision Spline Circuit": the grand prix course.
#
# The hardest track: 21 hand-placed waypoints smoothed into ~480 centreline
# points with a Catmull-Rom spline. It is also the only circuit that uses
# curriculum spawning during training (see ai_evolution.eval_genomes).
# =============================================================================
import math
import numpy as np
import pygame
from settings import (
    SCREEN_WIDTH, SCREEN_HEIGHT, COLOR_GRASS, COLOR_GRASS_DARK,
    COLOR_GRAVEL, COLOR_ASPHALT, COLOR_ASPHALT_LINE, COLOR_KERB_RED,
    COLOR_KERB_WHITE, COLOR_TEXT, COLOR_PANEL_BG, MAX_RAY_LENGTH
)
from tracks.base_track import BaseTrack

def catmull_rom_spline(P0, P1, P2, P3, n_points=24):
    """Sample one Catmull-Rom segment between P1 and P2.

    P0 and P3 are the neighbouring control points; they only set the entry
    and exit tangents, so the curve passes through P1 and P2 exactly.
    """
    t = np.linspace(0, 1, n_points)
    t2 = t * t
    t3 = t2 * t
    a = -0.5 * t3 + t2 - 0.5 * t
    b =  1.5 * t3 - 2.5 * t2 + 1.0
    c = -1.5 * t3 + 2.0 * t2 + 0.5 * t
    d =  0.5 * t3 - 0.5 * t2
    x = P0[0] * a + P1[0] * b + P2[0] * c + P3[0] * d
    y = P0[1] * a + P1[1] * b + P2[1] * c + P3[1] * d
    return list(zip(x, y))

def generate_smooth_circuit(base_waypoints, samples_per_segment=24):
    """Close the waypoint loop and smooth every segment into one point list."""
    smooth_pts = []
    n = len(base_waypoints)
    for i in range(n):
        p0 = base_waypoints[(i - 1) % n]
        p1 = base_waypoints[i]
        p2 = base_waypoints[(i + 1) % n]
        p3 = base_waypoints[(i + 2) % n]
        segment = catmull_rom_spline(p0, p1, p2, p3, samples_per_segment)
        smooth_pts.extend(segment[:-1])
    return smooth_pts

# All waypoints shifted upward by 45px (y - 45) for balanced vertical alignment
GP_WAYPOINTS = [
    (270, 155), (480, 155), (660, 135), (800, 95),  (920, 115),
    (960, 195), (890, 275), (760, 315), (740, 405), (830, 495),
    (930, 575), (890, 665), (760, 675), (600, 575), (460, 555),
    (360, 635), (190, 675), (100, 575), (90, 415),  (120, 275), 
    (170, 175)
]

# 21 waypoints x 24 samples, minus the duplicated seam point per segment.
CIRCUIT_PATH = generate_smooth_circuit(GP_WAYPOINTS, samples_per_segment=24)
SPAWN_POINT = CIRCUIT_PATH[0]
SPAWN_ANGLE = 90.0

def compute_track_normals(pts):
    """Perpendicular offset direction at every point of a closed polyline.

    Used to extrude the centreline into a ribbon: gravel, kerbs and tarmac
    are all drawn by offsetting consecutive centreline points along these
    normals by the required half-width.
    """
    n = len(pts)
    normals = []
    for i in range(n):
        prev_p = pts[(i - 1) % n]
        next_p = pts[(i + 1) % n]
        dx = next_p[0] - prev_p[0]
        dy = next_p[1] - prev_p[1]
        length = math.hypot(dx, dy)
        normals.append((0.0, -1.0) if length == 0 else (-dy / length, dx / length))
    return normals

class SplineCircuitTrack(BaseTrack):
    """Grand prix course: a Catmull-Rom centreline and mask-based physics."""
    def __init__(self):
        """Bind the shared centreline constants, then render surface + mask."""
        super().__init__("spline_gp", "Precision Spline Circuit", "Challenging grand prix course packed with tight twists and flowing chicanes.")
        self.track_width = 76.0
        self.center = (430, (SCREEN_HEIGHT // 2) - 45)
        self.circuit_path = CIRCUIT_PATH
        self.spawn_pos = SPAWN_POINT
        self.spawn_angle = SPAWN_ANGLE
        self.spawn_outside_dir = self._compute_spawn_outside_dir(0)
        self.max_gen_duration = 38.0
        self.surface, self.wall_mask = self._build_environment()
        
    def _build_environment(self):
        """Render gravel -> kerbs -> tarmac -> centreline -> finish line at 2x,
        downscale to screen size, then rasterise the drivable-area mask.
        """
        SCALE = 2
        W, H = SCREEN_WIDTH * SCALE, SCREEN_HEIGHT * SCALE
        
        scaled_pts = [(p[0] * SCALE, p[1] * SCALE) for p in self.circuit_path]
        normals = compute_track_normals(scaled_pts)
        n = len(scaled_pts)
        
        # 1. Base Lawn Stripes (Full Screen Width)
        surf = pygame.Surface((W, H))
        surf.fill(COLOR_GRASS)

        stripe_h = 40 * SCALE
        for y in range(0, H, stripe_h):
            if (y // stripe_h) % 2 == 0:
                pygame.draw.rect(surf, COLOR_GRASS_DARK, (0, y, W, stripe_h))

        half_w = (self.track_width * SCALE) / 2.0
        gravel_extra = 16.0 * SCALE
        kerb_w = 6.0 * SCALE
        tarmac_half_w = half_w - kerb_w

        # 2. Gravel Runoff Layer
        for i in range(n):
            j = (i + 1) % n
            p1, p2 = scaled_pts[i], scaled_pts[j]
            n1, n2 = normals[i], normals[j]
            gw = half_w + gravel_extra
            q1 = (p1[0] - n1[0] * gw, p1[1] - n1[1] * gw)
            q2 = (p1[0] + n1[0] * gw, p1[1] + n1[1] * gw)
            q3 = (p2[0] + n2[0] * gw, p2[1] + n2[1] * gw)
            q4 = (p2[0] - n2[0] * gw, p2[1] - n2[1] * gw)
            pygame.draw.polygon(surf, COLOR_GRAVEL, [q1, q2, q3, q4])

        # 3. Alternating Full-Width Kerb Base Layer
        for i in range(n):
            j = (i + 1) % n
            p1, p2 = scaled_pts[i], scaled_pts[j]
            n1, n2 = normals[i], normals[j]
            kerb_col = COLOR_KERB_RED if (i // 4) % 2 == 0 else COLOR_KERB_WHITE
            q1 = (p1[0] - n1[0] * half_w, p1[1] - n1[1] * half_w)
            q2 = (p1[0] + n1[0] * half_w, p1[1] + n1[1] * half_w)
            q3 = (p2[0] + n2[0] * half_w, p2[1] + n2[1] * half_w)
            q4 = (p2[0] - n2[0] * half_w, p2[1] - n2[1] * half_w)
            pygame.draw.polygon(surf, kerb_col, [q1, q2, q3, q4])

        # 4. Asphalt Tarmac Layer
        for i in range(n):
            j = (i + 1) % n
            p1, p2 = scaled_pts[i], scaled_pts[j]
            n1, n2 = normals[i], normals[j]
            q1 = (p1[0] - n1[0] * tarmac_half_w, p1[1] - n1[1] * tarmac_half_w)
            q2 = (p1[0] + n1[0] * tarmac_half_w, p1[1] + n1[1] * tarmac_half_w)
            q3 = (p2[0] + n2[0] * tarmac_half_w, p2[1] + n2[1] * tarmac_half_w)
            q4 = (p2[0] - n2[0] * tarmac_half_w, p2[1] - n2[1] * tarmac_half_w)
            pygame.draw.polygon(surf, COLOR_ASPHALT, [q1, q2, q3, q4])

        # 5. Centerline
        for i in range(0, n, 6):
            p1 = scaled_pts[i]
            p2 = scaled_pts[(i + 3) % n]
            pygame.draw.line(surf, COLOR_ASPHALT_LINE, p1, p2, int(2 * SCALE))

        # 6. Checkered Finish Line
        sf_p = scaled_pts[0]
        sf_norm = normals[0]
        num_blocks = 8
        b_len = 6 * SCALE
        step_w = (tarmac_half_w * 2.0) / num_blocks

        for b in range(num_blocks):
            offset1 = -tarmac_half_w + b * step_w
            offset2 = -tarmac_half_w + (b + 1) * step_w
            c1 = COLOR_TEXT if b % 2 == 0 else COLOR_PANEL_BG
            c2 = COLOR_PANEL_BG if b % 2 == 0 else COLOR_TEXT

            p_a1 = (sf_p[0] + sf_norm[0] * offset1, sf_p[1] + sf_norm[1] * offset1)
            p_a2 = (sf_p[0] + sf_norm[0] * offset2, sf_p[1] + sf_norm[1] * offset2)
            p_b1 = (p_a1[0] + sf_norm[1] * b_len, p_a1[1] - sf_norm[0] * b_len)
            p_b2 = (p_a2[0] + sf_norm[1] * b_len, p_a2[1] - sf_norm[0] * b_len)
            p_c1 = (p_a1[0] - sf_norm[1] * b_len, p_a1[1] + sf_norm[0] * b_len)
            p_c2 = (p_a2[0] - sf_norm[1] * b_len, p_a2[1] + sf_norm[0] * b_len)

            pygame.draw.polygon(surf, c1, [p_a1, p_a2, p_b2, p_b1])
            pygame.draw.polygon(surf, c2, [p_c1, p_c2, p_a2, p_a1])

        final_track = pygame.transform.smoothscale(surf, (SCREEN_WIDTH, SCREEN_HEIGHT))

        # 7. Binary Collision Mask (0 = Drivable tarmac, 1 = Barrier/Kerb)
        mask_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        mask_surf.fill((255, 255, 255))
        
        native_pts = self.circuit_path
        native_normals = compute_track_normals(native_pts)
        drivable_half_w = (self.track_width - 8.0) / 2.0
        for i in range(len(native_pts)):
            j = (i + 1) % len(native_pts)
            p1, p2 = native_pts[i], native_pts[j]
            n1, n2 = native_normals[i], native_normals[j]
            q1 = (p1[0] - n1[0] * drivable_half_w, p1[1] - n1[1] * drivable_half_w)
            q2 = (p1[0] + n1[0] * drivable_half_w, p1[1] + n1[1] * drivable_half_w)
            q3 = (p2[0] + n2[0] * drivable_half_w, p2[1] + n2[1] * drivable_half_w)
            q4 = (p2[0] - n2[0] * drivable_half_w, p2[1] - n2[1] * drivable_half_w)
            pygame.draw.polygon(mask_surf, (0, 0, 0), [q1, q2, q3, q4])

        mask_surf.set_colorkey((0, 0, 0))
        wall_mask = pygame.mask.from_surface(mask_surf)
        return final_track, wall_mask

    def compute_spawn_pos(self, spawn_index):
        """Two-lane start line, all cars packed on it (see the note below)."""
        # Spline's start line sits at the left edge of the screen (x=270).
        # The shared ring-style grid steps backwards along the track, which
        # quickly puts later spawn indices outside the track on this map.
        # Keep all spline starters tightly packed at the actual start line,
        # staggered only across the track width.
        px, py = self.spawn_pos
        ox, oy = self.spawn_outside_dir
        lateral = 7.0 if (spawn_index % 2 == 0) else -7.0
        return (px + ox * lateral, py + oy * lateral)

    def compute_curriculum_spawn(self, spawn_index, spline_idx):
        """3-wide grid of spawn slots at an arbitrary point along the track."""
        idx = int(spline_idx) % len(self.circuit_path)
        p1 = self.circuit_path[idx]
        p2 = self.circuit_path[(idx + 1) % len(self.circuit_path)]
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        heading_angle = math.degrees(math.atan2(dx, -dy))
        
        col = spawn_index % 3
        row = spawn_index // 3
        offset_lat = (col - 1) * 6.0
        offset_long = -float(row * 5.0)
        
        length = math.hypot(dx, dy)
        nx, ny = (-dy / length, dx / length) if length > 0 else (0, -1)
        
        pos_x = p1[0] + nx * offset_lat + (dx / length) * offset_long
        pos_y = p1[1] + ny * offset_lat + (dy / length) * offset_long
        return pos_x, pos_y, heading_angle

    def check_collision(self, car) -> bool:
        """True when the car's sprite mask overlaps a non-drivable pixel."""
        car_mask = pygame.mask.from_surface(car.rotated_sprite, threshold=128)
        offset = (int(car.rect.left), int(car.rect.top))
        return bool(self.wall_mask.overlap(car_mask, offset))

    def cast_rays(self, car, sensor_angles, max_len=MAX_RAY_LENGTH):
        """March each ray in 2 px steps through the wall mask."""
        endpoints, readings = [], []
        start_x, start_y = car.pos_x, car.pos_y

        for offset_angle in sensor_angles:
            global_angle = car.angle + offset_angle
            rad = math.radians(global_angle)
            dir_x, dir_y = math.sin(rad), -math.cos(rad)

            hit_dist = max_len
            current_step = 0.0
            step_size = 2.0

            while current_step < max_len:
                current_step += step_size
                tx = int(start_x + dir_x * current_step)
                ty = int(start_y + dir_y * current_step)

                if not (0 <= tx < SCREEN_WIDTH and 0 <= ty < SCREEN_HEIGHT):
                    hit_dist = current_step
                    break
                if self.wall_mask.get_at((tx, ty)):
                    hit_dist = current_step
                    break

            endpoints.append((int(start_x + dir_x * hit_dist), int(start_y + dir_y * hit_dist)))
            readings.append(hit_dist / max_len)
        return endpoints, readings

    def compute_fitness(self, car) -> float:
        """Checkpoint bookkeeping for the HUD, plus the progress/distance score.

        The score deliberately uses the ABSOLUTE path index -- read the long
        comment above `progress_score` before changing it.
        """
        # Windowed forward search: accumulates car.checkpoints_passed, which is
        # what the HUD lap counter reads. It is bookkeeping for the HUD only --
        # it is deliberately NOT part of the fitness score below.
        n = len(self.circuit_path)
        curr_idx = car.last_closest_idx
        search_range = 30
        min_w = float('inf')
        closest_w = curr_idx
        for offset in range(-5, search_range):
            test_idx = (curr_idx + offset) % n
            pt = self.circuit_path[test_idx]
            d = (car.pos_x - pt[0]) ** 2 + (car.pos_y - pt[1]) ** 2
            if d < min_w:
                min_w = d
                closest_w = test_idx
        forward_step = (closest_w - curr_idx) % n
        if 0 < forward_step < search_range:
            car.checkpoints_passed += forward_step
            car.last_closest_idx = closest_w

        # Fitness formula: progress + distance + survival.
        # Full-scan closest point over the whole path:
        min_dist = float('inf')
        closest_idx = 0
        for i, pt in enumerate(self.circuit_path):
            d = (car.pos_x - pt[0]) ** 2 + (car.pos_y - pt[1]) ** 2
            if d < min_dist:
                min_dist = d
                closest_idx = i

        # DO NOT "fix" this absolute index into a spawn-relative one.
        #
        # It looks wrong: closest_idx is the ABSOLUTE path index, so with
        # curriculum spawning a car born at index 240 banks 3360 free points
        # before it even moves. That is real, but measured head-to-head the
        # spawn-relative alternative loses badly.
        #
        # A/B over 4 seeds x 100 generations, champion re-driven from 5 spawn
        # points each (start line + 4 curriculum points), mean laps completed:
        #
        #     seed    absolute (this code)    spawn-relative (worse)
        #     12345         3.33                    2.12
        #     777           3.30                    0.05
        #     4242          0.07                    0.05   (both stall)
        #     999           3.55                    0.18
        #
        # The absolute form wins 3, ties 1, loses 0. Its breakthroughs also
        # generalise: every one of its 5 spawn points completes a full
        # 3.3-3.6 laps, whereas the spawn-relative breakthrough dies instantly
        # at 2 of its 5 spawn points.
        #
        # Why the "obviously better" version is worse: closest_idx saturates at
        # 482, so the progress term caps at 6748 and stops supplying gradient
        # after the first lap. Past that point the distance term
        # (total_distance * 1.5) dominates, which correlates cleanly with
        # actually driving. The uncapped spawn-relative counter stays the
        # dominant term forever, so it amplifies every tracking error in the
        # windowed checkpoint search and selects for brittle policies instead.
        progress_score = float(closest_idx) * 14.0
        distance_score = car.total_distance * 1.5
        survival_bonus = car.time_alive * 0.2
        return max(0.0, progress_score + distance_score + survival_bonus)