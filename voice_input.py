#!/usr/bin/env python3
"""
Voice Input Mode for Terminal - Faster Whisper version
Toggle with Super+v: starts/stops voice recognition, types result via wtype.
"""

import os
import sys
import signal
import subprocess
import queue
import time
import threading
import numpy as np
import sounddevice as sd

PID_FILE = "/tmp/voice_input.pid"
INDICATOR_STATE = "/tmp/voice_indicator_state"
INDICATOR_SCRIPT = os.path.expanduser("~/customization/voice_indicator.py")
MIC_RATE = 44100      # USB mic native rate
WHISPER_RATE = 16000  # Whisper model rate
SILENCE_THRESHOLD = 500  # Audio level below this is silence
SILENCE_DURATION = 1.0   # Seconds of silence to trigger transcription
MIN_AUDIO_LENGTH = 0.5   # Minimum audio length to transcribe

indicator_proc = None
model = None

# Word to digit/shortcut mappings
WORD_MAP = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "zero": "0",
    "ten": "10", "eleven": "11", "twelve": "12",
    "yes": "y", "no": "n", "yeah": "y", "nope": "n",
}

# Commands - triggered by "execute <command>"
COMMANDS = {
    "click": ("wlrctl", ["pointer", "click"]),
    "right click": ("wlrctl", ["pointer", "click", "right"]),
    "double click": ("wlrctl", ["pointer", "click", "click"]),
    "enter": ("wtype", ["-k", "Return"]),
    "inner": ("wtype", ["-k", "Return"]),  # Whisper variant
    "select": ("wtype", ["-k", "Return"]),
    "up": ("wtype", ["-k", "Up"]),
    "down": ("wtype", ["-k", "Down"]),
    "left": ("wtype", ["-k", "Left"]),
    "right": ("wtype", ["-k", "Right"]),
    "write": ("wtype", ["-k", "Right"]),  # Whisper variant
    "tab": ("wtype", ["-k", "Tab"]),
    "escape": ("wtype", ["-k", "Escape"]),
    "scape": ("wtype", ["-k", "Escape"]),  # Whisper variant
    "backspace": ("wtype", ["-k", "BackSpace"]),
    "delete": ("wtype", ["-k", "Delete"]),
    "space": ("wtype", ["-k", "space"]),
    "page up": ("wtype", ["-k", "Page_Up"]),
    "page down": ("wtype", ["-k", "Page_Down"]),
    "home": ("wtype", ["-k", "Home"]),
    "end": ("wtype", ["-k", "End"]),
}

audio_buffer = []
audio_lock = threading.Lock()
last_sound_time = time.time()
is_recording = False

def resample(data, from_rate, to_rate):
    """Simple resampling using linear interpolation."""
    if len(data) == 0:
        return np.array([], dtype=np.float32)
    duration = len(data) / from_rate
    new_length = int(duration * to_rate)
    if new_length == 0:
        return np.array([], dtype=np.float32)
    indices = np.linspace(0, len(data) - 1, new_length)
    resampled = np.interp(indices, np.arange(len(data)), data)
    return resampled.astype(np.float32)

def audio_callback(indata, frames, time_info, status):
    """Called for each audio block from the microphone."""
    global last_sound_time, is_recording

    if status:
        print(status, file=sys.stderr)

    audio_data = indata[:, 0].copy()
    audio_level = np.abs(audio_data).mean() * 32768

    with audio_lock:
        if audio_level > SILENCE_THRESHOLD:
            last_sound_time = time.time()
            is_recording = True
        audio_buffer.extend(audio_data)

def bell():
    """Terminal bell for feedback."""
    print("\a", end="", flush=True)

def start_indicator():
    """Start the visual indicator overlay."""
    global indicator_proc
    try:
        indicator_proc = subprocess.Popen(
            ["python3", INDICATOR_SCRIPT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"Could not start indicator: {e}", file=sys.stderr)

def stop_indicator():
    """Stop the visual indicator overlay."""
    global indicator_proc
    try:
        with open(INDICATOR_STATE, "w") as f:
            f.write("off")
    except Exception:
        pass
    if indicator_proc:
        try:
            indicator_proc.terminate()
            indicator_proc.wait(timeout=1)
        except Exception:
            pass
        indicator_proc = None

def set_indicator(state):
    """Set indicator state: 'yellow' (listening) or 'green' (processing)."""
    try:
        with open(INDICATOR_STATE, "w") as f:
            f.write(state)
    except Exception:
        pass

def type_text(text):
    """Type text into focused window using wtype."""
    if not text.strip():
        return
    try:
        subprocess.run(["wtype", text], check=True, timeout=5)
    except subprocess.CalledProcessError as e:
        print(f"wtype error: {e}", file=sys.stderr)
    except FileNotFoundError:
        print("wtype not found", file=sys.stderr)

def execute_command(cmd):
    """Execute a voice command (click, arrow keys, etc.)."""
    if cmd not in COMMANDS:
        return False
    program, args = COMMANDS[cmd]
    try:
        subprocess.run([program] + args, check=True, timeout=5)
        print(f"[Execute] {cmd}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Cappy command error: {e}", file=sys.stderr)
        return False
    except FileNotFoundError:
        print(f"{program} not found", file=sys.stderr)
        return False

def handle_cappy(text):
    """Check for and handle Cappy commands. Returns (handled, remaining_text)."""
    # Strip punctuation and normalize
    lower = text.lower().strip().replace(".", " ").replace(",", " ").replace("!", " ").replace("?", " ")
    lower = " ".join(lower.split())  # normalize whitespace

    # Check for various ways Whisper might transcribe "Execute"
    cappy_variants = ["execute", "executed", "exec"]

    matched_prefix = None
    for variant in cappy_variants:
        if lower.startswith(variant):
            matched_prefix = variant
            break

    if not matched_prefix:
        return False, text

    # Extract command after the trigger word
    after_cappy = lower[len(matched_prefix):].strip()

    # Remove filler words Whisper might add
    for filler in ["us", "a", "the", "to"]:
        if after_cappy.startswith(filler + " "):
            after_cappy = after_cappy[len(filler):].strip()

    # Try to match longest command first (e.g., "right click" before "right")
    for cmd in sorted(COMMANDS.keys(), key=len, reverse=True):
        if after_cappy.startswith(cmd):
            execute_command(cmd)
            remaining = after_cappy[len(cmd):].strip()
            return True, remaining

    print(f"[Cappy] Unknown command: {after_cappy}", file=sys.stderr)
    return True, ""

def transform_text(text):
    """Convert spoken words to digits/shortcuts."""
    words = text.lower().split()
    result = []
    for word in words:
        clean = word.strip(".,!?")
        if clean in WORD_MAP:
            result.append(WORD_MAP[clean])
        else:
            result.append(word)
    return " ".join(result)

def transcribe_audio(audio_data):
    """Transcribe audio using faster-whisper."""
    global model

    if len(audio_data) < WHISPER_RATE * MIN_AUDIO_LENGTH:
        return ""

    # Normalize audio to float32 range [-1, 1]
    audio_float = audio_data.astype(np.float32)
    if audio_float.max() > 1.0:
        audio_float = audio_float / 32768.0

    try:
        segments, _ = model.transcribe(
            audio_float,
            language="en",
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            initial_prompt="Execute click. Execute enter. Execute up. Execute down. Execute left. Execute right. Execute tab. Execute escape. Execute backspace. Execute delete. Execute space. Execute page up. Execute page down. One two three four five six seven eight nine zero."
        )
        text = " ".join([seg.text.strip() for seg in segments])
        return text.strip()
    except Exception as e:
        print(f"Transcription error: {e}", file=sys.stderr)
        return ""

def is_running():
    """Check if another instance is running."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return pid
        except (ValueError, ProcessLookupError, PermissionError):
            os.remove(PID_FILE)
    return None

def stop_other_instance(pid):
    """Stop the other running instance."""
    try:
        os.kill(pid, signal.SIGUSR1)
        return True
    except Exception:
        return False

def write_pid():
    """Write our PID to the file."""
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

def cleanup(*args):
    """Clean up on exit."""
    stop_indicator()
    try:
        os.remove(PID_FILE)
    except Exception:
        pass

def run_recognition():
    """Main recognition loop."""
    global model, audio_buffer, last_sound_time, is_recording

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    signal.signal(signal.SIGUSR1, lambda *_: sys.exit(0))

    import atexit
    atexit.register(cleanup)

    write_pid()

    # Load faster-whisper model
    print("[Voice] Loading Whisper model...", file=sys.stderr)
    from faster_whisper import WhisperModel
    model = WhisperModel("small", device="cpu", compute_type="int8")
    print("[Voice] Model loaded!", file=sys.stderr)

    # Start visual indicator
    start_indicator()
    bell()

    try:
        with sd.InputStream(samplerate=MIC_RATE, channels=1,
                           dtype='float32', callback=audio_callback,
                           blocksize=int(MIC_RATE * 0.1)):
            while True:
                time.sleep(0.1)

                current_time = time.time()
                silence_time = current_time - last_sound_time

                # Check if we have audio and enough silence has passed
                with audio_lock:
                    buffer_duration = len(audio_buffer) / MIC_RATE
                    should_transcribe = (
                        is_recording and
                        silence_time > SILENCE_DURATION and
                        buffer_duration > MIN_AUDIO_LENGTH
                    )

                    if should_transcribe:
                        # Copy and clear buffer
                        audio_data = np.array(audio_buffer, dtype=np.float32)
                        audio_buffer.clear()
                        is_recording = False

                if should_transcribe:
                    set_indicator("green")

                    # Resample to 16kHz for Whisper
                    resampled = resample(audio_data, MIC_RATE, WHISPER_RATE)

                    text = transcribe_audio(resampled)

                    if text:
                        print(f"[Voice] Heard: {text}")

                        # Check for Cappy commands first
                        was_cappy, remaining = handle_cappy(text)

                        if was_cappy:
                            if remaining:
                                transformed = transform_text(remaining)
                                type_text(transformed + " ")
                        else:
                            transformed = transform_text(text)
                            type_text(transformed + " ")

                    set_indicator("yellow")

    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
    finally:
        bell()
        cleanup()

def main():
    other_pid = is_running()

    if other_pid:
        stop_other_instance(other_pid)
        print("Stopped voice input")
    else:
        run_recognition()

if __name__ == "__main__":
    main()
