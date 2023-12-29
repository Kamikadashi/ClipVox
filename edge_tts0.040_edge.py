import threading
import time
import pyperclip
import pygame
from pynput import keyboard
from gtts import gTTS
import subprocess
from pydub import AudioSegment
import re
import queue
import os
import tempfile

# Initialize Pygame for audio playback
pygame.mixer.init()

# Global variable to track the active state
active = False

# Global variable to store previous clipboard content
previous_clipboard = ""

# Global variable to indicate if the audio is paused
audio_paused = False

# Global variable to store the queue of audio chunks
audio_queue = queue.Queue()

# Global variables to store the current parameters
current_rate = "-15%"
current_speed_factor = 2.90
current_asetrate_factor = 0.94

# Global variable to store the current voice
current_voice = "en-US-ChristopherNeural"

# List of voices
voices = ["en-US-ChristopherNeural", "ja-JP-KeitaNeural", "ja-JP-NanamiNeural", "uk-UA-PolinaNeural", "uk-UA-OstapNeural", "de-DE-ConradNeural", "ru-RU-DmitryNeural"]

# Key press event listener
def on_key_press(key):
    global active
    global previous_clipboard
    global audio_paused
    global current_voice
    global current_rate
    global current_speed_factor
    global current_asetrate_factor

    try:
        if key.char == '5':
            active = not active
            if active:
                previous_clipboard = pyperclip.paste()
                print("Activated")
            else:
                print("Deactivated")
        elif key.char == '0':
            for _ in range(10):  # Trigger the action 10 times.
                pygame.mixer.music.stop()
                while not audio_queue.empty():  # Clear the audio queue when '0' is pressed.
                    audio_queue.get()
                time.sleep(0.2)  # Wait for 0.2 seconds between each action.
        elif key.char == '6':
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.pause()
                audio_paused = True  # Set the flag to indicate that the audio is paused.
            else:
                pygame.mixer.music.unpause()
                audio_paused = False  # Reset the flag when unpausing.
        elif key.char == '1':
            # Change the current voice to the next one in the list
            current_voice = voices[(voices.index(current_voice) + 1) % len(voices)]
            print(f"Voice changed to {current_voice}")
        elif key.char == '2':
            # Change the current rate
            current_rate = input("Enter new edge tts speed rate (-15%): ")
            print(f"Rate changed to {current_rate}")
        elif key.char == '3':
            # Change the current speed factor
            current_speed_factor = float(input("Enter new ffmpeg speed factor(2.90): "))
            print(f"Speed factor changed to {current_speed_factor}")
        elif key.char == '4':
            # Change the current asetrate factor
            current_asetrate_factor = float(input("Enter new asetrate pitch factor(0.94): "))
            print(f"Asetrate factor changed to {current_asetrate_factor}")
    except AttributeError:
        pass

# Clipboard monitoring thread
def clipboard_monitor():
    global previous_clipboard
    while True:
        if active:
            try:
                current_clipboard = pyperclip.paste()
            except pyperclip.PyperclipWindowsException:
                time.sleep(0.5)  # Wait for half a second before retrying.
                continue  # Skip the rest of this loop iteration.
            
            if has_kanji_or_letters(current_clipboard):
                if current_clipboard != previous_clipboard:
                    previous_clipboard = current_clipboard
                    process_clipboard_text(current_clipboard)
        time.sleep(0.1)  # Reduced sleep time for faster clipboard monitoring.


def has_kanji_or_letters(text):
    # Regular expression to match kanji or alphabetic characters.
    kanji_or_letters_pattern = re.compile(r'[一-龯A-Za-zぁ-んА-Яа-я]')
    return bool(kanji_or_letters_pattern.search(text))

def process_clipboard_text(text):
    text = re.sub(r'\r\n|\n|\r', ' ', text)  # Replace all newlines with spaces.
    sentences = re.split('(?<=[.!?]) +', text)  # Split the text into sentences.

    chunks = []
    current_chunk = []
    chunk_size = 2

    for sentence in sentences:
        if len(current_chunk) < chunk_size:
            current_chunk.append(sentence)
        else:
            chunks.append(' '.join(current_chunk))
            current_chunk = [sentence]
            chunk_size *= 4  # Double the chunk size.
            if chunk_size > 16:  # Reset the chunk size back to 2 after it reaches 16.
                chunk_size = 16

    if current_chunk:  # Don't forget the last chunk.
        chunks.append(' '.join(current_chunk))

    for chunk in chunks:
        audio_queue.put(chunk)  # Add the chunk to the queue.

    # Start a new thread to generate and play audio only if there isn't one already running.
    if not any([t.is_alive() for t in threading.enumerate() if t.name == "AudioThread"]):
        threading.Thread(target=generate_and_play_audio, name="AudioThread").start()

previous_files = []  # List to store the paths of previous files

def generate_and_play_audio():
    global audio_paused
    global previous_files

    while not audio_queue.empty():
        chunk = audio_queue.get()
        # Create temporary files for the output and speedup versions
        output_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        speedup_output_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        output_file_name = output_file.name
        speedup_output_file_name = speedup_output_file.name
        output_file.close()
        speedup_output_file.close()
        generate_audio(chunk, output_file_name, speedup_output_file_name)

        # Wait for the current chunk to finish playing before starting the next one.
        while pygame.mixer.music.get_busy() or audio_paused:  # Add a check for the pause flag here.
            time.sleep(0.1)  # Check every 100ms.

        if not audio_paused:  # Only start the next chunk if the audio is not paused.
            previous_files.append((output_file_name, speedup_output_file_name))  # Add the current files to the list of previous files
            if len(previous_files) > 2:  # If there are more than two previous files
                old_output_file, old_speedup_file = previous_files.pop(0)  # Remove the oldest files from the list
                threading.Thread(target=play_audio, args=(speedup_output_file_name, old_output_file, old_speedup_file), name="PlaybackThread").start()
            else:
                threading.Thread(target=play_audio, args=(speedup_output_file_name, None, None), name="PlaybackThread").start()

def generate_audio(text, output_file_name, speedup_output_file_name):
    success = False
    while not success:
        try:
            subprocess.run([
                "edge-tts",
                "--rate={}".format(current_rate),
                "--voice", current_voice,  # Use the current voice
                "--text", text,
                "--write-media", output_file_name,
            ])
            speedup_audio(output_file_name, speedup_output_file_name, current_speed_factor, current_asetrate_factor)  # Use the current speed factor and asetrate factor
            success = True
        except Exception as e:
            print(f"Failed to generate audio: {e}")
            print("Retrying in 5 seconds...")
            time.sleep(5)  # Wait for 5 seconds before retrying

# Speed up audio using FFmpeg.
def speedup_audio(input_file, output_file, speed_factor, asetrate_factor):
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", input_file,
        "-filter:a", f"atempo={speed_factor}, asetrate=24000*{asetrate_factor}, afftdn, loudnorm",  # Use the current asetrate factor
        "-vn",  # Disable video stream.
        "-y",   # Overwrite output file if it exists.
        output_file
    ]
    subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def play_audio(file_path, old_output_file, old_speedup_file):
    pygame.mixer.music.load(file_path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():  # Wait for the audio to finish playing
        pygame.time.Clock().tick(10)
    if old_output_file and old_speedup_file:  # If there are old files to delete
        os.remove(old_output_file)  # Remove the old original version
        os.remove(old_speedup_file)  # Remove the old speedup version

# Start clipboard monitoring thread.
clipboard_thread = threading.Thread(target=clipboard_monitor)
clipboard_thread.daemon = True
clipboard_thread.start()

# Start key press event listener.
with keyboard.Listener(on_press=on_key_press) as listener:
    print("Press 5 to toggle activation.")
    print("Press 0 to stop the audio and clear the queue.")
    print("Press 6 to pause/unpause the audio.")
    print("Press 1 to change the voice.")
    print("Press 2 to change the edge tts speed rate.")
    print("Press 3 to change the ffmpeg speed factor.")
    print("Press 4 to change the asetrate pitch factor.")
    listener.join()
