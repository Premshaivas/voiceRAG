from __future__ import annotations

import assemblyai as aai

from .config import settings


class AssemblyAITranscriber:
    def __init__(self, api_key: str | None = None, speech_model: str | None = None):
        self.api_key = api_key or settings.assemblyai_api_key
        self.speech_model = speech_model or settings.assemblyai_speech_model

    def transcribe(self, path: str):
        if not self.api_key:
            raise RuntimeError("ASSEMBLYAI_API_KEY is not configured")
        config = aai.TranscriptionConfig(speech_models=[self.speech_model, "universal-2"], language_detection=True)
        transcript = aai.Transcriber(api_key=self.api_key).transcribe(path, config=config)
        if transcript.status == aai.TranscriptStatus.error:
            raise RuntimeError(transcript.error or "AssemblyAI transcription failed")
        if not transcript.text:
            raise RuntimeError("Transcription completed without text")
        return transcript

