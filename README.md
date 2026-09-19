# Cyber Racer Simulator

**A multi-track NEAT neural-evolution engine, wrapped in a playable racing game.**

Cars here are not scripted. They are driven by small neural networks whose *topology and weights are both
evolved from scratch*: the network starts with zero hidden neurons and no connections, and NEAT grows
whichever structure survives. You can watch the whole thing happen: the HUD draws the live network of the
current leader next to the car it is steering.

> Demo: [Watch on YouTube](https://www.youtube.com/watch?v=gHnUnb1GFCk) (local copy: [`Demo Video.mp4`](./Demo%20Video.mp4))

---

## At a glance

Fitness recorded in each shipped champion checkpoint (`Code/best_car_model_*.pkl`):

| Circuit | Champion fitness |
|---|---|
| Ring | 9,410.6 |
| **Spline** | **21,552.6** |
| Tri-Oval | 25,148.9 |
| Figure-8 | 35,194.9 |

These are training-scope scores, not lap times. The numbers are not comparable across circuits, because
each track owns its own fitness function (that is the point: "progress" means something different on an
oval than on a figure-8). What makes a champion trustworthy is not its fitness but how it behaves from
starts it never trained on. See [Evaluation](#evaluation).

---

## Quick start

```bash
pip install pygame-ce neat-python

cd Code
python main.py
```

Python 3.13, `pygame-ce` 2.5.x, `neat-python` 2.0.x. Runs fullscreen at 1440x810.

Every bundled asset (sprites, sound effects, the NEAT config and the trained checkpoints) is
resolved against `Code/` itself rather than the working directory, so `python Code/main.py` from
the repository root loads the same models as `python main.py` from inside `Code/`.

Sound effects are generated on first run into `Code/Sounds/`. The repo ships the generator
(`generate_sounds.py`), not the WAVs, so nothing is a binary blob you cannot regenerate.

## Controls

Cars drive at a constant speed; the network (and you) only control steering.

| | |
|---|---|
| **P1 steer** | `←` `→` or `A` `D` |
| **P2 steer** (local PvP) | `A` `D` |
| **Start / restart** | `Space` |
| **Confirm restart** | `R` |
| **Back to menu** | `Esc` |

## Modes

1. **Single Player (vs AI):** you in the red F1 against the evolved champion in the yellow one.
2. **Two Players (local PvP):** two humans, one keyboard, same lap target.
3. **Training Camp:** solo test drive with the LiDAR rays drawn, useful for feeling out a circuit.
4. **AI Evolution Method:** live evolution. The population's current leader races the previous champion;
   press `Esc` when you are happy and the best genome is written to `Code/best_car_model_<track>.pkl`.

## Circuits

`Ring` · `Tri-Oval` · `Figure-8` · `Spline`. Each owns its geometry, wall mask, ray casting *and* its own
fitness function, because the honest way to grade progress differs per shape (polar angle for the ring,
gate events for the figure-8, checkpoints elsewhere).

---

## How the AI learns

**Inputs:** 7 LiDAR rays swept across the car's front, each returning normalised distance to the nearest
wall (1.0 = nothing in range). Plus nothing else: no position, no velocity, no map. The network has to
infer "which way is the road" from a 7-number snapshot, 60 times a second.

**Outputs:** 2 neurons, left and right. Steering is `right − left`.

**Start state:** `num_hidden = 0`. Every hidden neuron and every connection in a champion was added by
mutation and kept because it helped. Population 30, elitism 1, stagnation limit 20.

**Fitness is event-driven**, not distance-based:

| Event | Reward |
|---|---|
| Passing the start/finish line | 3,500 (full lap) |
| Holding a gate / checkpoint | 800 / 8 per checkpoint |
| Speed, road alignment, survival | small continuous terms |

Distance-based fitness is gameable: a car that hugs the inside of a corner or oscillates in place can
accumulate it. Per-lap credit cannot be farmed without actually finishing laps.

**Curriculum spawning** (Spline) rotates the spawn point around the track as generations advance, so a
champion has to know the whole circuit rather than memorise one start.

### Anti-cheating rules, and why they exist

Evolution is very good at finding the hole in your scoring function. Three of them were closed here:

- **Figure-8: driving in reverse is fatal.** Accumulating 40 px of net backward travel along the path
  tangent kills the car. A 74 px-wide road cannot U-turn, so legitimate driving never triggers it, but it
  stops a car from "lapping" by rocking back and forth over the line.
- **Checkpoint tracking refuses to guess.** If the nearest-path-point match is more than 40 px from the car,
  the match is discarded rather than trusted. Without this, plain `argmin` noise credited cars with up to
  24 checkpoints per frame while they sat still.
- **The finish line is a crossing test, not a proximity circle.** A circle wide enough to be reliable fires
  ~49 px before the car reaches the line; the line is only ~6 px wide on screen, so the race would end
  while the car is visibly short of it. The code watches the sign of the along-track offset instead.

### Evaluation

Fitness alone does not tell you whether a champion can drive, only that it scored well from the spawn
points it happened to see. Champions are therefore re-driven from **20 different spawn points** and graded
on how many of the 20 they complete (not on their score in any single one). Five points is enough to make a
car with a few blind spots look fine; twenty is not.

A worked example of why this matters: the Spline champion was tested against a "fixed" version of its own
progress metric that removes an apparent bug (an absolute path index that looks like it should be
spawn-relative). Fitness reasoning said the fix should help. Twenty-point hold-out said otherwise:

| Seed | Shipped (absolute) | "Fixed" (spawn-relative) |
|---|---|---|
| 12345 | 3.33 | 2.12 |
| 777 | 3.30 | 0.05 |
| 4242 | 0.07 | 0.05 |
| 999 | 3.55 | 0.18 |

The apparent defect is doing something useful. It is still there, on purpose, with a comment explaining
that it must not be "fixed".

### Figure-8: which basin a run lands in is a lottery

The figure-8 fitness landscape has more than one stable outcome: a champion can farm the single-loop
shortcut (worth 60% of a full lap) or run the complete figure-8. Six runs, identical code and identical
parameters, 150 generations each:

![Behavioural basins on the figure-8 track. Six panels, one per random seed, each plotting best and mean fitness over 150 generations. Background shading marks the strategy the champion has settled into: orange for the shortcut basin, green for the full-lap basin, grey for no strategy. Red dashed lines mark extinction resets.](docs/figure8_basin_analysis.png)

Shading marks the regime the champion is in: **orange** = shortcut basin, **green** = full figure-8
basin, **grey** = never learned to lap at all. Red dashes are extinction resets. One of the six never
forms a strategy; two leave the shortcut for the full-lap basin, but only late in the run; the
remaining three farm the shortcut for all 150 generations.

Which basin a run lands in is decided by the seed, not by tuning. All six panels are the same code with
the same parameters. The honest summary is therefore not "the AI learns the track" but "the AI reliably
learns *a* strategy, and which one is close to a coin flip". That is precisely why a champion is graded
on held-out starts rather than on its fitness number.

---

## Engineering notes

- **Sound is synthesised, not sampled.** `generate_sounds.py` builds every cue with the standard library
  (no numpy, no asset files). Seamless loops work by snapping every partial to a multiple of `1/duration`;
  the ignition sound winds down on a raised-cosine tail so it never clicks off.
- **Saving a model must not perturb evolution.** `neat-python`'s `DefaultGenomeConfig.__getstate__`
  consumes a value from a live `itertools.count` node indexer, so *pickling a genome changes the future
  trajectory of the run*. `model_io.save_trained_model` clones the genome before serialising it and
  restores the original state afterwards.
- **NEAT passes elites by reference.** A new champion is deep-copied the moment it appears.
- **Overlays share one anchor.** Figure-8 and Tri-Oval deliberately offset their HUD anchor away from the
  geometric centre so text does not sit on top of the road; every centred overlay reads the same
  `overlay_anchor`, so countdown cues and generation labels cannot drift apart.

## Project structure

```
Cyber Racer Simulator/
├── Code/                       # the application
│   ├── main.py                 # menu + the four game modes
│   ├── car.py                  # physics, LiDAR, sprite
│   ├── ai_evolution.py         # NEAT training loop
│   ├── model_io.py             # genome persistence (with the pickle-guard above)
│   ├── audio.py                # thin mixer layer; silent if audio is unavailable
│   ├── generate_sounds.py      # regenerates Code/Sounds/*.wav
│   ├── settings.py  ui.py
│   ├── tracks/                 # one module per circuit (geometry + fitness)
│   ├── Sounds/  Pictures/      # generated audio, car liveries
│   └── best_car_model_*.pkl    # trained champions
├── docs/                       # figure-8 behavioural basin analysis (shown above)
├── Demo Video.mp4
└── README.md
```

## Known limitations

- Fitness numbers are per-circuit and cannot be compared across rows in the table above.
- Audio is one-shot only (countdown, ignition, crash, victory). The continuous driving loop was cut after
  six attempts that did not survive listening tests. The best synthesised recipe is kept in the archived
  scripts for anyone who wants to retry.
- Evolution has no generation cap: press `Esc` when you are satisfied. Breakthroughs usually land
  somewhere between generation 90 and 200.

## Author

**Tee Yi Xuan.** Built as a portfolio project. The AI is the point; the game is the harness.
