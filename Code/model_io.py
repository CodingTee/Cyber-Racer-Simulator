# =============================================================================
# model_io.py -- persist and restore the trained NEAT champion.
#
# A checkpoint is a plain pickle of {"genome", "config"}; the feed-forward
# network is rebuilt from the genome on load. Saving is deliberately free of
# side effects -- see save_trained_model for why that is not automatic.
# =============================================================================
import os
import copy
import pickle
import neat

# Checkpoints live next to this module. Bare filenames are anchored to that
# directory, so launching from anywhere reads and writes the same archive
# instead of silently starting a second one in the caller's folder.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def resolve_path(filename):
    """Anchors a bare filename to the module directory when it is not found.

    Absolute paths and paths that already exist relative to the working
    directory are returned untouched, so callers that pass a correct path keep
    their current behaviour.
    """
    if os.path.isabs(filename) or os.path.exists(filename):
        return filename
    return os.path.join(_BASE_DIR, filename)


def load_trained_model(filename):
    """Load (net, genome, config) from a checkpoint pickle.

    Returns (None, None, None) for every failure -- missing file, corrupt
    pickle, or a genome whose topology no longer matches the config -- so
    callers can treat "no trained model yet" as an ordinary state.
    """
    filename = resolve_path(filename)
    if not os.path.exists(filename):
        return None, None, None
    try:
        with open(filename, "rb") as f:
            data = pickle.load(f)
            genome = data["genome"]
            config = data["config"]
            net = neat.nn.FeedForwardNetwork.create(genome, config)
            return net, genome, config
    except Exception as e:
        print(f"Failed to load {filename}: {e}")
        return None, None, None


def save_trained_model(filename, genome, config):
    """Persist the best genome. Must not perturb the running evolution.

    NEAT-PYTHON SIDE EFFECT WORKED AROUND HERE
    ------------------------------------------
    `DefaultGenomeConfig.__getstate__` (neat/genome.py) serialises the
    `node_indexer` - an `itertools.count` - by consuming one value from it:

        state['_node_indexer_next_value'] = next(self.node_indexer)

    The counter is shared with the live config, so every checkpoint used up
    one node ID. The next structural mutation then received a different node
    key than it would have had, which reshuffles the innovation numbering and
    reroutes the entire evolutionary trajectory.

    Measured on spline_gp, seed 12345, 100 generations, identical start with
    no archive present: training WITH checkpointing reached 0.06 laps, while
    training WITHOUT it reached 3.33 laps. Same code, same seed.

    Fix: give pickle a clone of the counter so it consumes from the clone,
    then restore the live one. Checkpointing becomes read-only again.
    """
    genome_config = getattr(config, "genome_config", None)
    live_indexer = getattr(genome_config, "node_indexer", None)
    if live_indexer is not None:
        genome_config.node_indexer = copy.copy(live_indexer)
    try:
        with open(resolve_path(filename), "wb") as f:
            pickle.dump({"genome": genome, "config": config}, f)
    except Exception as e:
        print(f"Failed to save {filename}: {e}")
    finally:
        if live_indexer is not None:
            genome_config.node_indexer = live_indexer
