import neopixel
import machine
import time
import math

LED_PIN    = 0
BUTTON_PIN = 27
NUM_LEDS   = 15

np     = neopixel.NeoPixel(machine.Pin(LED_PIN), NUM_LEDS)
button = machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

# ------------------------------------------------------------------
# Colors
# ------------------------------------------------------------------
BLUE_COLOR   = (20,  70,  150)   # cool blue — one end of the ambient drift
PURPLE_COLOR = (110, 70,  190)   # light purple — the other end
SPLASH_COLOR = (200, 235, 255)   # bright icy white-blue a ripple crest flashes toward

BRIGHTNESS = 1.0

# ------------------------------------------------------------------
# How much rain is falling — the main knob you asked for. This scales
# how often a new drop lands; everything else about a ripple's shape
# is independent of it.
# ------------------------------------------------------------------
RAIN_INTENSITY = 1.0   # 0.2 (light drizzle) .. 3.0 (heavy downpour)

BASE_DROP_PROB     = 0.03   # per-tick chance of a new drop at RAIN_INTENSITY = 1.0
MAX_ACTIVE_RIPPLES = 6      # caps simultaneous ripples so a downpour doesn't overload the loop

# ------------------------------------------------------------------
# Ambient surface — the gentle, ever-present blue/purple drift the
# puddle sits at between drops
# ------------------------------------------------------------------
AMBIENT_RATE           = 0.015   # radians/tick the global color phase advances — slow and gentle
AMBIENT_SPATIAL_OFFSET = 0.35    # radians of phase offset per LED, so the drift looks like it travels along the strip

# ------------------------------------------------------------------
# Ripple physics — a drop creates an outward-travelling wavefront that
# oscillates (brighter/dimmer, cooler/warmer) and decays both with
# time and with distance travelled, same as a real ripple on water.
# ------------------------------------------------------------------
RIPPLE_SPEED         = 0.6    # LEDs/tick the wavefront expands outward
RIPPLE_K             = 2.5    # spatial frequency of the ringing behind the wavefront (radians/LED)
RIPPLE_DECAY_TIME    = 0.06   # amplitude loss per tick (energy dissipating over time)
RIPPLE_DECAY_SPACE   = 0.55   # amplitude loss per LED of distance behind the wavefront (rings die out quickly behind the leading edge)
RIPPLE_DIST_FALLOFF  = 0.12   # amplitude loss per LED of distance from the drop's origin
RAMP_WIDTH           = 0.35   # LEDs over which the wavefront "arrives" at a position — small keeps the initial spike sharp
RIPPLE_MAX_TICKS     = 60     # a ripple is retired after this many ticks regardless (fully decayed by then)

RIPPLE_BRIGHTNESS_GAIN = 1.3   # how much a ripple crest can boost brightness above ambient
RIPPLE_DIM_GAIN        = 0.4   # how much a ripple trough can dim below ambient
RIPPLE_COLOR_MIX       = 1.0   # how far a ripple crest pulls the color toward SPLASH_COLOR

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def lerp_color(a, b, t):
    t = clamp(t, 0.0, 1.0)
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )

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
# Active ripples: each is [origin, age_ticks]. origin is a float LED
# position (drops can land between LEDs), age_ticks counts up once
# per loop iteration from the moment the drop lands.
# ----------------------------------------------------------------
ripples = []

ambient_phase = 0.0
leds_on       = True
last_press    = 0

while True:
    now = time.ticks_ms()

    if button.value() == 0 and time.ticks_diff(now, last_press) > 200:
        leds_on = not leds_on
        last_press = now
        if not leds_on:
            all_off()

    if leds_on:
        # --- maybe spawn a new drop --------------------------------
        if len(ripples) < MAX_ACTIVE_RIPPLES and randu() < BASE_DROP_PROB * RAIN_INTENSITY:
            origin = randu() * (NUM_LEDS - 1)
            ripples.append([origin, 0])

        # --- age ripples, retire old ones ---------------------------
        next_ripples = []
        for rp in ripples:
            rp[1] += 1
            if rp[1] < RIPPLE_MAX_TICKS:
                next_ripples.append(rp)
        ripples = next_ripples

        ambient_phase += AMBIENT_RATE

        # --- render --------------------------------------------------
        for x in range(NUM_LEDS):
            # ambient blue/purple drift
            phase      = ambient_phase + x * AMBIENT_SPATIAL_OFFSET
            blend_t    = 0.5 + 0.5 * math.sin(phase)
            base_color = lerp_color(BLUE_COLOR, PURPLE_COLOR, blend_t)
            base_mod   = 0.85 + 0.15 * math.sin(phase * 0.6 + 2.0)

            # sum every active ripple's contribution at this LED
            ripple_sum = 0.0
            for rp in ripples:
                origin, age = rp
                d     = abs(x - origin)
                front = age * RIPPLE_SPEED
                lead  = front - d

                arrival = clamp((lead + RAMP_WIDTH) / RAMP_WIDTH, 0.0, 1.0)
                if arrival <= 0.0:
                    continue

                lag      = max(0.0, lead)
                envelope = (arrival
                            * math.exp(-RIPPLE_DECAY_TIME * age)
                            * math.exp(-RIPPLE_DECAY_SPACE * lag)
                            * math.exp(-RIPPLE_DIST_FALLOFF * d))
                osc = math.cos(RIPPLE_K * lag)
                ripple_sum += envelope * osc

            ripple_sum = clamp(ripple_sum, -1.2, 1.2)

            brightness_scale = (base_mod
                                 + max(0.0, ripple_sum) * RIPPLE_BRIGHTNESS_GAIN
                                 - max(0.0, -ripple_sum) * RIPPLE_DIM_GAIN)

            color_mix_t = clamp(ripple_sum * RIPPLE_COLOR_MIX, 0.0, 1.0)
            final_color = lerp_color(base_color, SPLASH_COLOR, color_mix_t)

            np[x] = scale_color(final_color, max(0.0, brightness_scale) * BRIGHTNESS)

        np.write()

    time.sleep_ms(60)