import os
import numpy as np
import sounddevice as sd
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from scipy.signal import butter, lfilter
import matplotlib
matplotlib.use('TkAgg')  # Ensure compatibility with Pi

# === Environment Setup ===
os.environ['SDL_VIDEO_WINDOW_POS'] = '0,0'
os.environ['QT_QPA_PLATFORM'] = 'xcb'

# === Settings ===
samplerate = 16000
blocksize = 1024
input_device = 4     # PulseAudio input: UGREEN mic
output_device = 8    # PulseAudio output: default sink (UGREEN headphone jack)
display_samples = 90
taper_size = 10

# === Butterworth Filter ===
def butter_lowpass(cutoff=1000, fs=16000, order=4):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    return butter(order, normal_cutoff, btype='low', analog=False)

b, a = butter_lowpass()

def smooth_signal(data):
    return lfilter(b, a, data)

# === Visualization Setup ===
fig = plt.figure(figsize=(8, 4.8), dpi=100)
manager = plt.get_current_fig_manager()

# 🖥️ Enable fullscreen again
try:
    manager.full_screen_toggle()
except AttributeError:
    pass

ax = fig.add_subplot(111)
fig.patch.set_facecolor('black')
ax.set_facecolor('black')
ax.set_ylim(-1.0, 1.0)
ax.set_xlim(0, display_samples)
ax.axis('off')

try:
    manager.canvas.manager.window.config(cursor='none')
except Exception:
    try:
        manager.window.config(cursor='none')
    except:
        pass

# Trail waveform setup
trail_length = 6
line_history = [
    ax.plot(np.zeros(display_samples), color='#00ffcc', linewidth=1.8, alpha=0.15 * (i + 1))[0]
    for i in range(trail_length)
]
main_line, = ax.plot(np.zeros(display_samples), color='#00ffcc', linewidth=2.5, alpha=1.0)
waveform = np.zeros(blocksize)

# === Audio Callback ===
def audio_callback(indata, outdata, frames, time, status):
    global waveform
    if status:
        print(status)
    mono = indata[:, 0]
    waveform = smooth_signal(mono)
    outdata[:] = np.tile(mono[:, np.newaxis], (1, outdata.shape[1]))  # Duplicate mono input to all output channels

# === Update Function for Animation ===
waveform_history = [np.zeros(display_samples) for _ in range(trail_length)]

def apply_edge_taper(data, size):
    window = np.ones_like(data)
    fade = 0.5 * (1 - np.cos(np.linspace(0, np.pi, size)))
    window[:size] *= fade
    window[-size:] *= fade[::-1]
    return data * window

def update(frame):
    mid = blocksize // 2
    half_disp = display_samples // 2
    partial_wave = waveform[mid - half_disp : mid + half_disp].copy()
    partial_wave = apply_edge_taper(partial_wave, taper_size)
    waveform_history.pop(0)
    waveform_history.append(partial_wave)

    for i, line in enumerate(line_history):
        line.set_ydata(waveform_history[i])
    main_line.set_ydata(waveform_history[-1])
    return line_history + [main_line]

# === Ctrl+Q to Exit ===
def on_key(event):
    if event.key == 'ctrl+q':
        plt.close(fig)

fig.canvas.mpl_connect('key_press_event', on_key)

# === Start Audio Stream and Animation ===
stream = sd.Stream(
    samplerate=samplerate,
    blocksize=blocksize,
    device=(input_device, output_device),
    dtype='float32',
    channels=1,
    callback=audio_callback
)

with stream:
    ani = animation.FuncAnimation(fig, update, interval=32, blit=True, cache_frame_data=False)
    plt.show()
