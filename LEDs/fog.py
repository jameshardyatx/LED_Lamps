import neopixel
import machine
import time
import math

LED_PIN    = 0
BUTTON_PIN = 27
NUM_LEDS   = 10

np     = neopixel.NeoPixel(machine.Pin(LED_PIN), NUM_LEDS)
button = machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

# Palette — hex values converted to (R, G, B)
# #77D9DA  primary fog teal
# #234A59  deep shadow blue-grey
# #8BD9C3  pale mint lift
# #F2D8C9  warm peach wisp (rare, distant fog catch)
PALETTE = [
    (0x23, 0x4A, 0x59),  # deep shadow
    (0x77, 0xD9, 0xDA),  # primary teal fog  ← anchor, returned to often
    (0x8B, 0xD9, 0xC3),  # mint lift
    (0x77, 0xD9, 0xDA),  # primary again — doubles its weight in the ramp
    (0xF2, 0xD8, 0xC9),  # warm peach wisp
    (0x77, 0xD9, 0xDA),  # primary again — fog always comes back
    (0x23, 0x4A, 0x59),  # deep shadow
]

BRIGHTNESS = 0.9   # fog is never harsh; keep it dim and diffuse

def lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )

def palette_color(value):
    """Sample the palette ramp at value 0.0–1.0."""
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

# --- Layered sine fog engine ---
# Fog texture = three sine waves per LED summed together.
# Each wave has its own speed and spatial frequency so they
# never fully align — producing the drifting, non-repeating
# quality of real fog banks.
#
# Wave parameters: (time_speed, spatial_freq, amplitude)
# time_speed    — how fast the wave travels (t multiplier)
# spatial_freq  — how tightly it varies across the LED strip
# amplitude     — contribution weight (all three sum to 1.0)

WAVES = [
    (0.018, 0.55, 0.50),   # slow, broad primary drift
    (0.031, 1.30, 0.32),   # medium, tighter wisp detail
    (0.057, 2.70, 0.18),   # fast, fine micro-turbulence
]

# Per-LED spatial offsets — spread unevenly so the strip
# doesn't look like a uniform gradient at rest
import math
OFFSETS = [i * 0.71 + math.sin(i * 1.3) * 0.4 for i in range(NUM_LEDS)]

leds_on    = True
last_press = 0
t          = 0.0

while True:
    now = time.ticks_ms()

    if button.value() == 0 and time.ticks_diff(now, last_press) > 200:
        leds_on = not leds_on
        last_press = now
        if not leds_on:
            all_off()

    if leds_on:
        for i in range(NUM_LEDS):
            # Sum the three wave layers
            value = 0.0
            for (ts, sf, amp) in WAVES:
                value += math.sin(t * ts + OFFSETS[i] * sf) * amp

            # value is in roughly -1 … 1; normalise to 0 … 1
            value = (value + 1.0) / 2.0

            # Gentle S-curve: pulls mid-tones toward the primary fog colour
            # and softens the transitions at both ends — no hard edges in fog
            value = value * value * (3.0 - 2.0 * value)  # smoothstep

            np[i] = scale_color(palette_color(value), BRIGHTNESS)

        np.write()
        t += 1.0

    time.sleep_ms(50)