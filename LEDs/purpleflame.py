import neopixel
import machine
import time
import math

LED_PIN    = 0
BUTTON_PIN = 27
NUM_LEDS   = 10

np     = neopixel.NeoPixel(machine.Pin(LED_PIN), NUM_LEDS)
button = machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

# Palette — magical flame: deep violet base → pink-magenta body → hot pink crown
# #a75cb7  deep violet-purple  (base, smouldering core)
# #f0639c  warm rose-pink      (mid flame body)
# #ea6f7f  soft coral-pink     (secondary body warmth)
# #fd45e5  vivid magenta       (hottest crown, like arcane energy)
# Fades to near-white at the tip for that candle-flame glow
# #F00061  replace #f0639c
# #FD1EE0  replace #fd45e5
# #EA2F47  replace #ea6f7f
# #9F2CB7  replace #a75cb7

PALETTE = [
    (0,    0,    0  ),  # extinguished black
    (30,   5,    25 ),  # dim violet ember
    #(0xa7, 0x5c, 0xb7),  # #a75cb7 — deep violet base
    (0x9F, 0x2C, 0xB7),  # #9F2CB7 — new deep violet base,
    #(0xf0, 0x63, 0x9c),  # #f0639c — rose-pink body
    (0xF0, 0x00, 0x61), # new rose-pink with higher saturation
    #(0xea, 0x6f, 0x7f),  # #ea6f7f — coral warmth
    (0xEA, 0x2F, 0x47),  # new coral-pink with higher saturation
    #(0xfd, 0x45, 0xe5),  # #fd45e5 — vivid magenta crown
    (0xFD, 0x1E, 0xE0),  # new vivid magenta with higher saturation
    (255,  200,  240),   # pale pink-white hot tip
]

BRIGHTNESS = 0.7   # gentle — a magical candle, not a bonfire

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
        int(c[0] * brightness),
        int(c[1] * brightness),
        int(c[2] * brightness),
    )

def all_off():
    for i in range(NUM_LEDS):
        np[i] = (0, 0, 0)
    np.write()

# --- xorshift32 PRNG ---
_rng = 3141592653

def randu():
    global _rng
    x = _rng
    x ^= (x << 13) & 0xFFFFFFFF
    x ^= (x >> 17) & 0xFFFFFFFF
    x ^= (x << 5)  & 0xFFFFFFFF
    _rng = x & 0xFFFFFFFF
    return (_rng & 0xFFFF) / 65535.0

# ----------------------------------------------------------------
# Two-layer animation:
#
# LAYER 1 — slow drift (the steady flame body)
#   Three gentle sine waves give each LED a slowly undulating
#   base brightness in the violet-pink range.  This is the calm,
#   magical part — no noise, just graceful movement.
#
# LAYER 2 — soft noise (the living flicker)
#   Each LED has a smoothed random target that wanders lazily.
#   Unlike the fire/electricity scripts, targets stay in a
#   narrow band so nothing ever goes dark or blinding — just a
#   soft organic breathing over the sine base.
#
# The two layers are blended (70% sine body, 30% noise flicker)
# then mapped through the palette.
# ----------------------------------------------------------------

# Sine wave params: (time_speed, spatial_freq, amplitude)
WAVES = [
    (0.022, 0.50, 0.45),   # slow broad swell — the main flame body
    (0.038, 1.20, 0.32),   # medium wisp — inner tongue of flame
    (0.061, 2.50, 0.23),   # faster micro-flicker detail
]

# Uneven spatial offsets so adjacent LEDs don't pulse in sync
OFFSETS = [i * 0.618 + math.sin(i * 1.9) * 0.5 for i in range(NUM_LEDS)]

# Per-LED noise state
noise_val   = [0.45 + randu() * 0.15 for _ in range(NUM_LEDS)]
noise_tgt   = [0.40 + randu() * 0.20 for _ in range(NUM_LEDS)]
noise_timer = [int(randu() * 12)      for _ in range(NUM_LEDS)]

# Tuning
NOISE_SMOOTH  = 0.08    # very slow drift — magical flames are serene
NOISE_LO      = 0.35    # noise wanders between these bounds
NOISE_HI      = 0.65    # (never dark, never blinding)
NOISE_JOLT_MIN = 4      # ticks between new noise targets
NOISE_JOLT_MAX = 14
SINE_WEIGHT   = 0.68    # blend: 68% sine body
NOISE_WEIGHT  = 0.32    # blend: 32% noise flicker

# Bias the whole output upward so we sit in the pink-magenta zone by default
OUTPUT_FLOOR  = 0.38
OUTPUT_CEIL   = 0.88

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

            # --- Layer 1: sine body ---
            sine_val = 0.0
            for (ts, sf, amp) in WAVES:
                sine_val += math.sin(t * ts + OFFSETS[i] * sf) * amp
            sine_val = (sine_val + 1.0) / 2.0   # normalise -1…1 → 0…1

            # --- Layer 2: soft noise flicker ---
            noise_timer[i] -= 1
            if noise_timer[i] <= 0:
                noise_tgt[i]   = NOISE_LO + randu() * (NOISE_HI - NOISE_LO)
                noise_timer[i] = int(NOISE_JOLT_MIN + randu() * NOISE_JOLT_MAX)

            # Symmetric smooth drift — no asymmetry, flames are gentle here
            noise_val[i] += (noise_tgt[i] - noise_val[i]) * NOISE_SMOOTH
            noise_val[i]  = max(0.0, min(1.0, noise_val[i]))

            # --- Blend layers ---
            blended = sine_val * SINE_WEIGHT + noise_val[i] * NOISE_WEIGHT

            # Remap into the pink-magenta sweet spot
            value = OUTPUT_FLOOR + blended * (OUTPUT_CEIL - OUTPUT_FLOOR)

            # Soft S-curve — smooth transitions, no hard edges
            # Applied lightly so the magenta crown still peeks through on peaks
            value = value * value * (3.0 - 2.0 * value)
            value = max(0.0, min(1.0, value))

            np[i] = scale_color(flame_color(value), BRIGHTNESS)

        np.write()
        t += 1.0

    time.sleep_ms(45)