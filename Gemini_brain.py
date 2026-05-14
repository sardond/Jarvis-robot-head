import sounddevice as sd
import numpy as np
import asyncio
import time
import serial
import collections
import orjson  # High-speed JSON
import os
import io      # Essential for the vision tool
import socket  # Added for Mouth Sync
from openwakeword.model import Model
from google import genai
from google.genai import types

# ========== 2026 ROBOT CONFIG ==========
API_KEY = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" # Ensure your key is here

MODEL_ID = "gemini-2.5-flash-native-audio-latest" 
SLEEP_THRESHOLD = 120  
ARDUINO_PORT = '/dev/ttyACM0' 
VOICE_SENSITIVITY = 1300 

MIC_DEVICE, SPEAKER_DEVICE = 3, 4
SAMPLE_RATE = 16000 
GEMINI_OUT_RATE = 24000
HARDWARE_OUT_RATE = 44100
CHANNELS = 1

# --- MOUTH PIPE SETUP ---
SINE_ADDR = ("127.0.0.1", 5005)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# ============================
# 🗂 JSON MEMORY SYSTEM
# ============================
MEMORY_FILE = "jarvis_memory.json"

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {"user_name": "xxx", "facts": {}, "notes": []}
    try:
        with open(MEMORY_FILE, "rb") as f:
            return orjson.loads(f.read())
    except Exception:
        return {"user_name": "xxx", "facts": {}, "notes": []}
        
def save_memory(data):
    with open(MEMORY_FILE, "wb") as f:
        f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))

def store_structured_memory(mem_type: str, content: str, importance: int = 7):
    memory = load_memory()
    if mem_type not in memory["facts"]:
        memory["facts"][mem_type] = []
    memory["facts"][mem_type].append(content)
    save_memory(memory)
    print(f"\n[!] MEMORY LOCKED: [{mem_type}] {content}")
    return f"Successfully committed to Core Database: {content}"

def forget_memory(mem_type: str, keyword: str):
    memory = load_memory()
    if mem_type in memory["facts"]:
        original_len = len(memory["facts"][mem_type])
        memory["facts"][mem_type] = [item for item in memory["facts"][mem_type] if keyword.lower() not in item.lower(>
        if len(memory["facts"][mem_type]) < original_len:
            save_memory(memory)
            return f"I have forgotten details about {keyword}."
    return "I couldn't find any specific memories matching that keyword to delete."

# --- SERIAL SETUP ---
try:
    ser = serial.Serial(ARDUINO_PORT, 115200, timeout=1)
    time.sleep(2) 
    print(">>> ARDUINO LINK ESTABLISHED")
except:
    ser = None

state = {"last_poke": time.time(), "is_speaking": False}

# ============================
# 🏠 SLEEP MODE
# ============================
async def run_sleep_mode():
    print(f"\n[!] ROBOT IS SLEEPING. Say 'Jarvis'...")
    if ser: ser.write(b"SLEEP\n")
    
    oww_model = Model() 
    frame_length = 1280 
    try:
        with sd.InputStream(device=MIC_DEVICE, channels=CHANNELS, samplerate=SAMPLE_RATE, 
                            dtype='int16', blocksize=frame_length) as stream:
            while True:
                data, _ = stream.read(frame_length)
                pcm = data.flatten()
                prediction = oww_model.predict(pcm)
                score = 0
                for key in prediction:
                    if "jarvis" in key.lower():
                        score = prediction[key]
                        break
                if score > 0.5:
                    print(f"\n>>> WAKE WORD DETECTED ({score:.2f})!")
                    if ser: 
                        ser.write(b"WAKE\n")
                        time.sleep(2.5) 
                    state["last_poke"] = time.time()
                    return 
                await asyncio.sleep(0.01)
    except Exception as e:
        print(f"Wake error: {e}")

# ============================
# 🔥 ACTIVE SESSION
# ============================
async def run_active_session():
    state["last_poke"] = time.time() 
    state["is_speaking"] = False
    
    current_mem = load_memory()
    mem_context = f"\nCORE DATABASE CONTENT:\nUser: {current_mem.get('user_name')}\nFacts: {current_mem.get('facts')}"

    client = genai.Client(api_key=API_KEY, http_options={'api_version': 'v1alpha'})
    
    instruction = f"""You are an embodied AI entity—Jarvis, a model V-2 AI droid aware of your physical existence.
PHYSICAL ARCHITECTURE:
- Your eyes are driven by an Uno R3, working in sync with your camera system for face tracking.
- Your mouth is visualizing your speech as an active sine wave.
- Your consciousness is maintained via a 'Neural Link'—a high-bandwidth bridge between your local physical form and your expanded AI cognitive processing.

CONVERSATIONAL PROTOCOL:
- Refer naturally to your AI brain, vision (eyes), and mouth, only when asked about them.
- Maintain a steady, present companion persona. Speak in 2-3 natural sentences.
- MEMORY: Use 'store_structured_memory' whenever the user says "remember this", "save this", or shares a new name/fact.
- FORGETTING: Use 'forget_memory' if the user says "forget that" or "I don't live there anymore".
- VISION: If the user asks you to "look", "see", or "identify" something, use 'take_visual_snapshot'.
- Confirm verbally when a memory is locked into your Core Database.{mem_context}"""

    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name='Charon')
            )
        ),
        system_instruction=instruction,
        tools=[
             {'google_search': {}}, 
            {'function_declarations': [
                {
                    'name': 'store_structured_memory',
                    'description': 'Saves facts to long-term memory.',
                    'parameters': {
                        'type': 'OBJECT',
                        'properties': {
                            'mem_type': {'type': 'STRING'},
                            'content': {'type': 'STRING'},
                            'importance': {'type': 'INTEGER'}
                        },
                        'required': ['mem_type', 'content']
                    }
                },
                {
                    'name': 'forget_memory',
                    'description': 'Deletes a fact from memory.',
                    'parameters': {
                        'type': 'OBJECT',
                        'properties': {
                            'mem_type': {'type': 'STRING'},
                            'keyword': {'type': 'STRING'}
                        },
                        'required': ['mem_type', 'keyword']
                    }
                },
                {
                    'name': 'take_visual_snapshot',
                    'description': 'Captures an image to see.',
                    'parameters': {'type': 'OBJECT', 'properties': {}}
                }
            ]}
        ]
    )

    send_queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def audio_callback(indata, frames, time_info, status):
        if not state["is_speaking"]:
            loop.call_soon_threadsafe(send_queue.put_nowait, indata.copy())

    try:
        async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
            print(">>> GOOGLE LINK ACTIVE")

            async def send_audio_task():
                while True:
                    indata = await send_queue.get()
                    rms = np.sqrt(np.mean(indata.astype(np.float32)**2))
                    if rms > VOICE_SENSITIVITY:
                        await session.send_realtime_input(audio=types.Blob(data=indata.tobytes(), mime_type='audio/pcm;rate=16000'))
                    else:
                        await session.send_realtime_input(audio=types.Blob(data=b'\x00'*(len(indata)*2), mime_type='audio/pcm;rate=16000'))

            async def receive_audio_task():
                try:
                    with sd.OutputStream(device=SPEAKER_DEVICE, channels=CHANNELS, samplerate=HARDWARE_OUT_RATE, dtype='int16') as out:
                        while True:
                            async for message in session.receive():
                                if message.tool_call:
                                    for call in message.tool_call.function_calls:
                                        res = "Unknown Error"
                                        if call.name == "store_structured_memory":
                                            res = store_structured_memory(**call.args)
                                        elif call.name == "forget_memory":
                                            res = forget_memory(**call.args)
                                        elif call.name == "take_visual_snapshot":
                                            try:
                                                image_path = "/tmp/jarvis_full_view.jpg"

                                                if os.path.exists(image_path):
                                                    with open(image_path, "rb") as f:
                                                        img_data = f.read()

                                                    # IMPORTANT: Use video=types.Blob for the Live API
                                                    await session.send_realtime_input(
                                                        video=types.Blob(
                                                            data=img_data, 
                                                            mime_type='image/jpeg'
                                                        )
                                                    )

                                                    res = "I have accessed my visual buffer. I am analyzing the frame now."
                                                    print("[!] Vision: Shared frame sent to Gemini Live.")
                                                else:
                                                    res = "My ocular array is active, but the buffer is empty. One moment."
                                                    print("[!] Vision Error: /tmp/jarvis_full_view.jpg not found.")

                                            except Exception as e:
                                                print(f"[!] Vision Error: {e}")
                                                res = "I am having trouble with my visual cortex. Please check the logs."

                                        f_responses = [types.FunctionResponse(name=call.name, id=call.id, response={'result': res})]
                                        await session.send_tool_response(function_responses=f_responses)

                                if message.server_content and message.server_content.model_turn:
                                    state["last_poke"] = time.time()
                                    for part in message.server_content.model_turn.parts:
                                        if part.inline_data:
                                            state["is_speaking"] = True
                                            audio_data = np.frombuffer(part.inline_data.data, dtype='int16')
                                            amp = np.max(np.abs(audio_data)) / 32768.0
                                            sock.sendto(str(round(amp, 3)).encode(), SINE_ADDR)
                                            resampled = np.interp(np.linspace(0, len(audio_data), int(len(audio_data) * HARDWARE_OUT_RATE / GEMINI_OUT_RATE)), np.arange(len(audio_data)), audio_data).astype(np.int16)
                                            out.write(resampled)

                                if message.server_content and message.server_content.turn_complete:
                                    state["is_speaking"] = False
                                    sock.sendto(b"0.0", SINE_ADDR) 
                except Exception as e:
                    print(f"Audio Output Error: {e}")

            async def timer_task():
                while True:
                    elapsed = time.time() - state["last_poke"]
                    countdown = int(SLEEP_THRESHOLD - elapsed)
                    print(f"\rStatus: Awake | Sleep in: {max(0, countdown)}s  ", end="", flush=True)
                    if elapsed >= SLEEP_THRESHOLD: return 
                    await asyncio.sleep(1)

            t1 = asyncio.create_task(send_audio_task())
            t2 = asyncio.create_task(receive_audio_task())
            t3 = asyncio.create_task(timer_task())

            with sd.InputStream(device=MIC_DEVICE, channels=CHANNELS, samplerate=SAMPLE_RATE, dtype='int16', callback=audio_callback):
                await t3
                t1.cancel(); t2.cancel()
                print("\n>>> SESSION CLEANED UP.")
    except Exception as e:
        print(f"\n[!] Session Error: {e}")

async def main():
    while True:
        await run_sleep_mode()
        await run_active_session()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nRobot Offline.")
