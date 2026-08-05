import neopixel
import machine
import time

LED_PIN    = 0
BUTTON_PIN = 27
NUM_LEDS   = 15

np     = neopixel.NeoPixel(machine.Pin(LED_PIN), NUM_LEDS)
button = machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

# ------------------------------------------------------------------
# Zones
# ------------------------------------------------------------------
LAYER1_RANGE = (10, 15)  # LEDs 10-14 — gently flickering magical fire
LAYER2_RANGE = (5, 10)   # LEDs 5-9   — same animation as layer 1, offset + whitened
LAYER3_RANGE = (0, 5)    # LEDs 0-4   — sparking embers

BRIGHTNESS = 1.0

# ------------------------------------------------------------------
# Layer 1 — magical fire, LEDs 10-14
# Flickers by wandering across a 4-color gradient (not just brightness),
# so the flame itself keeps shifting hue as it flickers. Slow and calm:
# long gaps between re-targeting, gentle easing.
# ------------------------------------------------------------------
LAYER1_PALETTE = [
    (255, 35,   35),
    (255, 0, 220),
    (255, 10, 255),
    (255, 0, 0),
    (0, 0, 255)
]
LAYER1_JOLT_MIN     = 30    # ticks between re-targeting — slow and calm
LAYER1_JOLT_MAX     = 90
LAYER1_SMOOTH_RISE  = 0.10
LAYER1_SMOOTH_FALL  = 0.06
LAYER1_BRIGHT_LO    = 0.85   # never goes properly dark — this is a magical flame, not embers
LAYER1_BRIGHT_HI    = 1.0

# ------------------------------------------------------------------
# Layer 2 — LEDs 5-9
# Mirrors layer 1's exact hue/brightness animation, delayed by ~500ms,
# but rendered through a "whitened" version of layer 1's palette
# (each color blended toward white) with peak brightness matched to
# the old LAYER2_COLOR = (232, 120, 60)'s value (~232/255).
# ------------------------------------------------------------------
# LAYER2_PALETTE = [
#     (232, 142, 142),  # whitened (255,35,35)
#     (232, 127, 217),  # whitened (255,0,220)
#     (232, 132, 232),  # whitened (255,10,255)
#     (232, 127, 127),  # whitened (255,0,0)
#     (127, 127, 232),  # whitened (0,0,255)
# ]
LAYER2_PALETTE = [
    (232, 120, 60),
    (225, 70,   70),
    (225, 35, 230),
    (255, 50, 255),
    (255, 70, 70),
    (70, 70, 255)
]
LAYER2_OFFSET_MS   = 500
LOOP_PERIOD_MS     = 50
LAYER2_OFFSET_TICKS = max(1, LAYER2_OFFSET_MS // LOOP_PERIOD_MS)  # ~10 ticks

# ------------------------------------------------------------------
# Layer 3 — sparking embers, LEDs 0-4
# A dim baseline that wanders across a slightly orange-shifted, dimmer
# version of layer 1's palette, and occasionally throws a soft spark
# that decays gently back into the embers. Shifts between its colors
# faster than the other layers, but still eases smoothly (no jumps).
# ------------------------------------------------------------------
LAYER3_PALETTE = [
    (101, 17, 90),   # dim, orange-shifted violet
    (132, 13, 26),   # dim, orange-shifted rose
    (129, 41, 22),   # dim, orange-shifted coral
    (139, 24, 90),   # dim, orange-shifted magenta
]
LAYER3_SPARK_COLOR = (255, 210, 160)   # warm, soft spark peak
LAYER3_JOLT_MIN    = 10    # re-target much more often than layer 1/2 — rapid drifting
LAYER3_JOLT_MAX    = 30
LAYER3_SMOOTH_RISE = 0.22   # faster easing than layer 1/2, but still a smooth fade, not a jump
LAYER3_SMOOTH_FALL = 0.14
LAYER3_BRIGHT_LO   = 0.4
LAYER3_BRIGHT_HI   = 0.65

LAYER3_SPARK_PROBABILITY = 0.0015   # chance per LED per tick of a spark — rare and gentle
LAYER3_SPARK_PEAK        = 0.55     # how strong a spark gets at most — soft, not a hard flash
LAYER3_SPARK_DECAY       = 0.94     # spark brightness multiplier applied each tick — slow, calm fade

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def lerp_color(a, b, t):
    t = clamp(t, 0.0, 1.0)
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )

def palette_color(palette, t):
    t      = clamp(t, 0.0, len(palette) - 1)
    idx    = int(t)
    frac   = t - idx
    if idx >= len(palette) - 1:
        return palette[-1]
    return lerp_color(palette[idx], palette[idx + 1], frac)

def scale_color(c, brightness):
    return (
        max(0, min(255, int(c[0] * brightness))),
        max(0, min(255, int(c[1] * brightness))),
        max(0, min(255, int(c[2] * brightness))),
    )

def all_off():
    for i in range(NUM_LEDS):
        np[i] = (0, 0, 0)
    np.write()

# --- xorshift32 PRNG (no stdlib random needed) ---
_rng = 2463534242

def randu():
    global _rng
    x = _rng
    x ^= (x << 13) & 0xFFFFFFFF
    x ^= (x >> 17) & 0xFFFFFFFF
    x ^= (x << 5)  & 0xFFFFFFFF
    _rng = x & 0xFFFFFFFF
    return (_rng & 0xFFFF) / 65535.0

# ----------------------------------------------------------------
# Layer 1 state — per LED: hue position along the gradient, and
# brightness, each wandering independently with the same asymmetric
# smoothing (snap toward a new target a bit faster than easing away).
# ----------------------------------------------------------------
n1 = LAYER1_RANGE[1] - LAYER1_RANGE[0]
l1_hue        = [randu() * (len(LAYER1_PALETTE) - 1) for _ in range(n1)]
l1_hue_target = list(l1_hue)
l1_bright     = [LAYER1_BRIGHT_LO + randu() * (LAYER1_BRIGHT_HI - LAYER1_BRIGHT_LO) for _ in range(n1)]
l1_bright_target = list(l1_bright)
l1_jolt       = [int(randu() * LAYER1_JOLT_MAX) for _ in range(n1)]

# ----------------------------------------------------------------
# Layer 2 state — no independent jolt/smoothing state of its own.
# It replays layer 1's (hue, brightness) history, delayed by
# LAYER2_OFFSET_TICKS, through LAYER2_PALETTE instead of LAYER1_PALETTE.
# n2 must match n1 since it's a 1:1 per-LED playback of layer 1.
# ----------------------------------------------------------------
n2 = LAYER2_RANGE[1] - LAYER2_RANGE[0]
assert n2 == n1, "Layer 2 mirrors layer 1 per-LED, so the zones must be the same size"
l1_history = []  # each entry: (list_of_hues_copy, list_of_brights_copy)

# ----------------------------------------------------------------
# Layer 3 state — per LED: hue position wandering across LAYER3_PALETTE
# and baseline ember brightness, both as usual, plus an independent
# spark level that's normally 0 and decays back down after occasionally
# firing.
# ----------------------------------------------------------------
n3 = LAYER3_RANGE[1] - LAYER3_RANGE[0]
l3_hue           = [randu() * (len(LAYER3_PALETTE) - 1) for _ in range(n3)]
l3_hue_target    = list(l3_hue)
l3_bright        = [LAYER3_BRIGHT_LO + randu() * (LAYER3_BRIGHT_HI - LAYER3_BRIGHT_LO) for _ in range(n3)]
l3_bright_target = list(l3_bright)
l3_jolt          = [int(randu() * LAYER3_JOLT_MAX) for _ in range(n3)]
l3_spark         = [0.0 for _ in range(n3)]

leds_on    = True
last_press = 0

while True:
    now = time.ticks_ms()

    if button.value() == 0 and time.ticks_diff(now, last_press) > 200:
        leds_on = not leds_on
        last_press = now
        if not leds_on:
            all_off()

    if leds_on:
        # ---------------- Layer 1: magical fire -------------------
        for i in range(n1):
            l1_jolt[i] -= 1
            if l1_jolt[i] <= 0:
                l1_hue_target[i]    = randu() * (len(LAYER1_PALETTE) - 1)
                l1_bright_target[i] = LAYER1_BRIGHT_LO + randu() * (LAYER1_BRIGHT_HI - LAYER1_BRIGHT_LO)
                l1_jolt[i]          = int(LAYER1_JOLT_MIN + randu() * (LAYER1_JOLT_MAX - LAYER1_JOLT_MIN))

            dh = l1_hue_target[i] - l1_hue[i]
            db = l1_bright_target[i] - l1_bright[i]
            l1_hue[i]    += dh * (LAYER1_SMOOTH_RISE if dh > 0 else LAYER1_SMOOTH_FALL)
            l1_bright[i] += db * (LAYER1_SMOOTH_RISE if db > 0 else LAYER1_SMOOTH_FALL)

            color = palette_color(LAYER1_PALETTE, l1_hue[i])
            led   = LAYER1_RANGE[0] + i
            np[led] = scale_color(color, l1_bright[i] * BRIGHTNESS)

        # ---------------- Layer 2: layer 1's animation, delayed + whitened ----
        l1_history.append((list(l1_hue), list(l1_bright)))
        if len(l1_history) > LAYER2_OFFSET_TICKS:
            l1_history.pop(0)
        delayed_hue, delayed_bright = l1_history[0]

        for i in range(n2):
            color = palette_color(LAYER2_PALETTE, delayed_hue[i])
            led   = LAYER2_RANGE[0] + i
            np[led] = scale_color(color, delayed_bright[i] * BRIGHTNESS)

        # ---------------- Layer 3: sparking embers ------------------
        for i in range(n3):
            l3_jolt[i] -= 1
            if l3_jolt[i] <= 0:
                l3_hue_target[i]    = randu() * (len(LAYER3_PALETTE) - 1)
                l3_bright_target[i] = LAYER3_BRIGHT_LO + randu() * (LAYER3_BRIGHT_HI - LAYER3_BRIGHT_LO)
                l3_jolt[i]          = int(LAYER3_JOLT_MIN + randu() * (LAYER3_JOLT_MAX - LAYER3_JOLT_MIN))

            dh = l3_hue_target[i] - l3_hue[i]
            db = l3_bright_target[i] - l3_bright[i]
            l3_hue[i]    += dh * (LAYER3_SMOOTH_RISE if dh > 0 else LAYER3_SMOOTH_FALL)
            l3_bright[i] += db * (LAYER3_SMOOTH_RISE if db > 0 else LAYER3_SMOOTH_FALL)

            if l3_spark[i] > 0.02:
                l3_spark[i] *= LAYER3_SPARK_DECAY
            elif randu() < LAYER3_SPARK_PROBABILITY:
                l3_spark[i] = LAYER3_SPARK_PEAK * (0.8 + randu() * 0.2)

            base_color = scale_color(palette_color(LAYER3_PALETTE, l3_hue[i]), l3_bright[i])
            color      = lerp_color(base_color, LAYER3_SPARK_COLOR, l3_spark[i])

            led   = LAYER3_RANGE[0] + i
            np[led] = scale_color(color, BRIGHTNESS)

        np.write()

    time.sleep_ms(50)