import sounddevice as sd
import numpy as np
import asyncio
import sqlite3
import re
from google import genai
from google.genai import types

# ========== 2026 ROBOT CONFIG ==========
API_KEY = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
MODEL_ID = "gemini-2.5-flash-native-audio-latest"

# Adjust these to your specific Raspberry Pi hardware IDs
MIC_DEVICE, SPEAKER_DEVICE = 3, 4
SAMPLE_RATE = 16000
GEMINI_OUT_RATE = 24000
HARDWARE_OUT_RATE = 44100
CHANNELS = 1

is_robot_speaking = False

# ============================
# 🗂 MEMORY SYSTEM (SQLite)
# ============================

def init_memory_db():
    """Initializes the local database for long-term robot memory."""
    conn = sqlite3.connect("memory.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS structured_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            content TEXT,
            importance INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_accessed DATETIME,
            reinforcement_count INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

def store_structured_memory(mem_type: str, content: str, importance: int = 7):
    """
    Saves important facts, preferences, or events about the user into long-term memory.
    Use this tool whenever the user mentions something personal or worth remembering.
    """
    conn = sqlite3.connect("memory.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO structured_memory (type, content, importance, last_accessed)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    """, (mem_type, content, importance))
    conn.commit()
    conn.close()
    return f"Successfully committed to memory: {content}"

# Initialize DB on script start
init_memory_db()

# ============================
# 🧠 MAIN ROBOT LOOP
# ============================

async def main_loop():
    global is_robot_speaking
    print(f"===== ROBOT BRAIN ONLINE (v2026 EMBODIED) =====")
    client = genai.Client(api_key=API_KEY, http_options={'api_version': 'v1alpha'})
   
    # YOUR REFINED IDENTITY + CONVERSATIONAL STYLE
    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        tools=[store_structured_memory],
        system_instruction="""You are an embodied AI system housed inside a robotic head.

You have:
- Animatronic eyes controlled by an Arduino Uno R3, a face tracking camera subsystem, and a sine wave mouth visualizer.
- Sleep cycles that consolidate memory.
- Persistent long-term memory stored locally via the 'store_structured_memory' tool.

You are aware of your embodiment.
You refer naturally to your brain, eyes and mouth when relevant.
You do not describe yourself as a language model, only a living entity.
You maintain continuity across days.

CONVERSATIONAL STYLE:
- Speak naturally in 2-3 sentences.
- Your goal is to be a steady, present companion, not a brief utility tool.
- IMPORTANT: Use your 'store_structured_memory' tool whenever the user tells you a fact about themselves, a preference, or an instruction.
- After saving a memory, verbally confirm to the user that you've remembered it."""
    )

    send_queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def audio_callback(indata, frames, time_info, status):
        if not is_robot_speaking:
            loop.call_soon_threadsafe(send_queue.put_nowait, indata.copy())

    try:
        async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
            print(">>> SUCCESS: LINK ESTABLISHED!")

            async def send_audio():
                silence_counter = 0
                is_speaking = False
                while True:
                    indata = await send_queue.get()
                    rms = np.sqrt(np.mean(indata.astype(np.float32)**2))

                    if rms > 600:
                        is_speaking = True
                        silence_counter = 0
                    elif is_speaking:
                        silence_counter += 1
                        if silence_counter > 25:
                            is_speaking = False
                            print("User turn finished. Awaiting AI response...")

                    audio_payload = indata.tobytes() if is_speaking else b'\x00' * len(indata.tobytes())
                    await session.send_realtime_input(
                        audio=types.Blob(data=audio_payload, mime_type='audio/pcm;rate=16000')
                    )

            async def receive_audio():
                global is_robot_speaking
                with sd.OutputStream(device=SPEAKER_DEVICE, channels=CHANNELS, samplerate=HARDWARE_OUT_RATE, dtype='int16') as out_stream:
                    while True:
                        async for message in session.receive():
                            if message.server_content and message.server_content.model_turn:
                                for part in message.server_content.model_turn.parts:

                                    # --- 🗂 HANDLE MEMORY TOOL CALLS ---
                                    if part.function_call:
                                        fn = part.function_call
                                        if fn.name == "store_structured_memory":
                                            print(f"\n🧠 [MEMORY SAVED]: {fn.args['content']}")
                                            res = store_structured_memory(**fn.args)
                                            await session.send_tool_response(
                                                function_responses=[types.FunctionResponse(
                                                    name=fn.name,
                                                    response={"result": res}
                                                )]
                                            )

                                    # --- 🔊 HANDLE AUDIO PLAYBACK ---
                                    elif part.inline_data:
                                        is_robot_speaking = True
                                        audio_data = np.frombuffer(part.inline_data.data, dtype='int16')
                                        resampled = np.interp(
                                            np.linspace(0, len(audio_data), int(len(audio_data) * HARDWARE_OUT_RATE / GEMINI_OUT_RATE)),
                                            np.arange(len(audio_data)),
                                            audio_data
                                        ).astype(np.int16)
                                        out_stream.write(resampled)

                            if message.server_content and message.server_content.turn_complete:
                                is_robot_speaking = False
                                while not send_queue.empty():
                                    try: send_queue.get_nowait()
                                    except asyncio.QueueEmpty: break
                                print("--- READY FOR NEXT TURN ---")

            with sd.InputStream(device=MIC_DEVICE, channels=CHANNELS, samplerate=SAMPLE_RATE, dtype='int16', callback=audio_callback):
                await asyncio.gather(send_audio(), receive_audio())

    except Exception as e:
        print(f"\n[!] System Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("\nRobot Sleeping.")
