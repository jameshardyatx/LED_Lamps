import neopixel
import machine
import time

LED_PIN    = 0
BUTTON_PIN = 27
NUM_LEDS   = 15

np     = neopixel.NeoPixel(machine.Pin(LED_PIN), NUM_LEDS)
button = machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

# Palette — ember red through flame orange, topping out at the pale
# yellow-white a log hits when it pops and flares
PALETTE = [
    (0,   0,   0  ),  # dead black
    (15,  2,   0  ),  # faint ember
    (80,  10,  0  ),  # dark red
    (150, 35,  0  ),  # deep orange
    (210, 80,  5  ),  # orange
    (255, 130, 20 ),  # bright orange flame
    (255, 180, 60 ),  # yellow-orange
    (255, 225, 140),  # pale yellow-white — pop/flare peak
]

BRIGHTNESS = 1.0

def lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )

def flame_color(value):
    value  = max(0.0, min(1.0, value))
    scaled = value * (len(PALETTE) - 1)
    idx    = int(scaled)
    frac   = scaled - idx
    if idx >= len(PALETTE) - 1:
        return PALETTE[-1]
    return lerp_color(PALETTE[idx], PALETTE[idx + 1], frac)

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
# Campfire state per LED
# Each LED independently models a little tongue of flame that:
#   - flickers continuously in the ember/orange/flame range
#   - very rarely pops — a log-crackle flare that jumps to the pale
#     white-yellow peak, holds a moment, then eases back down
#   - a pop bleeds a little heat to its immediate neighbours, like
#     a real flare licking sideways
# ----------------------------------------------------------------

intensity  = [0.4 + randu() * 0.2 for _ in range(NUM_LEDS)]
target     = [0.4 + randu() * 0.2 for _ in range(NUM_LEDS)]
jolt_timer = [int(randu() * 5) for _ in range(NUM_LEDS)]
carry      = [0.0] * NUM_LEDS

# Tuning
SMOOTH_RISE = 0.55   # flame licks upward fairly quickly
SMOOTH_FALL = 0.18   # but settles back down more slowly

JOLT_MIN = 1
JOLT_MAX = 6

BASELINE_LO = 0.32   # normal flicker floor (dark red / deep orange)
BASELINE_HI = 0.68   # normal flicker ceiling (orange / bright orange)

POP_PROBABILITY = 0.00018  # chance per LED per tick of a pop/flare — this is deliberately tiny; pops should be rare
POP_INTENSITY   = 1.0      # scales how bright/long a pop reads, 0.5 (mild tick) .. 2.0 (violent crackle)
POP_HOLD_MIN    = 2        # ticks the flare peak holds before it's allowed to fall
POP_HOLD_MAX    = 6
POP_PROPAGATE   = 0.35     # how much heat a pop bleeds to each immediate neighbour

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
                # Neighbouring pop bled some heat over here — a small
                # secondary flare, not a full pop of its own
                target[i]     = min(1.0, 0.55 + carry[i] * 0.35)
                jolt_timer[i] = int(POP_HOLD_MIN / 2) + 1

            elif r < POP_PROBABILITY * POP_INTENSITY:
                # A genuine pop — snap to the pale flare peak
                flare         = 0.88 + randu() * 0.12 * min(1.3, POP_INTENSITY)
                target[i]     = min(1.0, flare)
                jolt_timer[i] = int(POP_HOLD_MIN + randu() * (POP_HOLD_MAX - POP_HOLD_MIN))
                if i > 0:
                    new_carry[i - 1] = max(new_carry[i - 1], flare * POP_PROPAGATE)
                if i < NUM_LEDS - 1:
                    new_carry[i + 1] = max(new_carry[i + 1], flare * POP_PROPAGATE)

            else:
                # Normal flicker — random walk in the ember/orange zone
                jolt_timer[i] -= 1
                if jolt_timer[i] <= 0:
                    target[i]     = BASELINE_LO + randu() * (BASELINE_HI - BASELINE_LO)
                    jolt_timer[i] = int(JOLT_MIN + randu() * JOLT_MAX)

            # Asymmetric smoothing: lick up fast, settle back down slower
            delta = target[i] - intensity[i]
            if delta > 0:
                intensity[i] += delta * SMOOTH_RISE
            else:
                intensity[i] += delta * SMOOTH_FALL

            intensity[i] = max(0.0, min(1.0, intensity[i]))

            np[i] = scale_color(flame_color(intensity[i]), BRIGHTNESS)

        carry = new_carry
        np.write()

    time.sleep_ms(80)