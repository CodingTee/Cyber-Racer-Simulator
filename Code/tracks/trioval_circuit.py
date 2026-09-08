# =============================================================================
# trioval_circuit.py -- "Tri-Oval Speedway": a 3-turn superspeedway.
#
# A closed parametric loop sampled into 320 centreline points. Unlike the
# ring it has no closed form, so collision and LiDAR work off a pre-rendered
# binary wall mask that the rays march through.
# =============================================================================
import math
import pygame
from settings import (
    SCREEN_WIDTH, SCREEN_HEIGHT, COLOR_GRASS, COLOR_GRASS_DARK,
    COLOR_GRAVEL, COLOR_ASPHALT, COLOR_ASPHALT_LINE, COLOR_KERB_RED,
    COLOR_KERB_WHITE, COLOR_TEXT, COLOR_PANEL_BG, MAX_RAY_LENGTH
)
from tracks.base_track import BaseTrack


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


class TriOvalCircuitTrack(BaseTrack):
    """Three-turn oval sampled into 320 centreline points; mask-based physics."""
    def __init__(self):
        """Build the centreline, measure its length, render surface + mask."""
        super().__init__(
            "trioval_gp",
            "Tri-Oval Speedway",
            "High-speed 3-turn superspeedway built for flat-out acceleration and sweeping apexes."
        )
        self.track_width = 106.0
        self.center = (525, (SCREEN_HEIGHT // 2) + 45)
        self.overlay_anchor = (525, (SCREEN_HEIGHT // 2) + 15)

        self.radius_x = 395.0
        self.radius_y = 270.0

        self.circuit_path = self._generate_circuit_path(num_points=320)
        self.start_idx = 0
        self.spawn_pos = self.circuit_path[0]

        # Calculate exact total perimeter length of the spline path
        self.track_length = sum(
            math.hypot(self.circuit_path[(i + 1) % len(self.circuit_path)][0] - self.circuit_path[i][0],
                       self.circuit_path[(i + 1) % len(self.circuit_path)][1] - self.circuit_path[i][1])
            for i in range(len(self.circuit_path))
        )

        p0 = self.circuit_path[0]
        p1 = self.circuit_path[1]
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        self.spawn_angle = math.degrees(math.atan2(dx, -dy))
        self.spawn_outside_dir = self._compute_spawn_outside_dir(0)

        self.max_gen_duration = 32.0
        self.surface, self.wall_mask = self._build_environment()

    def _generate_circuit_path(self, num_points=320):
        """Sample the superspeedway shape into `num_points` centreline points."""
        pts = []
        cx, cy = self.center[0], self.center[1]

        for i in range(num_points):
            t = (2 * math.pi * i) / num_points
            r_factor = 1.0 + 0.18 * math.sin(t) - 0.12 * math.cos(2 * t)
            x = cx + self.radius_x * math.cos(t) * (1.0 - 0.08 * math.sin(t))
            y = cy - self.radius_y * math.sin(t) * r_factor
            pts.append((x, y))

        return pts

    def _build_environment(self):
        """Render gravel -> kerbs -> tarmac -> centreline -> finish line at 2x,
        downscale to screen size, then rasterise the drivable-area mask.
        """
        SCALE = 2
        W, H = SCREEN_WIDTH * SCALE, SCREEN_HEIGHT * SCALE

        scaled_pts = [(p[0] * SCALE, p[1] * SCALE) for p in self.circuit_path]
        normals = compute_track_normals(scaled_pts)
        n = len(scaled_pts)

        # 1. Base Lawn
        surf = pygame.Surface((W, H))
        surf.fill(COLOR_GRASS)
        stripe_h = 40 * SCALE
        for y in range(0, H, stripe_h):
            if (y // stripe_h) % 2 == 0:
                pygame.draw.rect(surf, COLOR_GRASS_DARK, (0, y, W, stripe_h))

        half_w = (self.track_width * SCALE) / 2.0
        gravel_extra = 14.0 * SCALE
        kerb_w = 6.0 * SCALE
        tarmac_half_w = half_w - kerb_w

        # 2. Gravel Runoff
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

        # 3. Kerbs
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

        # 4. Asphalt Tarmac (94px Drivable Width)
        for i in range(n):
            j = (i + 1) % n
            p1, p2 = scaled_pts[i], scaled_pts[j]
            n1, n2 = normals[i], normals[j]
            q1 = (p1[0] - n1[0] * tarmac_half_w, p1[1] - n1[1] * tarmac_half_w)
            q2 = (p1[0] + n1[0] * tarmac_half_w, p1[1] + n1[1] * tarmac_half_w)
            q3 = (p2[0] + n2[0] * tarmac_half_w, p2[1] + n2[1] * tarmac_half_w)
            q4 = (p2[0] - n2[0] * tarmac_half_w, p2[1] - n2[1] * tarmac_half_w)
            pygame.draw.polygon(surf, COLOR_ASPHALT, [q1, q2, q3, q4])

        # 5. Dashed Centerline
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

        # 7. Collision Mask
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

    # Lateral start-line slots along `spawn_outside_dir`: positive = OUTSIDE of
    # the corner, negative = INSIDE. Slot 0/1 sit on the classic 2-wide
    # front row, so multiplayer P1/P2 keep their exact positions.
    _LATERAL_SLOTS = (7.0, -7.0, 21.0, -21.0, 30.0, -30.0)

    def compute_spawn_pos(self, spawn_index):
        # The shared ring-style grid steps `row * 12` px backward along the
        # tangent. The tri-oval start line sits at the right-hand end of the
        # oval where the track curves away immediately, so from row 8 onward
        # the slot walks straight off the tarmac: 15 of 30 cars were wrecked on
        # frame 1 and only 16 ever raced.
        # Keep every car on the start line, spread across the track width.
        lateral = self._LATERAL_SLOTS[spawn_index % len(self._LATERAL_SLOTS)]
        # Outside slot travels the longer line, so it keeps its head start.
        lane_stagger = lateral * (6.0 / 7.0)

        ox, oy = self.spawn_outside_dir
        rad = math.radians(self.spawn_angle)
        tx, ty = math.sin(rad), -math.cos(rad)
        return (self.spawn_pos[0] + ox * lateral + tx * lane_stagger,
                self.spawn_pos[1] + oy * lateral + ty * lane_stagger)

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
        """March each ray in 2 px steps through the wall mask.

        Far simpler than exact geometry for an arbitrary polyline track, and
        accurate to the 2 px step -- negligible against the 300 px range.
        """
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
        """Checkpoints x18 + speed + heading alignment + time alive."""
        n = len(self.circuit_path)
        curr_idx = car.last_closest_idx
        search_range = 30
        min_dist = float('inf')
        closest_idx = curr_idx

        for offset in range(-5, search_range):
            test_idx = (curr_idx + offset) % n
            pt = self.circuit_path[test_idx]
            d = (car.pos_x - pt[0]) ** 2 + (car.pos_y - pt[1]) ** 2
            if d < min_dist:
                min_dist = d
                closest_idx = test_idx

        forward_step = (closest_idx - curr_idx) % n
        if forward_step > 0 and forward_step < search_range:
            car.checkpoints_passed += forward_step
            car.last_closest_idx = closest_idx

        p1 = self.circuit_path[closest_idx]
        p2 = self.circuit_path[(closest_idx + 1) % n]
        t_dx, t_dy = p2[0] - p1[0], p2[1] - p1[1]
        t_len = math.hypot(t_dx, t_dy)
        rad = math.radians(car.angle)
        c_dx, c_dy = math.sin(rad), -math.cos(rad)
        alignment = (c_dx * t_dx + c_dy * t_dy) / (t_len + 1e-5) if t_len > 0 else 0.0

        progress_score = float(car.checkpoints_passed) * 18.0
        speed_bonus = car.speed * 2.5
        alignment_bonus = max(0.0, alignment) * 4.0
        survival_bonus = car.time_alive * 0.2

        return max(0.0, progress_score + speed_bonus + alignment_bonus + survival_bonus)