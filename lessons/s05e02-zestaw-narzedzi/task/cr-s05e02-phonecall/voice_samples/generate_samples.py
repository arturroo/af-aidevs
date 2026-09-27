#!/usr/bin/env python3
"""Script used to generate Polish voice samples for comparing Google Cloud TTS voices:
- pl-PL-Chirp3-HD-Fenrir (Google DeepMind Generative HD Voice - Crisp & Authoritative)
- pl-PL-Chirp3-HD-Charon (Google DeepMind Generative HD Voice - Gravelly & Deep)
- pl-PL-Wavenet-G (Standard DeepMind Wavenet Voice)
- pl-PL-Standard-G (Legacy Concatenative Voice)
"""

from pathlib import Path

from google.cloud import texttospeech

samples_dir = Path(__file__).parent
samples_dir.mkdir(parents=True, exist_ok=True)

client = texttospeech.TextToSpeechClient()
sample_text = (
    "Dzień dobry, z tej strony Tymon Gajewski, oficer logistyki Zygfryda. "
    "Dzwonię ze względu na transport organizowany do jednej z baz Zygfryda. "
    "Chciałbym zapytać o aktualny status dróg RD224, RD472 oraz RD820 – "
    "która z nich jest teraz przejezdna i bezpieczna?"
)

voices = [
    "pl-PL-Chirp3-HD-Fenrir",
    "pl-PL-Chirp3-HD-Charon",
    "pl-PL-Wavenet-G",
    "pl-PL-Standard-G",
]

for v in voices:
    print(f"Synthesizing sample for {v}...")
    resp = client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=sample_text),
        voice=texttospeech.VoiceSelectionParams(language_code="pl-PL", name=v),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.0,
        ),
    )
    target = samples_dir / f"{v}.mp3"
    target.write_bytes(resp.audio_content)
    print(f"Saved {target} ({len(resp.audio_content)} bytes)")

print("\nDone! All voice samples generated successfully.")
