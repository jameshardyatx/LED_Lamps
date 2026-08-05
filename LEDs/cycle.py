import neopixel
import machine
import time

LED_PIN                  = 0
ON_OFF_BUTTON_PIN        = 27
CYCLE_BUTTON_PIN         = 28
BRIGHTNESS_DEC_BUTTON_PIN = 29
BRIGHTNESS_INC_BUTTON_PIN = 6
NUM_LEDS                 = 10

np = neopixel.NeoPixel(machine.Pin(LED_PIN), NUM_LEDS)
on_off_button        = machine.Pin(ON_OFF_BUTTON_PIN,        machine.Pin.IN, machine.Pin.PULL_UP)
cycle_button         = machine.Pin(CYCLE_BUTTON_PIN,         machine.Pin.IN, machine.Pin.PULL_UP)
brightness_dec_button = machine.Pin(BRIGHTNESS_DEC_BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
brightness_inc_button = machine.Pin(BRIGHTNESS_INC_BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)


### original palette
# PALETTE = [
#     (0xff, 0x09,   0x05),   # red
#     (0xff, 0x50, 0x00),     # orange
#     (0xff, 0x99,   0x20),   # yellow
#     (0x00, 0xbf, 0x1b),     # green
#     (0x00, 0xb2, 0xc1),     # cyan
#     (0x05, 14,   0xfe),     # blue
#     (96,   81,   0xff),     # indigo
#     (0xFD, 0x1E, 0xE0),     # violet
# ]

### light rainbow
# PALETTE = [
#     (0xFB, 0xF8, 0xCC),  # #fbf8cc
#     (0xFD, 0xE4, 0xCF),  # #fde4cf
#     (0xFF, 0xCF, 0xD2),  # #ffcfd2
#     (0xF1, 0xC0, 0xE8),  # #f1c0e8
#     (0xCF, 0xBA, 0xF0),  # #cfbaf0
#     (0xA3, 0xC4, 0xF3),  # #a3c4f3
#     (0x90, 0xDB, 0xF4),  # #90dbf4
#     (0x8E, 0xEC, 0xF5),  # #8eecf5
#     (0x98, 0xF5, 0xE1),  # #98f5e1
#     (0xB9, 0xFB, 0xC0),  # #b9fbc0
# ]

### 10 color rainbow
PALETTE = [
    (0xFF, 0x00, 0x00),  # #ff0000
    (0xFF, 0x87, 0x00),  # #ff8700
    (0xFF, 0xD3, 0x00),  # #ffd300
    (0xDE, 0xFF, 0x0A),  # #deff0a
    (0xA1, 0xFF, 0x0A),  # #a1ff0a
    (0x0A, 0xFF, 0x99),  # #0aff99
    (0x0A, 0xEF, 0xFF),  # #0aefff
    (0x14, 0x7D, 0xF5),  # #147df5
    (0x58, 0x0A, 0xFF),  # #580aff
    (0xBE, 0x0A, 0xFF),  # #be0aff
]

brightness          = 0.5
leds_on             = True
last_press          = 0
current_color_index = 0
DEBOUNCE_MS         = 200

GAMMA = 2.2  # typical for WS2812B; tweak between 2.2–2.8 to taste

GAMMA_LUT = bytes(
    int((i / 255) ** GAMMA * 255 + 0.5) for i in range(256)
)


def apply_brightness(color):
    return tuple(GAMMA_LUT[int(c * brightness)] for c in color)

def all_off():
    for i in range(NUM_LEDS):
        np[i] = (0, 0, 0)
    np.write()

def next_color():
    global current_color_index
    current_color_index = (current_color_index + 1) % len(PALETTE)

def inc_brightness():
    global brightness
    brightness = min(1.0, brightness + 0.1)

def dec_brightness():
    global brightness
    brightness = max(0.0, brightness - 0.1)

# def update_leds():
#     if leds_on:
#         for i in range(NUM_LEDS):
#             np[i] = apply_brightness(PALETTE[current_color_index])
#         np.write()
#     else:
#         all_off()

def update_leds(): # this version has half one color, half the next
    if leds_on:
        color1 = apply_brightness(PALETTE[current_color_index])
        color2 = apply_brightness(
            PALETTE[(current_color_index + 1) % len(PALETTE)]
        )

        for i in range(5):
            np[i] = color1

        for i in range(5, 10):
            np[i] = color2

        np.write()
    else:
        all_off()

# Initial draw
update_leds()

while True:
    now = time.ticks_ms()

    any_pressed = (
        not on_off_button.value() or
        not cycle_button.value() or
        not brightness_dec_button.value() or
        not brightness_inc_button.value()
    )

    if any_pressed and time.ticks_diff(now, last_press) > DEBOUNCE_MS:
        last_press = now

        if not on_off_button.value():
            leds_on = not leds_on

        elif not cycle_button.value():
            next_color()

        elif not brightness_dec_button.value():
            dec_brightness()

        elif not brightness_inc_button.value():
            inc_brightness()

        update_leds()

    time.sleep_ms(10)