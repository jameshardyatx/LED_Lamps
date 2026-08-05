import neopixel
import machine
import time
import math

LED_PIN    = 0
BUTTON_PIN = 27
NUM_LEDS   = 15

np     = neopixel.NeoPixel(machine.Pin(LED_PIN), NUM_LEDS)
button = machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

BRIGHTNESS = 0.9  # fire wants to be bright

# Fire colour ramp: black → deep red → orange → yellow → pale yellow-white
FIRE_COLORS = [
    (0,   0,   0  ),  # out / ember black
    (80,  0,   0  ),  # deep red coal
    (180, 20,  0  ),  # red
    (255, 80,  0  ),  # orange
    (255, 180, 10 ),  # yellow-orange
    (255, 240, 80 ),  # bright yellow
    (255, 255, 180),  # hot white-yellow tip
]

def lerp_color(a, b, t):
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )

def fire_color(value):
    value  = max(0.0, min(1.0, value))
    scaled = value * (len(FIRE_COLORS) - 1)
    idx    = int(scaled)
    frac   = scaled - idx
    if idx >= len(FIRE_COLORS) - 1:
        return FIRE_COLORS[-1]
    return lerp_color(FIRE_COLORS[idx], FIRE_COLORS[idx + 1], frac)

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

# --- Minimal pseudo-random number generator (xorshift32) ---
# MicroPython has no random module on all builds; this is self-contained.
_rng_state = 2463534242

def randu():
    """Return a pseudo-random float 0.0–1.0."""
    global _rng_state
    x = _rng_state
    x ^= (x << 13) & 0xFFFFFFFF
    x ^= (x >> 17) & 0xFFFFFFFF
    x ^= (x << 5)  & 0xFFFFFFFF
    _rng_state = x & 0xFFFFFFFF
    return (_rng_state & 0xFFFF) / 65535.0

# Per-LED state: each LED tracks a smoothed intensity that gets jolted randomly
intensity   = [randu() for _ in range(NUM_LEDS)]   # current smoothed value
target      = [randu() for _ in range(NUM_LEDS)]   # value we're lerping toward
jolt_timer  = [0]      * NUM_LEDS                  # ticks until next target change

leds_on    = True
last_press = 0
tick       = 0

# Tuning knobs
SMOOTH      = 0.05   # how fast intensity tracks its target (0=frozen, 1=instant, .25=default)
JOLT_MIN    = 1      # minimum ticks before a new random target is chosen
JOLT_MAX    = 6      # maximum ticks (low = rapid flicker)
FLARE_PROB  = 0.08   # probability per tick of a sudden full-brightness flare
EMBER_PROB  = 0.05   # probability per tick of dropping to near-black ember

while True:
    now = time.ticks_ms()

    # Debounced button
    if button.value() == 0 and time.ticks_diff(now, last_press) > 200:
        leds_on = not leds_on
        last_press = now
        if not leds_on:
            all_off()

    if leds_on:
        for i in range(NUM_LEDS):

            # Occasionally throw a dramatic flare or sudden ember drop
            r = randu()
            if r < FLARE_PROB:
                target[i]     = 0.85 + randu() * 0.15   # white-hot flare
                jolt_timer[i] = 1
            elif r < FLARE_PROB + EMBER_PROB:
                target[i]     = randu() * 0.12           # sudden dark ember
                jolt_timer[i] = int(JOLT_MIN + randu() * (JOLT_MAX - JOLT_MIN))
            else:
                # Normal: pick a new random target when the timer expires
                jolt_timer[i] -= 1
                if jolt_timer[i] <= 0:
                    # Bias targets toward mid-orange (0.4–0.8) for a healthy flame core
                    target[i]     = 0.3 + randu() * 0.6
                    jolt_timer[i] = int(JOLT_MIN + randu() * (JOLT_MAX - JOLT_MIN))

            # Smooth lerp toward target — asymmetric: faster rise, slower decay
            delta = target[i] - intensity[i]
            if delta > 0:
                intensity[i] += delta * SMOOTH * 1.6   # snappy flare-up
            else:
                intensity[i] += delta * SMOOTH * 0.7   # slow ember fade

            intensity[i] = max(0.0, min(1.0, intensity[i]))

            # Squash low values to keep black truly black (no muddy dark-red glow)
            v = intensity[i] ** 1.4

            np[i] = scale_color(fire_color(v), BRIGHTNESS)

        np.write()
        tick += 1

    time.sleep_ms(35)