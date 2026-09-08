"""Абстракции голосового ввода/вывода (ТЗ §18, §19; решение PLAN.md — провайдеры в v1 не подключаются).

Интерфейсы спроектированы так, что добавление провайдера (Whisper API, Yandex
SpeechKit, Silero и т.д.) — это один новый класс и фабрика, без правок ядра бота.
Важно (ТЗ §38): голосовая транскрипция — НЕДОСТОЯННЫЙ ввод; handler голоса обязан
оборачивать результат transcribe() так же, как документы/OCR.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

VoiceResponseMode = Literal["text", "voice", "auto"]


class SpeechToTextError(Exception):
    pass


class TextToSpeechError(Exception):
    pass


class SpeechToText(ABC):
    """Преобразует аудио (ogg/opus из Telegram) в текст.

    Пример подключения провайдера:

        class WhisperSTT(SpeechToText):
            async def transcribe(self, audio_bytes: bytes, language_hint: str = "ru") -> str:
                ...  # реальный вызов API

    и регистрация фабрики в media/speech.py: get_speech_to_text().
    """

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, language_hint: str = "ru") -> str:
        """Возвращает расшифрованный текст; при неудаче бросает SpeechToTextError."""


class TextToSpeech(ABC):
    """Синтезирует голосовой ответ. Формат — ogg/opus (нативный формат voice в Telegram)."""

    @abstractmethod
    async def synthesize(self, text: str, language: str = "ru") -> bytes:
        """Возвращает аудио-байты (ogg/opus); при неудаче бросает TextToSpeechError."""


@dataclass(frozen=True)
class VoicePipeline:
    """Связка STT+TTS + политика ответов (VOICE_RESPONSE_MODE из .env).

    Режимы (ТЗ §19):
    - text: всегда текстовый ответ;
    - voice: всегда голосовой (плюс текст);
    - auto: текст → текст; голосовое входящее → голосовой ответ; фото+голос → голосовой.
    """

    stt: SpeechToText | None
    tts: TextToSpeech | None
    enabled: bool
    mode: VoiceResponseMode

    @property
    def input_available(self) -> bool:
        return self.enabled and self.stt is not None

    @property
    def output_available(self) -> bool:
        return self.enabled and self.tts is not None

    def should_reply_with_voice(self, incoming_was_voice: bool) -> bool:
        if not self.output_available:
            return False
        if self.mode == "voice":
            return True
        if self.mode == "auto":
            return incoming_was_voice
        return False


def get_voice_pipeline(enabled: bool, mode: VoiceResponseMode) -> VoicePipeline:
    """Фабрика: провайдеры STT/TTS не сконфигурированы (v1), возвращает пайплайн без них.

    Когда решите подключить голос: реализуйте SpeechToText/TextToSpeech-провайдеры,
    добавьте ключи в .env и возвращайте их здесь.
    """
    return VoicePipeline(stt=None, tts=None, enabled=enabled, mode=mode)
