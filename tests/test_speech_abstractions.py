import pytest

from media.speech import (
    SpeechToText,
    TextToSpeech,
    VoicePipeline,
    get_voice_pipeline,
)


class _DummySTT(SpeechToText):
    async def transcribe(self, audio_bytes: bytes, language_hint: str = "ru") -> str:
        return "расшифровка"


class _DummyTTS(TextToSpeech):
    async def synthesize(self, text: str, language: str = "ru") -> bytes:
        return b"ogg-opus-bytes"


def test_abstract_classes_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        SpeechToText()  # type: ignore[abstract]
    with pytest.raises(TypeError):
        TextToSpeech()  # type: ignore[abstract]


async def test_dummy_provider_implements_interface() -> None:
    assert await _DummySTT().transcribe(b"audio") == "расшифровка"
    assert await _DummyTTS().synthesize("текст") == b"ogg-opus-bytes"


def test_factory_without_providers() -> None:
    pipeline = get_voice_pipeline(enabled=True, mode="auto")
    assert pipeline.input_available is False
    assert pipeline.output_available is False
    assert pipeline.should_reply_with_voice(incoming_was_voice=True) is False


def test_should_reply_with_voice_modes() -> None:
    pipeline = VoicePipeline(stt=_DummySTT(), tts=_DummyTTS(), enabled=True, mode="auto")
    assert pipeline.should_reply_with_voice(incoming_was_voice=True) is True
    assert pipeline.should_reply_with_voice(incoming_was_voice=False) is False

    voice_pipeline = VoicePipeline(stt=_DummySTT(), tts=_DummyTTS(), enabled=True, mode="voice")
    assert voice_pipeline.should_reply_with_voice(incoming_was_voice=False) is True

    text_pipeline = VoicePipeline(stt=_DummySTT(), tts=_DummyTTS(), enabled=True, mode="text")
    assert text_pipeline.should_reply_with_voice(incoming_was_voice=True) is False

    disabled = VoicePipeline(stt=_DummySTT(), tts=_DummyTTS(), enabled=False, mode="voice")
    assert disabled.should_reply_with_voice(incoming_was_voice=True) is False
