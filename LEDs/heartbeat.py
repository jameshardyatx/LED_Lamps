import neopixel
import machine
import time
import math

LED_PIN    = 0
BUTTON_PIN = 27
NUM_LEDS   = 15

np     = neopixel.NeoPixel(machine.Pin(LED_PIN), NUM_LEDS)
button = machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

# Palette — heartbeat pulse
# Two stops: the pulse breathes between a dark resting shade and a
# brighter red-pink peak tint.
COLOR_HIGH  = (94,  2,   2  )  # dark red — resting/diastole floor
COLOR_LOW = (226, 4, 4)  # brighter red-pink — systolic peak

BPM         = 50
PERIOD_MS   = 60000.0 / BPM   # one full heartbeat cycle, in ms

# Lub-dub shape, as a fraction of one beat cycle (0.0-1.0)
LUB_CENTER  = 0.12   # systolic peak position within the beat
#LUB_WIDTH   = 0.045  # lub bump length — smaller = sharper/shorter
LUB_WIDTH = 0.09
LUB_HEIGHT  = 1.0    # lub bump peak intensity

DUB_CENTER  = 0.32   # dicrotic notch bump position within the beat
DUB_WIDTH   = 0.12   # dub bump length — smaller = sharper/shorter
DUB_HEIGHT  = 0.35   # dub bump peak intensity

# Double-beat spacing — how far into the cycle (as a fraction of one
# period) the second lub-dub starts, after the first. Two full beats
# fire each cycle before it rests back down at COLOR_HIGH.
SECOND_BEAT_OFFSET = 0.42

BRIGHTNESS  = 1.0

def lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )

def heartbeat_color(value):
    # value: 0.0 (resting floor) -> 1.0 (systolic peak)
    return lerp_color(COLOR_HIGH, COLOR_LOW, value)

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

# ----------------------------------------------------------------
# Heartbeat waveform
# A real pulse trace has two bumps per beat: the strong systolic
# peak (the "lub") followed by a smaller dicrotic bump (the "dub"),
# then a rest period before the next beat. Built from two Gaussian
# bumps layered on a single beat cycle t in [0, 1).
# ----------------------------------------------------------------

def gaussian(t, center, width, height):
    d = (t - center) / width
    return height * math.exp(-(d * d) / 2.0)

def single_beat(t):
    lub = gaussian(t, center=LUB_CENTER, width=LUB_WIDTH, height=LUB_HEIGHT)
    dub = gaussian(t, center=DUB_CENTER, width=DUB_WIDTH, height=DUB_HEIGHT)
    return lub + dub

def heartbeat_wave(t):
    # First beat starts at the top of the cycle, second beat starts
    # SECOND_BEAT_OFFSET later — whichever is louder at time t wins,
    # so the two don't cancel each other out where their tails overlap.
    v1 = single_beat(t)
    v2 = single_beat(t - SECOND_BEAT_OFFSET)
    v = max(v1, v2)
    return max(0.0, min(1.0, v))

leds_on    = True
last_press = 0

start_ms = time.ticks_ms()

while True:
    now = time.ticks_ms()

    if button.value() == 0 and time.ticks_diff(now, last_press) > 200:
        leds_on = not leds_on
        last_press = now
        if not leds_on:
            all_off()

    if leds_on:
        elapsed = time.ticks_diff(now, start_ms)
        t = (elapsed % PERIOD_MS) / PERIOD_MS   # phase within current beat, 0..1

        v = heartbeat_wave(t)
        color = scale_color(heartbeat_color(v), BRIGHTNESS)

        for i in range(NUM_LEDS):
            np[i] = color

        np.write()

    time.sleep_ms(20)