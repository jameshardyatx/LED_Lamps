import neopixel
import machine
import time
import math

LED_PIN    = 0
BUTTON_PIN = 27
NUM_LEDS   = 15

np     = neopixel.NeoPixel(machine.Pin(LED_PIN), NUM_LEDS)
button = machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

# Palette — electric arc colours
# #fffcb8  core white-yellow (the hottest channel centre)
# Rotating through orange plasma as energy disperses outward
PALETTE = [
    (0,    0,    0  ),  # dead black — arc extinguished
    (20,   5,    0  ),  # dim ember pre-ignition
    (180,  40,   0  ),  # deep orange plasma
    (255,  120,  0  ),  # bright orange arc edge
    (255,  210,  20 ),  # yellow-orange
    (255,  252,  100),  # near-white yellow
    (255,  252,  184),  # #fffcb8 — core white
    (255,  255,  230),  # blinding white overload
]

BRIGHTNESS = 1.0   # electricity is violent and bright

def lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )

def arc_color(value):
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
# Arc state per LED
# Each LED independently models a tiny arc segment that:
#   - sits at a smouldering orange baseline most of the time
#   - gets struck by sudden white-hot discharge spikes
#   - propagates spikes to neighbours (corona / branching effect)
#   - decays back through orange then cuts to black between strikes
# ----------------------------------------------------------------

# Smoothed intensity value currently displayed
intensity   = [randu() * 0.35 for _ in range(NUM_LEDS)]

# Target the smoother is chasing
target      = [0.3 + randu() * 0.2  for _ in range(NUM_LEDS)]

# Countdown ticks until a new random target is picked
jolt_timer  = [int(randu() * 8) for _ in range(NUM_LEDS)]

# Propagation carry: a spike on LED i can trigger LED i±1
carry       = [0.0] * NUM_LEDS

# Tuning
SMOOTH_RISE  = 0.9   # fast snap upward — arcs ignite instantly
SMOOTH_FALL  = 1.12   # slow orange decay — embers linger
JOLT_MIN     = 1
JOLT_MAX     = 8
STRIKE_PROB  = 0.01   # probability of a full white-hot discharge strike
DARK_PROB    = 0.08   # probability of sudden extinction (arc breaks)
PROPAGATE    = 0.25   # how much of a spike bleeds to neighbours
BASELINE_LO  = 0.28   # normal smoulder floor (orange zone)
BASELINE_HI  = 0.52   # normal smoulder ceiling

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
                # Incoming propagated spike — re-discharge this segment
                target[i]    = 0.75 + carry[i] * 0.25
                jolt_timer[i] = 1
                # Pass a weakened pulse onward to neighbours
                if i > 0:
                    new_carry[i - 1] = max(new_carry[i - 1], carry[i] * PROPAGATE)
                if i < NUM_LEDS - 1:
                    new_carry[i + 1] = max(new_carry[i + 1], carry[i] * PROPAGATE)

            elif r < STRIKE_PROB:
                # Spontaneous discharge — spike to white-hot core
                spike         = 0.82 + randu() * 0.18
                target[i]     = spike
                jolt_timer[i] = 1
                # Seed propagation in both directions
                if i > 0:
                    new_carry[i - 1] = max(new_carry[i - 1], spike * PROPAGATE)
                if i < NUM_LEDS - 1:
                    new_carry[i + 1] = max(new_carry[i + 1], spike * PROPAGATE)

            elif r < STRIKE_PROB + DARK_PROB:
                # Arc break — collapse to near black
                target[i]     = randu() * 0.08
                jolt_timer[i] = int(JOLT_MIN + randu() * 4)

            else:
                # Normal smoulder — random walk in the orange zone
                jolt_timer[i] -= 1
                if jolt_timer[i] <= 0:
                    target[i]     = BASELINE_LO + randu() * (BASELINE_HI - BASELINE_LO)
                    jolt_timer[i] = int(JOLT_MIN + randu() * JOLT_MAX)

            # Asymmetric smoothing: snap up fast, decay slowly through orange
            delta = target[i] - intensity[i]
            if delta > 0:
                intensity[i] += delta * SMOOTH_RISE
            else:
                intensity[i] += delta * SMOOTH_FALL

            intensity[i] = max(0.0, min(1.0, intensity[i]))

            # Hard gamma — keep black truly black; compress the dim orange zone
            # so the jump to white feels like a genuine voltage spike
            v = intensity[i] ** 1.8

            np[i] = scale_color(arc_color(v), BRIGHTNESS)

        carry = new_carry
        np.write()

    time.sleep_ms(120)