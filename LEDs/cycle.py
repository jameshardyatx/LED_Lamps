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

PALETTE = [
    (0xff, 0x09,   0x05),   # red
    (0xff, 0x50, 0x00),     # orange
    (0xff, 0xff,   0x11), # yellow
    (0x00, 0xbf, 0x1b),     # green
    (0x00, 0xb2, 0xc1),     # cyan
    (0x5d, 94,   0xff),     # blue
    (96,   81,   0xff),     # indigo
    (0xFD, 0x1E, 0xE0),     # violet
]

brightness          = 0.5
leds_on             = True
last_press          = 0
current_color_index = 0
DEBOUNCE_MS         = 200

def apply_brightness(color):
    return tuple(int(c * brightness) for c in color)

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

def update_leds():
    if leds_on:
        for i in range(NUM_LEDS):
            np[i] = apply_brightness(PALETTE[current_color_index])
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