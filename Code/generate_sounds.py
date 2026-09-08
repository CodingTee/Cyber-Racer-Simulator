# -*- coding: utf-8 -*-
"""Generate the game's sound effects procedurally (stdlib only).

No external assets, no numpy: every WAV is synthesised here so the repo stays
self-contained and anyone can regenerate the sounds with `python generate_sounds.py`.

Every cue is a short one-shot (countdown, starter, crash, victory); there
is no continuous driving-loop bed.
"""
import math
import os
import random
import struct
import wave

RATE = 44100
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Sounds")


def write_wav(name, samples):
    """Write float samples (-1..1) as a mono 16-bit 44.1 kHz WAV.

    Values are clipped into the int16 range first, so an over-loud
    generator can never wrap around and produce a click.
    """
    path = os.path.join(OUT_DIR, name)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        frames = b"".join(struct.pack("<h", max(-32768, min(32767, int(s * 32767))))
                          for s in samples)
        w.writeframes(frames)
    return path


def envelope(i, n, attack=0.01, decay=6.0):
    """Fast attack, exponential decay."""
    t = i / float(RATE)
    a = min(1.0, t / attack) if attack > 0 else 1.0
    return a * math.exp(-decay * i / float(n))


def tone(freq, dur, decay=6.0, harmonics=((1.0, 1.0),), attack=0.01):
    n = int(RATE * dur)
    out = []
    for i in range(n):
        env = envelope(i, n, attack, decay)
        v = sum(amp * math.sin(2 * math.pi * freq * mult * i / RATE)
                for mult, amp in harmonics)
        out.append(0.9 * env * v / len(harmonics) if harmonics else 0.0)
    return out


def _saw(phase, harmonics=6):
    """Band-limited-ish saw wave: h-th harmonic at amplitude 1/h."""
    v = 0.0
    for h in range(1, harmonics + 1):
        v += math.sin(h * phase) / h
    return v / 1.6                       # ~normalise: sum(1/h) for h<=6 ~= 2.45


def engine_start(dur=1.10):
    """Ignition + rev flare + settle, then a long fade so it dies away.

    RPM curve (Hz, the fundamental firing frequency), keyed on ABSOLUTE
    seconds so that lengthening the tail only lengthens the settle:
        0.00-0.10  starter cranks  30 -> 120
        0.10-0.35  throttle flare 120 -> 165
        0.35-0.65  clutch out     165 -> 110
        0.65-end   hold           110  while the tail fades out
    The last FADE seconds ramp down on a raised cosine, so the car winds
    down instead of stopping dead.
    The pitch is tracked with an accumulating phase (not sin(2*pi*f*t)) so
    a changing frequency stays continuous instead of clicking.
    """
    FADE = 0.45                 # seconds of smooth wind-down at the end
    n = int(RATE * dur)
    rng = random.Random(2026)
    out, phase, lp = [], 0.0, 0.0
    for i in range(n):
        t = i / float(RATE)
        if t < 0.10:
            f = 30.0 + 90.0 * (t / 0.10)
        elif t < 0.35:
            f = 120.0 + 45.0 * ((t - 0.10) / 0.25)
        elif t < 0.65:
            f = 165.0 + (110.0 - 165.0) * ((t - 0.35) / 0.30)
        else:
            f = 110.0
        phase += 2 * math.pi * f / RATE
        body = _saw(phase, 7)
        lp += 0.30 * (rng.uniform(-1.0, 1.0) - lp)  # combustion noise
        k = min(t / 0.75, 1.0)
        env = min(1.0, t / 0.0136) * (0.55 + 0.45 * math.exp(-1.1 * k))
        if t > dur - FADE:                          # 1 -> 0, no cliff
            u = (t - (dur - FADE)) / FADE
            env *= 0.5 * (1.0 + math.cos(math.pi * u))
        out.append(0.95 * env * (0.85 * body + 0.18 * lp))
    return out

def _normalise(samples, target_rms=0.20, peak_cap=0.95):
    """Scale to a known loudness, then pull the peaks back if they would clip.

    Keeps every loop at a comparable level no matter how many partials went
    into it, so the per-sound volume in audio.py stays meaningful.
    """
    rms = math.sqrt(sum(v * v for v in samples) / len(samples)) or 1.0
    gain = target_rms / rms
    peak = max(abs(v) for v in samples) * gain
    if peak > peak_cap:
        gain *= peak_cap / peak
    return [v * gain for v in samples]


def explosion(dur=0.75):
    """Noise burst with a closing low-pass + a low-frequency thump."""
    n = int(RATE * dur)
    rng = random.Random(1337)          # deterministic: same file every run
    out, lp, thump_phase = [], 0.0, 0.0
    for i in range(n):
        k = i / float(n)
        # rapid attack, long tail
        env = min(1.0, i / 300.0) * math.exp(-4.5 * k)
        # one-pole low-pass whose cutoff sweeps down (debris -> rumble)
        cutoff = 0.45 * math.exp(-3.0 * k) + 0.02
        lp += cutoff * (rng.uniform(-1.0, 1.0) - lp)
        # low sine "thump" that drops in pitch as the blast expands
        thump_phase += 2 * math.pi * (110 - 70 * k) / RATE
        thump = 0.55 * math.sin(thump_phase) * math.exp(-5.0 * k)
        out.append(0.95 * env * (0.75 * lp + thump))
    return out


def fanfare(total=0.95):
    """Rising major arpeggio: the sting when somebody wins.

    C5 - E5 - G5 - C6, the last note held. The notes overlap on purpose so
    it reads as one gesture rather than four separate beeps.
    """
    notes = [(523.25, 0.00, 0.18),      # C5
             (659.25, 0.09, 0.18),      # E5
             (783.99, 0.18, 0.20),      # G5
             (1046.50, 0.30, 0.60)]     # C6, held
    n = int(RATE * total)
    out = [0.0] * n
    for freq, start, dur in notes:
        seg = tone(freq, dur, decay=3.2, attack=0.006,
                   harmonics=((1.0, 1.0), (2.0, 0.30), (3.0, 0.12)))
        i0 = int(start * RATE)
        for j, v in enumerate(seg):
            if i0 + j < n:
                out[i0 + j] += v
    return _normalise(out, target_rms=0.22, peak_cap=0.95)

SPECS = [
    # low "deng"  (A4) -- countdown
    ("ready.wav", lambda: tone(440.0, 0.32, decay=5.0,
                               harmonics=((1.0, 1.0), (2.0, 0.25)))),
    # high "deng" (A5, one octave up) -- GO!; same timbre, brighter + shorter
    ("go.wav", lambda: tone(880.0, 0.38, decay=5.5, attack=0.005,
                            harmonics=((1.0, 1.0), (2.0, 0.28), (3.0, 0.10)))),
    ("crash.wav", lambda: explosion(0.75)),
    # ignition -> throttle flare -> clutch out; fires on the green light
    ("engine_start.wav", lambda: engine_start(1.10)),
    # rising arpeggio when a player takes the win
    ("victory.wav", lambda: fanfare(0.95)),
]

if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, fn in SPECS:
        p = write_wav(name, fn())
        print("wrote", p)
