import numpy as np
from PIL import Image, ImageDraw
from luma.lcd.device import ili9341
from luma.core.interface.serial import spi
import time
import socket
import threading
import math

# ==============================
# 🌐 UDP LISTENER (Neural Link)
# ==============================
receiver_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
receiver_sock.bind(("127.0.0.1", 5005))
receiver_sock.setblocking(False)

current_amp = 0.0

def socket_listener():
    global current_amp
    while True:
        try:
            data, _ = receiver_sock.recvfrom(1024)
            current_amp = float(data.decode())
        except:
            current_amp *= 0.85 
            time.sleep(0.01)

threading.Thread(target=socket_listener, daemon=True).start()

# ==============================
# Display Setup (LOCKED)
# ==============================
WIDTH, HEIGHT = 320, 240
serial = spi(port=0, device=0, gpio_DC=24, gpio_RST=25)
device = ili9341(serial, width=WIDTH, height=HEIGHT, rotate=1)

img = Image.new("RGB", device.size)
draw = ImageDraw.Draw(img)

# ==============================
# Waveform Settings
# ==============================
DISPLAY_SAMPLES = WIDTH
TRAIL_LENGTH = 6
TAPER_SIZE = 40 # Increased slightly for smoother edge fade
phase = 0.0

def apply_edge_taper(data, size):
    window = np.ones_like(data)
    fade = 0.5 * (1 - np.cos(np.linspace(0, np.pi, size)))
    window[:size] *= fade
    window[-size:] *= fade[::-1]
    return data * window

waveform_history = [np.zeros(DISPLAY_SAMPLES) for _ in range(TRAIL_LENGTH)]

# ==============================
# Draw Wave (UDP Synced)
# ==============================
def draw_wave():
    global phase
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill="black")
    mid_y = HEIGHT // 2

    # Create the holographic sine pattern
    x_vals = np.linspace(0, 4 * np.pi, WIDTH)
    
    # We use current_amp from the UDP link to drive the height
    raw_wave = np.sin(x_vals + phase) * current_amp
    wave = apply_edge_taper(raw_wave, TAPER_SIZE)
    
    waveform_history.pop(0)
    waveform_history.append(wave)

    for i, w in enumerate(waveform_history):
        alpha = int(255 * ((i + 1) / TRAIL_LENGTH) * 0.8)
        color = (0, alpha, alpha) 

        # SCALE FIX: Changed 15.0 to 0.8 to prevent clipping top/bottom
        # This keeps the wave contained within the 240px height.
        points = [(x, mid_y - int(y * (HEIGHT / 2) * 1.0)) for x, y in enumerate(w)]

        if len(points) > 1:
            draw.line(points, fill=color, width=2 if i == TRAIL_LENGTH-1 else 1)

    device.display(img)
    phase += 0.4

# ==============================
# Main Loop
# ==============================
try:
    print(">>> Auditory Hologlyph Projector ACTIVE")
    print(">>> Listening for Brain Link (UDP 5005)...")
    
    while True:
        draw_wave()
        time.sleep(0.02)

except KeyboardInterrupt:
    print("\nProjector Offline.")
