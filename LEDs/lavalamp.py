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
# The two colors that blend to make the lamp — a solid wax "blob"
# color suspended in a translucent "fluid" color.
# ------------------------------------------------------------------
BLOB_COLOR  = (150, 20, 190)   # rich purple wax
FLUID_COLOR = (140, 0,  14 )   # deep red fluid

# BLOB_COLOR = (80,   20,    10)
# FLUID_COLOR  = (225,  150,   10)

# BLOB_COLOR = (10,   200,    245)
# FLUID_COLOR  = (75,  255,   12)


BRIGHTNESS = 1.0

# How many wax blobs float around the strip at once
NUM_BLOBS = 4

# How long (ms) it takes the lamp to go from cold-start to full motion.
# Real lamps take ~45 min; tuned much shorter here so the warm-up is
# actually visible on a desk lamp. Bump this up for a lazier ramp.
WARMUP_DURATION_MS = 120000   # 2 minutes

# Motion tuning — speed and re-targeting frequency are both scaled by
# heat, so the lamp is genuinely sluggish at power-on and gradually
# gets more restless as it "warms up".
MAX_VEL          = 0.35   # LEDs per tick at full heat
VEL_SMOOTH       = 0.05   # how quickly velocity eases toward its target (accel/decel feel)
VEL_JOLT_MIN     = 40     # ticks between re-targeting velocity, before heat scaling
VEL_JOLT_MAX     = 120
COLD_SPEED_SCALE = 0.12   # fraction of MAX_VEL used right at power-on

# Blob size — each blob's radius breathes slowly so blobs swell and
# shrink like real wax, rather than staying a fixed size
BLOB_RADIUS_MIN    = 1.2
BLOB_RADIUS_MAX    = 2.8
RADIUS_BREATH_RATE = 0.015   # radians per tick, before heat scaling

# Metaball blend — how the summed blob field converts into a
# blob-color/fluid-color mix. Below FIELD_LOW is pure fluid, above
# FIELD_HIGH is pure blob color, and it's a smooth curve in between,
# which is what lets two nearby blobs merge into one soft-edged shape.
FIELD_LOW  = 0.5
FIELD_HIGH = 1.0

# Edge highlight — real wax blobs catch a bit of extra light right at
# their boundary (like a meniscus), so their left/right edges read
# brighter than their own core. RIM_CENTER sits at the same field
# value as the blob's visual boundary; the boost fades back out both
# toward the fluid and toward the blob's deep interior.
RIM_BOOST  = 0.4    # extra brightness at the rim, as a fraction (0.4 = 40% brighter)
RIM_CENTER = (FIELD_LOW + FIELD_HIGH) / 2.0
RIM_INNER_SPAN = (FIELD_HIGH - FIELD_LOW) * 0.6   # how quickly the boost rises coming from the fluid side
RIM_OUTER_SPAN = (FIELD_HIGH - FIELD_LOW) * 1.4   # how quickly it fades going into the blob's interior


def lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
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

def smoothstep(edge0, edge1, x):
    if edge1 <= edge0:
        return 0.0 if x < edge0 else 1.0
    t = (x - edge0) / (edge1 - edge0)
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)

def rim_factor(field):
    # A bump that's 0 out in the fluid, rises to 1 right at the blob's
    # boundary (RIM_CENTER), then falls back to 0 deep inside the blob
    # — so only the left/right edges of a blob get the highlight, not
    # its solid core.
    rise = smoothstep(RIM_CENTER - RIM_INNER_SPAN, RIM_CENTER, field)
    fall = smoothstep(RIM_CENTER, RIM_CENTER + RIM_OUTER_SPAN, field)
    return rise * (1.0 - fall)

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
# Blob state
#
# Each blob is a position + radius that both drift smoothly:
#   - velocity eases toward an occasionally re-rolled random target,
#     instead of snapping, so motion never looks jerky
#   - radius breathes on its own slow sine wave
#   - blobs softly bounce off the ends of the strip
#
# Color at each LED is rendered by summing every blob's metaball
# field at that position and smoothstep-blending between the fluid
# and blob colors — this is what makes blobs merge into each other
# smoothly instead of just being circles that overlap and clip.
# ----------------------------------------------------------------

pos              = [(i + 0.5) * (NUM_LEDS / NUM_BLOBS) for i in range(NUM_BLOBS)]
vel              = [0.0 for _ in range(NUM_BLOBS)]
vel_target       = [0.0 for _ in range(NUM_BLOBS)]
vel_jolt_timer   = [0 for _ in range(NUM_BLOBS)]
radius_phase     = [randu() * 6.28318 for _ in range(NUM_BLOBS)]
radius           = [BLOB_RADIUS_MIN for _ in range(NUM_BLOBS)]

start_ms   = time.ticks_ms()
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
        elapsed    = time.ticks_diff(now, start_ms)
        heat       = max(0.0, min(1.0, elapsed / WARMUP_DURATION_MS))
        heat_eased = heat * heat * (3.0 - 2.0 * heat)   # smoothstep ramp
        speed_scale = COLD_SPEED_SCALE + (1.0 - COLD_SPEED_SCALE) * heat_eased

        # --- update each blob's motion and size ---------------------
        for i in range(NUM_BLOBS):
            vel_jolt_timer[i] -= 1
            if vel_jolt_timer[i] <= 0:
                vel_target[i] = (randu() * 2.0 - 1.0) * MAX_VEL * speed_scale
                # re-target more often once warmed up, for more restless motion
                jolt_range   = VEL_JOLT_MIN + randu() * (VEL_JOLT_MAX - VEL_JOLT_MIN)
                retarget_div = 0.4 + 0.6 * heat_eased
                vel_jolt_timer[i] = int(jolt_range / retarget_div)

            # ease current velocity toward its target — smooth accel/decel
            vel[i] += (vel_target[i] - vel[i]) * VEL_SMOOTH
            pos[i] += vel[i]

            # soft bounce off both ends of the strip
            if pos[i] < 0.0:
                pos[i]        = -pos[i]
                vel[i]        = -vel[i]
                vel_target[i] = -vel_target[i]
            elif pos[i] > NUM_LEDS - 1:
                pos[i]        = 2.0 * (NUM_LEDS - 1) - pos[i]
                vel[i]        = -vel[i]
                vel_target[i] = -vel_target[i]

            # breathing radius — faster, wider swings once warmed up
            radius_phase[i] += RADIUS_BREATH_RATE * (0.3 + 0.7 * heat_eased)
            breath           = 0.5 + 0.5 * math.sin(radius_phase[i])
            radius[i]        = BLOB_RADIUS_MIN + (BLOB_RADIUS_MAX - BLOB_RADIUS_MIN) * breath

        # --- render: sum metaball fields, blend colors --------------
        for x in range(NUM_LEDS):
            field = 0.0
            for i in range(NUM_BLOBS):
                d  = x - pos[i]
                r2 = radius[i] * radius[i]
                field += r2 / (d * d + r2)

            blend = smoothstep(FIELD_LOW, FIELD_HIGH, field)
            color = lerp_color(FLUID_COLOR, BLOB_COLOR, blend)

            rim   = rim_factor(field)
            np[x] = scale_color(color, BRIGHTNESS * (1.0 + RIM_BOOST * rim))

        np.write()

    time.sleep_ms(30)