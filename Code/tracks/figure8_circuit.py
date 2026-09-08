# =============================================================================
# figure8_circuit.py -- "Lemniscate Circuit": the figure-8.
#
# The only circuit with its own rulebook. A lemniscate centreline crosses
# itself, so distance along the path cannot prove a lap: this track counts
# gate passages and start-line crossings instead (see update_race_events),
# and kills any car that accumulates net backwards travel.
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


class Figure8CircuitTrack(BaseTrack):
    """Figure-8 (lemniscate) circuit with event-based lap scoring."""
    def __init__(self):
        """Build the lemniscate, locate crossing/gates/line, then render."""
        super().__init__(
            "figure8_gp",
            "Lemniscate Circuit",
            "High-speed figure-8 raceway demanding surgical transitions through flowing curves."
        )
        self.track_width = 74.0
        self.center = (535, SCREEN_HEIGHT // 2)
        self.overlay_anchor = (735, 545)

        self.scale_x = 460.0
        self.scale_y = 300.0
        self.rotation_angle = -math.radians(34)

        self.circuit_path = self._generate_circuit_path(num_points=320)
        self.start_idx = 14

        # ---- Event-based lap system geometry (see update_race_events) ----
        # The lemniscate passes through the intersection at t=0 and t=pi,
        # so circuit_path[0] and circuit_path[160] are the SAME physical
        # point (the track centre). One full figure-8 lap = one traversal of
        # both loops = one pass of every road point = one pass of start_idx.
        self.crossing_pos = self.circuit_path[0]
        self.line_pos = self.circuit_path[self.start_idx]
        # Gates = far end of each loop (found programmatically: the path point
        # farthest from the crossing on each half of the parameterisation,
        # i.e. idx 80 (right loop) and idx 240 (left loop) for n=320).
        n_pts = len(self.circuit_path)
        _cx, _cy = self.crossing_pos
        def _d2_cross(p):
            return (p[0] - _cx) ** 2 + (p[1] - _cy) ** 2
        _half = n_pts // 2
        _gate_a = max(range(1, _half), key=lambda i: _d2_cross(self.circuit_path[i]))
        _gate_b = max(range(_half + 1, n_pts), key=lambda i: _d2_cross(self.circuit_path[i]))
        self.gate_centers = (self.circuit_path[_gate_a], self.circuit_path[_gate_b])
        # Passage radii: the car centre stays within ~27 px of the centreline
        # on this 74 px-wide road, so 48/50 px catches every on-road passage
        # while never reaching from one road arm to another at the crossing.
        self.gate_radius2 = 48.0 ** 2
        # Finish line: a CROSSING test, not a proximity circle. A circle wide
        # enough to catch the line would fire while the car is still ~49 px
        # short of the checkered band (which is only ~6 px wide on screen), so
        # the race would end before the car visibly touches it. Instead the
        # code watches the sign of the along-track offset from the line plane
        # and credits the frame the car centre actually passes through it.
        _n = len(self.circuit_path)
        _p0 = self.circuit_path[self.start_idx]
        _p1 = self.circuit_path[(self.start_idx + 1) % _n]
        _fdx, _fdy = _p1[0] - _p0[0], _p1[1] - _p0[1]
        _fl = math.hypot(_fdx, _fdy) or 1.0
        self.line_fwd = (_fdx / _fl, _fdy / _fl)
        self.line_side = (-self.line_fwd[1], self.line_fwd[0])
        # Only credit a crossing that happens on the road: the opposite arm of
        # the 8 passes the line plane ~73 px to the side, so a bare plane test
        # could not tell the two apart.
        self.line_half_width = (self.track_width - 8.0) / 2.0
        # Reverse kill threshold: ~3 car lengths of NET backward travel
        # (~9 frames at full speed against the path tangent). Legitimate
        # diagonal cuts through the intersection stay aligned with one of the
        # exit tangents and never accumulate this much, while a driver that
        # truly runs the track backwards dies within its first reverse
        # transit -- that is the intended behaviour.
        self.reverse_kill_dist = 40.0

        # Lap scoring. Two ways to cross the start
        # line, two payouts:
        #   BOTH gates held  -> full figure-8 lap, 3500
        #   ONE gate held    -> single loop only, 60% of a lap, 2100
        # Per unit distance the single loop pays 2900/1178px = 2.46 vs the full
        # lap's 5100/2357px = 2.16, i.e. cutting is worth about +14% -- but it
        # has to be earned: running one loop means making the ~66 deg turn at
        # the crossing every time, which accumulates ~30 px of reverse
        # projection against the 40 px death threshold. Slow/inexact drivers
        # are better off running the whole track; only a driver that has
        # already mastered it can cash in the shortcut.
        self.full_lap_value = 3500.0
        self.shortcut_ratio = 0.6       # a single loop counts as 60% of a lap
        self.shortcut_lap_value = self.shortcut_ratio * self.full_lap_value
        # Racing (HUD + win condition) scores a single loop as a FULL lap:
        # crossing the finish line has to look like completing a lap, otherwise
        # the counter sits at 0.60 and the car "crosses the line and keeps
        # going". Only get_lap_count reads this -- training fitness keeps using
        # shortcut_ratio above, so evolution still pays 60% for the shortcut.
        self.shortcut_race_ratio = 1.0

        # ---- Start position: ON the start/finish line (ring-style) ----
        # The line stays at start_idx and the cars start ON it, spread across
        # the track width like ring_circuit does. No slot spawns past the
        # line: every car crosses it the same number of times.
        self.spawn_pos = self.line_pos
        p0 = self.circuit_path[self.start_idx]
        p1 = self.circuit_path[(self.start_idx + 1) % len(self.circuit_path)]
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        self.spawn_angle = math.degrees(math.atan2(dx, -dy))
        self.spawn_outside_dir = self._compute_spawn_outside_dir(self.start_idx)

        self.max_gen_duration = 35.0
        self.surface, self.wall_mask = self._build_environment()

    def _generate_circuit_path(self, num_points=320):
        """Sample the lemniscate x=sin(t), y=sin(2t)/2 and rotate it into place."""
        pts = []
        cx, cy = self.center[0], self.center[1]
        cos_rot = math.cos(self.rotation_angle)
        sin_rot = math.sin(self.rotation_angle)

        for i in range(num_points):
            t = (2 * math.pi * i) / num_points
            raw_x = self.scale_x * math.sin(t)
            raw_y = self.scale_y * (math.sin(2 * t) / 2.0)

            rot_x = raw_x * cos_rot - raw_y * sin_rot
            rot_y = raw_x * sin_rot + raw_y * cos_rot
            pts.append((cx + rot_x, cy + rot_y))

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

        # 1. Lawn Stripes
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

        # 4. Asphalt Tarmac
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
        sf_p = scaled_pts[self.start_idx]
        sf_norm = normals[self.start_idx]
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

        # 7. Binary Collision Mask
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

    def _point_back_along_path(self, idx, dist):
        """Walk `dist` px backwards along the centreline from idx.

        Returns (position, heading_deg, nearest_idx). The heading is the
        forward track direction at the anchor point, so a car placed there
        faces the way the track goes. Used to put the starting grid behind the
        start/finish line without hand-tuning a pixel offset.
        """
        pts = self.circuit_path
        n = len(pts)
        i = int(idx) % n
        remaining = float(dist)
        px, py = pts[i]
        while remaining > 0.0:
            prev = (i - 1) % n
            seg = math.hypot(pts[i][0] - pts[prev][0], pts[i][1] - pts[prev][1])
            if seg <= 0.0:
                i = prev
                continue
            if seg >= remaining:
                t = remaining / seg
                px = pts[i][0] + (pts[prev][0] - pts[i][0]) * t
                py = pts[i][1] + (pts[prev][1] - pts[i][1]) * t
                remaining = 0.0
                break
            remaining -= seg
            i = prev
            px, py = pts[i]
        nxt = pts[(i + 1) % n]
        heading = math.degrees(math.atan2(nxt[0] - px, -(nxt[1] - py)))
        return (px, py), heading, i

    # Ring/trioval-style start: every car ON the start line, spread across
    # the track width. Slot 0 is the centreline so champion/showcase runs are
    # unaffected. A static collision scan puts the road edge of this straight
    # at |lateral| = 22 px, so 16 px leaves a real margin.
    _LATERAL_SLOTS = (0.0, -8.0, 8.0, -16.0, 16.0)

    def compute_spawn_pos(self, spawn_index):
        """Every car starts ON the start line, spread across the road width."""
        # All 30 evolution cars start on the line like ring/trioval (5
        # lateral slots, 6 cars per slot). A per-row backward column would
        # give every car a different spawn point -- and a spawn-position
        # fitness bias.
        lateral = self._LATERAL_SLOTS[spawn_index % len(self._LATERAL_SLOTS)]
        ox, oy = self.spawn_outside_dir
        return self.spawn_pos[0] + ox * lateral, self.spawn_pos[1] + oy * lateral

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

    def update_race_events(self, car):
        """Per-frame figure-8 race rules, called from Car.update in every mode.

        1. REVERSE = DEATH. There is no reverse gear (speed is constant), so
           "driving backwards" means the car turned around and travels against
           the path direction. Detected as accumulated negative projection of
           the velocity onto the local path tangent (the figure-8-correct
           generalisation of ring's polar-angle check, which cannot be used
           here because the polar angle swings back and forth on a normal lap).

        2. LAPS = start-line passes holding BOTH gates. A lap only counts when
           the car touched the far end of BOTH loops since the previous line
           pass — on this geometry that is exactly one full figure-8 traversal.
           This makes the whole-loop skip (swinging back through the
           intersection instead of running the second loop) worth ZERO laps,
           while every partial shortcut stays free: how the car gets from gate
           to gate is its own business. Shortcuts pay via lap TIME (fixed time
           budget, fewer px per lap = more laps), never via skipped distance.

           A SINGLE loop crossed while holding one gate counts as a
           shortcut lap at 60% of a full lap (see self.shortcut_lap_value).
           It pays
           about +14% per unit distance, but demands the ~66 deg turn at the
           crossing every lap, which sits close to the 40 px reverse-death
           threshold — so it is an optimisation only a competent driver can
           cash in, not a farming exploit.

        A forward-only window tracker hallucinates checkpoints whenever the
        car leaves its window (argmin noise over far away points can credit
        up to 24 indices per frame); the rules below close that hole."""
        if not car.is_alive:
            return
        pts = self.circuit_path
        n = len(pts)

        # True nearest path point (full scan; n=320, cheap, and reused by
        # compute_fitness for silent tracker resyncs)
        best_d2 = float("inf")
        real_idx = 0
        for i in range(n):
            p = pts[i]
            dx = car.pos_x - p[0]
            dy = car.pos_y - p[1]
            dd = dx * dx + dy * dy
            if dd < best_d2:
                best_d2, real_idx = dd, i
        car._f8_real_idx = real_idx

        # ---- 1. reverse detection (tangent projection) ----
        tp = pts[(real_idx + 1) % n]
        tm = pts[(real_idx - 1) % n]
        t_dx, t_dy = tp[0] - tm[0], tp[1] - tm[1]
        t_len = math.hypot(t_dx, t_dy) or 1.0
        rad = math.radians(car.angle)
        vx = math.sin(rad) * car.speed
        vy = -math.cos(rad) * car.speed
        proj = (vx * t_dx + vy * t_dy) / t_len
        if proj < 0.0:
            car.reverse_accum -= proj
        else:
            car.reverse_accum = max(0.0, car.reverse_accum - proj)
        if car.reverse_accum > self.reverse_kill_dist:
            car.is_alive = False
            return

        # ---- 2. gates ----
        for g_id, g_pos in enumerate(self.gate_centers):
            dx = car.pos_x - g_pos[0]
            dy = car.pos_y - g_pos[1]
            if dx * dx + dy * dy < self.gate_radius2 and g_id not in car.gates_hit:
                car.gates_hit.add(g_id)
                car.gate_credits += 1

        # ---- 3. lap line (start line) ----
        # BOTH gates held  -> a full figure-8 traversal (one lap).
        # ONE gate held    -> a single loop: the car cut through the crossing
        #                     instead of running the other loop. Credited at
        #                     60% (see self.shortcut_lap_value), so taking the
        #                     shortcut pays per unit distance but never turns
        #                     into "farm the short loop forever for free laps".
        # Zero gates held  -> nothing (crossing the line twice without visiting
        #                     any gate must not score).
        # Crossing test: credit the frame the car centre goes from behind the
        # line plane to on/over it, while staying on the road. A proximity
        # circle would fire ~49 px early (the drawn band is ~6 px).
        dx = car.pos_x - self.line_pos[0]
        dy = car.pos_y - self.line_pos[1]
        along = dx * self.line_fwd[0] + dy * self.line_fwd[1]
        lateral = dx * self.line_side[0] + dy * self.line_side[1]
        prev = car.line_prev_along
        car.line_prev_along = along
        if prev is not None and prev < 0.0 <= along and abs(lateral) <= self.line_half_width:
            if len(car.gates_hit) >= 2:
                car.line_credits += 1
                car.lap_base_cp = car.checkpoints_passed
            elif len(car.gates_hit) == 1:
                car.shortcut_credits += 1
                car.lap_base_cp = car.checkpoints_passed
            car.gates_hit.clear()

    def get_lap_count(self, car):
        """Continuous lap progress -- drives BOTH the HUD and the race finish.

        Returns the integer ladder (1.0 per full figure-8, `shortcut_race_ratio`
        per single loop) plus the fraction of the lap in progress, so the HUD
        climbs smoothly instead of sitting on 0.00 for nine seconds and then
        jumping to 1.00. The in-progress fraction is the honest checkpoint
        count since the last scoring line pass over the 320 checkpoints of a
        full lap, clamped just below 1.0 so crossing the line is what actually
        completes a lap.

        RACE RULE: an armed line pass scores a whole lap (shortcut_race_ratio
        = 1.0) even when the car only ran one loop. Training is deliberately
        different -- compute_fitness pays only shortcut_ratio (0.6) for the
        same event -- so evolution is still pushed to look for the shortcut,
        while on track "crossing the line" means what a driver expects it to.
        """
        n = float(len(self.circuit_path))
        done = max(0, car.checkpoints_passed - car.lap_base_cp)
        frac = min(0.999, done / n)
        return (float(car.line_credits)
                + self.shortcut_race_ratio * float(car.shortcut_credits)
                + frac)

    def compute_fitness(self, car) -> float:
        """Honest checkpoint tracking while alive + event-driven lap scoring."""
        n = len(self.circuit_path)

        if car.is_alive:
            # ---- Honest tracker: forward window + distance gate + resync ----
            # The window is forward-only, but a match is only trusted when the
            # matched point is actually close to the car (<= 40 px, roughly the
            # road half-width). When the car shortcut-jumps across the
            # intersection, is knocked far off line, or backs out of the
            # window, the window's argmin would otherwise pick noisy far-away
            # points and hallucinate up to 24 checkpoints per frame — so
            # instead we silently resync to the TRUE nearest point and credit
            # nothing for the skipped distance (shortcuts pay via lap time,
            # never via checkpoint score).
            curr_idx = car.last_closest_idx
            search_range = 25
            min_d2 = float("inf")
            closest_idx = curr_idx
            for offset in range(-4, search_range):
                test_idx = (curr_idx + offset) % n
                pt = self.circuit_path[test_idx]
                d2 = (car.pos_x - pt[0]) ** 2 + (car.pos_y - pt[1]) ** 2
                if d2 < min_d2:
                    min_d2, closest_idx = d2, test_idx

            forward_step = (closest_idx - curr_idx) % n
            if 0 < forward_step < search_range and min_d2 <= 40.0 ** 2:
                car.checkpoints_passed += forward_step
                car.last_closest_idx = closest_idx
            else:
                car.last_closest_idx = getattr(car, "_f8_real_idx", curr_idx)

            # Heading & velocity alignment bonus
            p1 = self.circuit_path[car.last_closest_idx]
            p2 = self.circuit_path[(car.last_closest_idx + 1) % n]
            t_dx, t_dy = p2[0] - p1[0], p2[1] - p1[1]
            t_len = math.hypot(t_dx, t_dy)
            rad = math.radians(car.angle)
            c_dx, c_dy = math.sin(rad), -math.cos(rad)
            alignment = (c_dx * t_dx + c_dy * t_dy) / (t_len + 1e-5) if t_len > 0 else 0.0
        else:
            alignment = 0.0

        # ---- Event-driven fitness ----
        # A full honest lap (both loops) is worth ~12,000:
        #   line credit 3500 + 2 gates x 800 + 320 checkpoints x 8.
        # A single-loop shortcut lap is worth ~6,900:
        #   shortcut credit 2100 + 1 gate x 800 + 160 checkpoints x 8,
        # over half the distance -- so cutting pays about +14% per px, provided
        # the driver can survive the crossing turn.
        lap_score = float(car.line_credits) * self.full_lap_value
        shortcut_score = float(car.shortcut_credits) * self.shortcut_lap_value
        gate_score = float(car.gate_credits) * 800.0
        progress_score = float(car.checkpoints_passed) * 8.0
        speed_bonus = car.speed * 2.5
        alignment_bonus = max(0.0, alignment) * 4.0
        survival_bonus = car.time_alive * 0.2

        return max(0.0, lap_score + shortcut_score + gate_score
                   + progress_score + speed_bonus + alignment_bonus
                   + survival_bonus)