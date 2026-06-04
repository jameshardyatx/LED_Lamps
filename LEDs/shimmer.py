import neopixel
import machine
import time
import math

LED_PIN    = 0
BUTTON_PIN = 27
NUM_LEDS   = 10

np     = neopixel.NeoPixel(machine.Pin(LED_PIN), NUM_LEDS)
button = machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

BRIGHTNESS = 0.7
SPEED      = 3   # animation tick speed (ms increment per loop)
SHIMMER_RATE = 7  # how fast individual LED phases drift

# Caustic colour stops: deep ocean blue → cyan → bright white
# Each entry: (R, G, B) at full brightness
CAUSTIC_COLORS = [
    (0,   30,  120),  # deep ocean blue
    (0,   80,  200),  # mid blue
    (0,  200,  230),  # cyan
    (180, 240, 255),  # pale cyan-white
    (255, 255, 255),  # white hotspot
]

def lerp_color(a, b, t):
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )

def caustic_color(value):
    """Map value 0.0–1.0 through the caustic colour ramp."""
    value = max(0.0, min(1.0, value))
    scaled = value * (len(CAUSTIC_COLORS) - 1)
    idx    = int(scaled)
    frac   = scaled - idx
    if idx >= len(CAUSTIC_COLORS) - 1:
        return CAUSTIC_COLORS[-1]
    return lerp_color(CAUSTIC_COLORS[idx], CAUSTIC_COLORS[idx + 1], frac)

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

# Each LED gets its own phase offset so shimmer looks organic, not uniform
phase_offsets = [i * 0.63 + 0.1 for i in range(NUM_LEDS)]  # golden-ratio spread

t       = 0.0
leds_on = True
last_press = 0

while True:
    now = time.ticks_ms()

    # Debounced button check
    if button.value() == 0 and time.ticks_diff(now, last_press) > 200:
        leds_on = not leds_on
        last_press = now
        if not leds_on:
            all_off()

    if leds_on:
        for i in range(NUM_LEDS):
            # Two overlapping sine waves per LED → irregular caustic flicker
            wave1 = math.sin(t * 0.04 + phase_offsets[i] * 2.1)
            wave2 = math.sin(t * 0.07 + phase_offsets[i] * 3.7)
            combined = (wave1 + wave2) / 2.0          # range -1 … 1
            value    = (combined + 1.0) / 2.0          # normalise to 0 … 1

            # Bias toward the blue/cyan range; white only on bright peaks
            value = value ** 1.6

            color = caustic_color(value)
            np[i] = scale_color(color, BRIGHTNESS)

        np.write()
        t += SPEED

    time.sleep_ms(40)