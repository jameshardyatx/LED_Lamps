import neopixel
import machine
import time

LED_PIN    = 0
BUTTON_PIN = 27
NUM_LEDS   = 15

np     = neopixel.NeoPixel(machine.Pin(LED_PIN), NUM_LEDS)
button = machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

# ------------------------------------------------------------------
# The two knobs you asked for — everything else derives from these
# ------------------------------------------------------------------
STORM_SPEED     = 1.0   # 0.3 (slow, rolling storm) .. 3.0 (frantic, right overhead)
STORM_INTENSITY = 1.0   # 0.3 (distant heat lightning) .. 2.0 (violent, blinding)
# At these defaults the strip is meant to be constantly crackling — dim
# electric-blue glow with restless individual sparks and frequent bigger
# multi-flash strikes, never fully dark.

# Palette — storm sky arcing up to a lightning-white core
# Dark, cold cloud tones through electric blue to blinding white
# PALETTE = [
#     (0,   0,   0  ),  # pitch black
#     (2,   3,   8  ),  # deep storm cloud // #080701
#     (8,   10,  22 ),  # cloud underbelly glow // #161308
#     (30,  38,  70 ),  # charged cloud, pre-strike // #463E23
#     (110, 130, 200),  # electric blue // #DB9F15
#     (195, 210, 255),  # near-white blue // #C87600
#     (255, 255, 255),  # blinding white core // #FFF4DA
# ]

PALETTE = [
    (0, 0, 0),
    (16, 7 , 1),
    (44, 19, 8),
    (70, 62, 15),
    (227, 105, 23),
    (240, 118, 0),
    (255, 244, 218)
]

BRIGHTNESS = 1.0   # lightning is violent and bright

def lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )

def storm_color(value):
    value  = max(0.0, min(1.0, value))
    scaled = value * (len(PALETTE) - 1)
    idx    = int(scaled)
    frac   = scaled - idx
    if idx >= len(PALETTE) - 1:
        return PALETTE[-1]
    return lerp_color(PALETTE[idx], PALETTE[idx + 1], frac)

def scale_color(c, brightness):
    return (
        int(c[0] * brightness),
        int(c[1] * brightness),
        int(c[2] * brightness),
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
# Storm state
#
# Two layers, same as a real storm:
#   - AMBIENT: every LED sits at a dim, drifting cloud-glow level,
#     each with its own slow random walk so the "sky" never looks
#     static.
#   - STRIKE: a shared event that overrides the ambient layer and
#     snaps every LED toward a bright core, in a short burst of
#     multiple flashes (real lightning almost never fires just
#     once), then decays back down into the clouds.
# ----------------------------------------------------------------

# Per-LED smoothed intensity currently displayed
intensity  = [randu() * 0.08 for _ in range(NUM_LEDS)]

# Per-LED ambient target the smoother is chasing
target     = [0.03 + randu() * 0.05 for _ in range(NUM_LEDS)]

# Per-LED countdown ticks until a new ambient target is picked
jolt_timer = [int(randu() * 6) for _ in range(NUM_LEDS)]

# Ambient tuning — dim, restless cloud glow. Kept well above zero so the
# sky always has a visible charge to it instead of ever going fully dark.
AMBIENT_LO       = 0.22
AMBIENT_HI       = 0.38
AMBIENT_JOLT_MIN = 1
AMBIENT_JOLT_MAX = 3   # short so the ambient hum itself keeps re-rolling fast

# Quick individual-LED sparks layered on top of the ambient hum — this is
# what makes it read as "constantly crackling" rather than occasional
# isolated strikes. Independent per LED, independent of the big strikes.
CRACKLE_PROB     = 0.10   # chance per LED per tick
CRACKLE_LO       = 0.45
CRACKLE_HI       = 0.75
CRACKLE_LIFETIME = 2      # ticks before it reverts to ambient

# Asymmetric smoothing: snap up fast, decay slower
SMOOTH_RISE = 0.9
SMOOTH_FALL = 0.35

# Strike state machine
STATE_AMBIENT   = 0
STATE_FLASH_ON  = 1
STATE_FLASH_GAP = 2
STATE_DECAY     = 3

state             = STATE_AMBIENT
flashes_remaining = 0
strike_peak       = 0.0
state_timer       = 0     # ticks left in the current sub-state
decay_step        = 0
DECAY_STEPS       = 5

# Base probability a strike begins on any given tick, scaled by intensity
STRIKE_PROB = 0.02

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
        # --- ambient cloud layer: always running underneath -------
        for i in range(NUM_LEDS):
            jolt_timer[i] -= 1
            if jolt_timer[i] <= 0:
                target[i]     = AMBIENT_LO + randu() * (AMBIENT_HI - AMBIENT_LO)
                jolt_timer[i] = int(AMBIENT_JOLT_MIN + randu() * AMBIENT_JOLT_MAX)

            # crackle: quick individual sparks on top of the ambient hum,
            # independent of the big multi-flash strikes below
            if randu() < CRACKLE_PROB * STORM_INTENSITY:
                target[i]     = CRACKLE_LO + randu() * (CRACKLE_HI - CRACKLE_LO)
                jolt_timer[i] = CRACKLE_LIFETIME

        # --- strike state machine ----------------------------------
        if state == STATE_AMBIENT:
            if randu() < STRIKE_PROB * STORM_INTENSITY:
                flash_count       = 1 + int(randu() * 3) + int(STORM_INTENSITY)
                flashes_remaining = max(1, min(6, flash_count))
                state             = STATE_FLASH_ON
                strike_peak       = 0.75 + randu() * 0.25 * min(1.5, STORM_INTENSITY)
                strike_peak       = min(1.0, strike_peak)
                state_timer       = max(1, int((2 + randu() * 4) / STORM_SPEED))

        elif state == STATE_FLASH_ON:
            for i in range(NUM_LEDS):
                # slight per-LED jitter so the flash isn't a flat wall
                target[i] = strike_peak * (0.85 + randu() * 0.15)
            state_timer -= 1
            if state_timer <= 0:
                flashes_remaining -= 1
                if flashes_remaining > 0:
                    state       = STATE_FLASH_GAP
                    state_timer = max(1, int((2 + randu() * 5) / STORM_SPEED))
                else:
                    state      = STATE_DECAY
                    decay_step = DECAY_STEPS

        elif state == STATE_FLASH_GAP:
            for i in range(NUM_LEDS):
                target[i] = AMBIENT_LO + randu() * 0.05
            state_timer -= 1
            if state_timer <= 0:
                strike_peak = 0.7 + randu() * 0.3 * min(1.5, STORM_INTENSITY)
                strike_peak = min(1.0, strike_peak)
                state       = STATE_FLASH_ON
                state_timer = max(1, int((2 + randu() * 4) / STORM_SPEED))

        elif state == STATE_DECAY:
            t = decay_step / DECAY_STEPS
            for i in range(NUM_LEDS):
                target[i] = AMBIENT_LO + (strike_peak - AMBIENT_LO) * t * (0.85 + randu() * 0.15)
            decay_step -= 1
            if decay_step <= 0:
                state = STATE_AMBIENT

        # --- smoothing + render -------------------------------------
        for i in range(NUM_LEDS):
            delta = target[i] - intensity[i]
            if delta > 0:
                intensity[i] += delta * SMOOTH_RISE
            else:
                intensity[i] += delta * SMOOTH_FALL
            intensity[i] = max(0.0, min(1.0, intensity[i]))

            # Softer gamma than a pure ember effect — we want the ambient
            # floor to stay visibly lit, while flashes still punch through
            # as a clear spike against it
            v = intensity[i] ** 1.3

            np[i] = scale_color(storm_color(v), BRIGHTNESS)

        np.write()

    time.sleep_ms(max(4, int(30 / STORM_SPEED)))