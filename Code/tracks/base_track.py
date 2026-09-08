# =============================================================================
# base_track.py -- the contract every circuit implements, plus the shared
# starting-grid maths that the spline-based tracks reuse.
# =============================================================================
import math


class BaseTrack:
    """Abstract circuit: geometry, collision, LiDAR, fitness and spawn grid.

    Subclasses must implement compute_spawn_pos, check_collision, cast_rays
    and compute_fitness. update_race_events is optional and defaults to a
    no-op -- only the figure-8 needs per-frame rules on top.
    """
    def __init__(self, track_id, name, description):
        """Store identity plus the defaults a subclass overrides."""
        self.id = track_id
        self.name = name
        self.description = description
        self.surface = None
        self.model_filename = f"best_car_model_{self.id}.pkl"
        self.max_gen_duration = 30.0
        self.center = (0, 0)
        self.spawn_pos = (0, 0)
        self.spawn_angle = 90.0

    def compute_spawn_pos(self, spawn_index):
        """Screen position where car `spawn_index` starts. Must be overridden."""
        raise NotImplementedError

    def check_collision(self, car) -> bool:
        """True when the car's rotated sprite overlaps a wall/kerb pixel."""
        raise NotImplementedError

    def cast_rays(self, car, sensor_angles, max_length) -> tuple:
        """Cast one ray per sensor angle; return (endpoints, 0..1 readings).

        A reading of 1.0 means nothing was hit within max_length; 0.0 means
        the wall is touching the car. These seven numbers are the NEAT net's
        entire view of the world.
        """
        raise NotImplementedError

    def compute_fitness(self, car) -> float:
        """Training score for this car, sampled once per simulated frame."""
        raise NotImplementedError

    def update_race_events(self, car):
        """Per-frame race-event bookkeeping (lap gates, lap line, reverse
        detection), called from Car.update on every frame in every mode.
        Default: no-op. Only tracks with special rules (figure-8) override."""
        pass

    # ---- Shared ring-style starting grid (used by all spline-based tracks) ----

    def _compute_spawn_outside_dir(self, idx):
        """Unit vector pointing to the OUTSIDE of the upcoming corner at
        circuit_path[idx] (the side the track curves away from). The outside
        slot travels a longer line, so it is the slot that gets the head start."""
        n = len(self.circuit_path)
        p0 = self.circuit_path[idx]
        p1 = self.circuit_path[(idx + 1) % n]
        p2 = self.circuit_path[(idx + 2) % n]
        v1 = (p1[0] - p0[0], p1[1] - p0[1])
        v2 = (p2[0] - p1[0], p2[1] - p1[1])
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        rad = math.radians(self.spawn_angle)
        tx, ty = math.sin(rad), -math.cos(rad)
        # cross > 0 -> turning toward the (-ty, tx) side -> outside is (ty, -tx)
        return (ty, -tx) if cross >= 0 else (-ty, tx)

    def _compute_spawn_grid(self, spawn_index, lateral_off=7.0, stagger_off=6.0, row_gap=12.0):
        """Ring-style 2-wide grid, identical layout logic to ring_circuit.

        Row 0 (the multiplayer / vs-AI start):
          slot 0 -> OUTSIDE of the next corner, starts stagger_off px AHEAD
          slot 1 -> INSIDE,                    starts stagger_off px BEHIND
        Later rows (evolution) step `row_gap` px backward along the track.

        Keeping the outside slot ahead means two cars running the identical
        algorithm stay level instead of the trailing slot losing by default.
        """
        px, py = self.spawn_pos
        ox, oy = self.spawn_outside_dir
        rad = math.radians(self.spawn_angle)
        tx, ty = math.sin(rad), -math.cos(rad)

        if spawn_index % 2 == 0:
            lateral, stagger = lateral_off, stagger_off
        else:
            lateral, stagger = -lateral_off, -stagger_off
        longitudinal = -float(spawn_index // 2) * row_gap

        return (px + ox * lateral + tx * (stagger + longitudinal),
                py + oy * lateral + ty * (stagger + longitudinal))