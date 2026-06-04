import neopixel
import machine
import time

LED_PIN    = 0
BUTTON_PIN = 27
NUM_LEDS   = 10

np     = neopixel.NeoPixel(machine.Pin(LED_PIN), NUM_LEDS)
button = machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

def rainbow():

    def hsv_to_rgb(h, s, v):
            h = h % 360
            c = v * s
            x = c * (1 - abs((h / 60) % 2 - 1))
            m = v - c
            if   h < 60:  r, g, b = c, x, 0
            elif h < 120: r, g, b = x, c, 0
            elif h < 180: r, g, b = 0, c, x
            elif h < 240: r, g, b = 0, x, c
            elif h < 300: r, g, b = x, 0, c
            else:         r, g, b = c, 0, x
            return (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))
    
    BRIGHTNESS = 0.1
    SPEED      = 10
    SPREAD     = 50

    hue     = 0
    leds_on = True
    last_press = 0

    def all_off():
        for i in range(NUM_LEDS):
            np[i] = (0, 0, 0)
        np.write()

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
                np[i] = hsv_to_rgb((hue + i * SPREAD) % 360, 1.0, BRIGHTNESS)
            np.write()
            hue = (hue + SPEED) % 360

        time.sleep_ms(200)