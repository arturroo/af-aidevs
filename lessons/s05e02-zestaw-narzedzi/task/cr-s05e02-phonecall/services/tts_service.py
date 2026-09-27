import base64
import logging

from google.cloud import texttospeech

import config

logger = logging.getLogger("services.tts")


class TTSService:
    """Synthesizes Polish speech to MP3 format using Google Cloud Text-to-Speech API."""

    def __init__(
        self,
        voice_name: str = config.DEFAULT_VOICE_NAME,
        speaking_rate: float = config.DEFAULT_SPEAKING_RATE,
    ) -> None:
        self.client = texttospeech.TextToSpeechClient()
        self.voice_name = voice_name
        self.speaking_rate = speaking_rate

    def synthesize_mp3_bytes(
        self,
        text_or_ssml: str,
        voice_name: str | None = None,
        speaking_rate: float | None = None,
    ) -> bytes:
        voice = voice_name or self.voice_name
        rate = speaking_rate or self.speaking_rate

        # Determine if input is SSML or plain text
        is_ssml = text_or_ssml.strip().startswith("<speak>")

        if is_ssml:
            synthesis_input = texttospeech.SynthesisInput(ssml=text_or_ssml)
        else:
            synthesis_input = texttospeech.SynthesisInput(text=text_or_ssml)

        # Build voice selection
        voice_params = texttospeech.VoiceSelectionParams(
            language_code="pl-PL",
            name=voice,
        )

        # Audio config for MP3 format
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=rate,
        )

        logger.info(
            f"Synthesizing audio via Google Cloud TTS (voice={voice}, rate={rate}, is_ssml={is_ssml})"
        )

        try:
            response = self.client.synthesize_speech(
                input=synthesis_input,
                voice=voice_params,
                audio_config=audio_config,
            )
        except Exception as e:
            logger.warning(
                f"TTS synthesis failed with voice '{voice}' ({e}). Retrying with fallback 'pl-PL-Wavenet-G'..."
            )
            fallback_voice_params = texttospeech.VoiceSelectionParams(
                language_code="pl-PL",
                name="pl-PL-Wavenet-G",
            )
            response = self.client.synthesize_speech(
                input=synthesis_input,
                voice=fallback_voice_params,
                audio_config=audio_config,
            )

        audio_bytes = response.audio_content
        logger.info(
            f"TTS synthesis complete: generated {len(audio_bytes)} bytes of MP3"
        )
        return audio_bytes

    def synthesize_base64_mp3(
        self,
        text_or_ssml: str,
        voice_name: str | None = None,
        speaking_rate: float | None = None,
    ) -> str:
        audio_bytes = self.synthesize_mp3_bytes(
            text_or_ssml, voice_name=voice_name, speaking_rate=speaking_rate
        )
        return base64.b64encode(audio_bytes).decode("utf-8")
