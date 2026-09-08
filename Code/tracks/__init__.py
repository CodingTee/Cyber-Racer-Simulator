# =============================================================================
# tracks/ -- the four circuits.
#
# Each track module exposes one BaseTrack subclass that owns its geometry,
# its wall mask, its LiDAR casting and its fitness formula. get_all_tracks()
# is the factory the menu uses; building a track renders its whole surface,
# so it is done once and the surfaces are reused for the rest of the session.
# =============================================================================
from tracks.ring_circuit import RingCircuitTrack
from tracks.trioval_circuit import TriOvalCircuitTrack
from tracks.figure8_circuit import Figure8CircuitTrack
from tracks.spline_circuit import SplineCircuitTrack

def get_all_tracks():
    """Instantiate every circuit; list order = menu carousel order."""
    return [
        RingCircuitTrack(),
        TriOvalCircuitTrack(),
        Figure8CircuitTrack(),
        SplineCircuitTrack()
    ]