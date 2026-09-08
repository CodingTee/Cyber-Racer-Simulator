# =============================================================================
# ring_circuit.py -- "Speed Ring Circuit": a perfect annulus.
#
# The simplest circuit and the only one with closed-form maths: no centreline
# array, no normals. Collision and LiDAR are solved analytically against the
# two boundary circles, which makes it the cheapest track to simulate and the
# reference the other three are measured against.
# =============================================================================
import math
import pygame
from settings import (
    SCREEN_WIDTH, SCREEN_HEIGHT, COLOR_GRASS, COLOR_GRASS_DARK,
    COLOR_GRAVEL, COLOR_ASPHALT, COLOR_ASPHALT_LINE, COLOR_KERB_RED,
    COLOR_KERB_WHITE, MAX_RAY_LENGTH
)
from tracks.base_track import BaseTrack

class RingCircuitTrack(BaseTrack):
    """Circular circuit: constant-width annulus, analytic collision + LiDAR."""
    def __init__(self):
        """Define the annulus (inner/outer radius + kerb) and render it."""
        super().__init__("ring_gp", "Speed Ring Circuit", "High-speed oval built for full-throttle racing and clean cornering.")
        self.center = (520, SCREEN_HEIGHT // 2)
        self.outer_radius = 350.0
        self.inner_radius = 210.0
        self.kerb_thickness = 7.0
        self.mid_radius = (self.outer_radius + self.inner_radius) / 2.0
        
        # Strict drivable boundaries: touching kerbs triggers instant crash
        self.collision_outer_limit = self.outer_radius - self.kerb_thickness
        self.collision_inner_limit = self.inner_radius + self.kerb_thickness
        
        self.spawn_pos = (float(self.center[0]), float(self.center[1] - self.mid_radius))
        self.spawn_angle = 90.0
        self.max_gen_duration = 30.0
        self.surface, self.wall_mask = self._build_environment()

    def _build_environment(self):
        """Render the track at 2x and downscale, then rasterise the wall mask.

        Everything is drawn on a double-size surface and smoothly scaled down
        so kerbs and centreline dashes stay anti-aliased. The wall mask is
        authored at native resolution: black = drivable tarmac,
        white = barrier.
        """
        SCALE = 2
        W, H = SCREEN_WIDTH * SCALE, SCREEN_HEIGHT * SCALE
        CX, CY = self.center[0] * SCALE, self.center[1] * SCALE
        R_OUTER = self.outer_radius * SCALE
        R_INNER = self.inner_radius * SCALE
        R_MID = self.mid_radius * SCALE
        K_THICK = self.kerb_thickness * SCALE
        GRAVEL_W = 16.0 * SCALE
        
        # 1. Base Layer: Global lawn stripes (Full Screen Width)
        surf = pygame.Surface((W, H))
        surf.fill(COLOR_GRASS)
        stripe_h = 40 * SCALE
        for y in range(0, H, stripe_h):
            if (y // stripe_h) % 2 == 0:
                pygame.draw.rect(surf, COLOR_GRASS_DARK, (0, y, W, stripe_h))

        # 2. Outer Gravel Runoff
        pygame.draw.circle(surf, COLOR_GRAVEL, (CX, CY), int(R_OUTER + GRAVEL_W))

        # 3. Outer Kerbs (80 spaced out segments)
        num_kerbs = 80
        angle_step = 360.0 / num_kerbs

        for i in range(num_kerbs):
            ang_rad = math.radians(i * angle_step)
            next_rad = math.radians((i + 1) * angle_step + 0.1)
            col = COLOR_KERB_RED if i % 2 == 0 else COLOR_KERB_WHITE

            op1 = (CX + math.cos(ang_rad) * (R_OUTER - K_THICK), CY + math.sin(ang_rad) * (R_OUTER - K_THICK))
            op2 = (CX + math.cos(ang_rad) * R_OUTER, CY + math.sin(ang_rad) * R_OUTER)
            op3 = (CX + math.cos(next_rad) * R_OUTER, CY + math.sin(next_rad) * R_OUTER)
            op4 = (CX + math.cos(next_rad) * (R_OUTER - K_THICK), CY + math.sin(next_rad) * (R_OUTER - K_THICK))
            pygame.draw.polygon(surf, col, [op1, op2, op3, op4])

        # 4. Asphalt Tarmac
        pygame.draw.circle(surf, COLOR_ASPHALT, (CX, CY), int(R_OUTER - K_THICK))

        # 5. Smooth Curvature-Conforming Dashed Median Centerline
        num_dashes = 64
        dash_step = 360.0 / num_dashes
        samples_per_dash = 6

        for i in range(num_dashes):
            dash_start_deg = i * dash_step
            dash_span_deg = dash_step * 0.48
            
            dash_pts = []
            for s in range(samples_per_dash + 1):
                ang = math.radians(dash_start_deg + (dash_span_deg * (s / samples_per_dash)))
                dash_pts.append((CX + math.cos(ang) * R_MID, CY + math.sin(ang) * R_MID))
                
            pygame.draw.lines(surf, COLOR_ASPHALT_LINE, False, dash_pts, int(2.5 * SCALE))

        # 6. Inner Kerbs
        for i in range(num_kerbs):
            ang_rad = math.radians(i * angle_step)
            next_rad = math.radians((i + 1) * angle_step + 0.1)
            col = COLOR_KERB_RED if i % 2 == 0 else COLOR_KERB_WHITE

            ip1 = (CX + math.cos(ang_rad) * R_INNER, CY + math.sin(ang_rad) * R_INNER)
            ip2 = (CX + math.cos(ang_rad) * (R_INNER + K_THICK), CY + math.sin(ang_rad) * (R_INNER + K_THICK))
            ip3 = (CX + math.cos(next_rad) * (R_INNER + K_THICK), CY + math.sin(next_rad) * (R_INNER + K_THICK))
            ip4 = (CX + math.cos(next_rad) * R_INNER, CY + math.sin(next_rad) * R_INNER)
            pygame.draw.polygon(surf, col, [ip1, ip2, ip3, ip4])

        # 7. Inner Gravel Runoff
        pygame.draw.circle(surf, COLOR_GRAVEL, (CX, CY), int(R_INNER))

        # 8. Checkered Finish Line (Clipped strictly between kerbs)
        grid_top = int(CY - (R_OUTER - K_THICK))
        grid_bottom = int(CY - (R_INNER + K_THICK))
        block_sz = 6 * SCALE

        for r in range(grid_top, grid_bottom, block_sz):
            c1 = (255, 255, 255) if (r // block_sz) % 2 == 0 else (25, 25, 25)
            c2 = (25, 25, 25) if (r // block_sz) % 2 == 0 else (255, 255, 255)
            pygame.draw.rect(surf, c1, (CX - block_sz, r, block_sz, block_sz))
            pygame.draw.rect(surf, c2, (CX, r, block_sz, block_sz))

        # 9. Seamless Infield Mask Cutout
        infield_mask = pygame.Surface((W, H), pygame.SRCALPHA)
        for y in range(0, H, stripe_h):
            if (y // stripe_h) % 2 == 0:
                pygame.draw.rect(infield_mask, (*COLOR_GRASS_DARK, 255), (0, y, W, stripe_h))
            else:
                pygame.draw.rect(infield_mask, (*COLOR_GRASS, 255), (0, y, W, stripe_h))

        cutout = pygame.Surface((W, H), pygame.SRCALPHA)
        pygame.draw.circle(cutout, (255, 255, 255, 255), (CX, CY), int(R_INNER - GRAVEL_W))
        infield_mask.blit(cutout, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        surf.blit(infield_mask, (0, 0))

        final_track = pygame.transform.smoothscale(surf, (SCREEN_WIDTH, SCREEN_HEIGHT))

        # 10. Binary Collision Mask (0 = Drivable tarmac, 1 = Barrier / Kerb)
        mask_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        mask_surf.fill((255, 255, 255))
        
        native_cx, native_cy = self.center[0], self.center[1]
        pygame.draw.circle(mask_surf, (0, 0, 0), (native_cx, native_cy), int(self.collision_outer_limit))
        pygame.draw.circle(mask_surf, (255, 255, 255), (native_cx, native_cy), int(self.collision_inner_limit))

        mask_surf.set_colorkey((0, 0, 0))
        wall_mask = pygame.mask.from_surface(mask_surf)

        return final_track, wall_mask

    # Lateral start-line slots in screen-y: negative = OUTSIDE of the oval
    # (larger radius), positive = INSIDE. Slot 0/1 sit on the classic
    # 2-wide front row, so multiplayer P1/P2 keep their exact positions.
    _LATERAL_SLOTS = (-7.0, 7.0, -21.0, 21.0, -35.0, 35.0)

    def compute_spawn_pos(self, spawn_index):
        # Ring's start line sits at the TOP of the oval. Stepping `row * 12`
        # px backward along the tangent will not do: walking a straight line
        # off a circle leaves the arc behind, and by row 13 the slot sits
        # ~50 px outside the centre line and clips the outer barrier.
        # So every car stays on the start line, spread across the width.
        lateral = self._LATERAL_SLOTS[spawn_index % len(self._LATERAL_SLOTS)]
        # Outside slot travels the longer arc, so it keeps its head start.
        lane_stagger = -lateral * (6.0 / 7.0)
        return self.spawn_pos[0] + lane_stagger, self.spawn_pos[1] + lateral

    def check_collision(self, car) -> bool:
        """True when the car's sprite mask overlaps a non-drivable pixel."""
        car_mask = pygame.mask.from_surface(car.rotated_sprite, threshold=128)
        offset = (int(car.rect.left), int(car.rect.top))
        return bool(self.wall_mask.overlap(car_mask, offset))

    def cast_rays(self, car, sensor_angles, max_len=MAX_RAY_LENGTH):
        """Ray/circle intersection against both barriers (closed form)."""
        endpoints, readings = [], []
        ox = car.pos_x - self.center[0]
        oy = car.pos_y - self.center[1]
        c_base = ox * ox + oy * oy

        for offset_angle in sensor_angles:
            rad = math.radians(car.angle + offset_angle)
            dx, dy = math.sin(rad), -math.cos(rad)
            b = 2.0 * (ox * dx + oy * dy)
            hit_dist = max_len

            # Sensor rays detect the kerb collision bounds
            for r in (self.collision_inner_limit, self.collision_outer_limit):
                c = c_base - r * r
                disc = b * b - 4.0 * c
                if disc >= 0:
                    sqrt_disc = math.sqrt(disc)
                    t1 = (-b - sqrt_disc) / 2.0
                    t2 = (-b + sqrt_disc) / 2.0
                    if 0.0 < t1 < hit_dist: hit_dist = t1
                    if 0.0 < t2 < hit_dist: hit_dist = t2

            endpoints.append((int(car.pos_x + dx * hit_dist), int(car.pos_y + dy * hit_dist)))
            readings.append(hit_dist / max_len)
        return endpoints, readings

    def compute_fitness(self, car) -> float:
        """Arc distance travelled, minus a penalty for steering wobble."""
        progress_score = car.total_angle_traversed * self.mid_radius
        wiggle_penalty = max(0.0, (car.total_degrees_turned - math.degrees(max(0.0, car.total_angle_traversed))) * 0.08)
        return max(0.0, progress_score - wiggle_penalty)