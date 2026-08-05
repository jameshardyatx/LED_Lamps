import neopixel
import machine
import time
import math

LED_PIN    = 0
BUTTON_PIN = 27
NUM_LEDS   = 15

np     = neopixel.NeoPixel(machine.Pin(LED_PIN), NUM_LEDS)
button = machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

# Palette — Matrix code rain
# Index 0 = the top of the strip (where new "characters" spawn),
# rising index = falling downward.
# #c8ffc8 near-white glyph head (the character actively "printing")
# Trail decays through phosphor green down to black as glyphs age out
# PALETTE = [
#     (0,   0,   0  ),  # dead black — no glyph here
#     (0,   12,  0  ),  # barely-there residual glow
#     (0,   45,  4  ),  # deep phosphor green trail
#     (0,   110, 20 ),  # mid green — aged glyph
#     (20,  180, 50 ),  # brighter green — recent glyph
#     (110, 255, 130),  # fresh glyph, glowing
#     (200, 255, 200),  # #c8ffc8 — near-white head
#     (235, 255, 235),  # blinding white-green overload (rare double-strike)
# ]

PALETTE = [
    (0,   0,   0  ),  # dead black — no glyph here
    (0,   12,  0  ),  # barely-there residual glow
    (0,   45,  4  ),  # deep phosphor green trail
    (0,   110, 20 ),  # mid green — aged glyph
    (20,  180, 50 ),  # brighter green — recent glyph
    (55, 255, 60),  # fresh glyph, glowing
    (55, 255, 55),  # #c8ffc8 — near-white head
    (100, 255, 100),  # blinding white-green overload (rare double-strike)
]

BRIGHTNESS = 1.0   # the code always runs at full glow

def lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )

def rain_color(value):
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
# Rain state per LED
# Each LED independently models a tiny stretch of "code column" that:
#   - sits dark most of the time (empty screen space)
#   - occasionally has a glyph head snap in, bright near-white-green
#   - propagates its glow DOWNWARD only (i -> i+1), like a falling drop
#   - decays slowly through the green trail back to black behind it
#   - flickers faintly while in the trail, as if the glyph were still
#     changing character before it fully fades
# ----------------------------------------------------------------

# Smoothed intensity value currently displayed
intensity   = [0.0 for _ in range(NUM_LEDS)]

# Target the smoother is chasing
target      = [0.0 for _ in range(NUM_LEDS)]

# Countdown ticks until this LED's trail flickers to a new value
jolt_timer  = [int(randu() * 8) for _ in range(NUM_LEDS)]

# Propagation carry: a bright head on LED i seeds a falling drop at i+1
carry       = [0.0] * NUM_LEDS

# Tuning
SMOOTH_RISE   = 0.9    # fast snap upward — a glyph head appears instantly
SMOOTH_FALL   = 1.12    # slow green decay — trails linger like phosphor
JOLT_MIN      = 1
JOLT_MAX      = 8
SPAWN_PROB    = 0.05   # probability a brand-new drop enters at the top (i=0)
FLICKER_PROB  = 0.45   # probability an existing trail glyph flickers
PROPAGATE     = 0.78   # how much of a head's glow carries into the next LED down
TRAIL_LO      = 0.08   # faint residual trail floor
TRAIL_HI      = 0.30   # faint residual trail ceiling

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
        new_carry = [0.0] * NUM_LEDS

        for i in range(NUM_LEDS):
            r = randu()

            if carry[i] > 0.05:
                # A drop is falling into this LED from the one above
                target[i]     = 0.78 + carry[i] * 0.22
                jolt_timer[i] = 1
                # Pass the (slightly weaker) head onward, downward only
                if i < NUM_LEDS - 1:
                    new_carry[i + 1] = max(new_carry[i + 1], carry[i] * PROPAGATE)

            elif i == 0 and r < SPAWN_PROB:
                # A brand-new glyph enters at the top of the strip
                spike         = 0.85 + randu() * 0.15
                target[i]     = spike
                jolt_timer[i] = 1
                if NUM_LEDS > 1:
                    new_carry[1] = max(new_carry[1], spike * PROPAGATE)

            elif intensity[i] > TRAIL_LO and r < FLICKER_PROB:
                # Trailing glyph flickers to a new character before fading
                jolt_timer[i] -= 1
                if jolt_timer[i] <= 0:
                    target[i]     = TRAIL_LO + randu() * (TRAIL_HI - TRAIL_LO)
                    jolt_timer[i] = int(JOLT_MIN + randu() * JOLT_MAX)

            else:
                # Otherwise keep decaying toward black, no new target
                jolt_timer[i] -= 1
                if jolt_timer[i] <= 0 and intensity[i] <= TRAIL_LO:
                    target[i]     = 0.0
                    jolt_timer[i] = int(JOLT_MIN + randu() * JOLT_MAX)

            # Asymmetric smoothing: snap up fast, decay slowly through green
            delta = target[i] - intensity[i]
            if delta > 0:
                intensity[i] += delta * SMOOTH_RISE
            else:
                intensity[i] += delta * SMOOTH_FALL

            intensity[i] = max(0.0, min(1.0, intensity[i]))

            # Hard gamma — keep black truly black; compress the dim trail zone
            # so the head still reads as a genuine bright glyph snapping in
            v = intensity[i] ** 1.8

            np[i] = scale_color(rain_color(v), BRIGHTNESS)

        carry = new_carry
        np.write()

    time.sleep_ms(120)