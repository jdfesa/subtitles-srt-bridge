from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import wave

from subtitles_bridge.adapters.whisper import (
    WhisperConfig,
    WhisperSpeechRecognizer,
)
from subtitles_bridge.errors import TranscriptionDependencyError, TranscriptionError


class FakeModel:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def transcribe(self, audio, **options):
        self.calls.append((audio, options))
        if self.error is not None:
            raise self.error
        return self.result


class FakeArray:
    def __init__(self, frames, dtype):
        self.frames = frames
        self.dtype = dtype

    def astype(self, dtype):
        self.dtype = dtype
        return self

    def __truediv__(self, divisor):
        return (self.frames, self.dtype, divisor)


class FakeNumpy:
    float32 = "float32"

    @staticmethod
    def frombuffer(frames, dtype):
        return FakeArray(frames, dtype)


class WhisperSpeechRecognizerTests(unittest.TestCase):
    def make_cache(self, content=b"model"):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        checkpoint = root / "small.pt"
        checkpoint.write_bytes(content)
        checksum = sha256(content).hexdigest()
        url = f"https://models.example/{checksum}/small.pt"
        return root, checkpoint, url

    def test_uses_valid_local_cache_and_detects_language_with_transcribe_task(self):
        cache, checkpoint, url = self.make_cache()
        model = FakeModel(
            {
                "language": "ru",
                "segments": [
                    {"start": 0.0, "end": 1.5, "text": "Привет"},
                ],
            }
        )
        load_calls = []

        def load_model(path, **options):
            load_calls.append((path, options))
            return model

        module = SimpleNamespace(_MODELS={"small": url}, load_model=load_model)
        recognizer = WhisperSpeechRecognizer(
            WhisperConfig(model="small", cache_directory=cache),
            module_loader=lambda name: module,
            python_executable="/env/bin/python",
            audio_loader=lambda path: f"samples:{path}",
        )

        transcript = recognizer.transcribe(Path("selected.wav"))
        second_transcript = recognizer.transcribe(Path("selected-2.wav"))

        self.assertEqual(load_calls, [(str(checkpoint.resolve()), {})])
        self.assertEqual(
            model.calls,
            [
                ("samples:selected.wav", {"task": "transcribe"}),
                ("samples:selected-2.wav", {"task": "transcribe"}),
            ],
        )
        self.assertEqual(transcript.language, "ru")
        self.assertEqual(transcript.segments[0].text, "Привет")
        self.assertEqual(second_transcript, transcript)

    def test_verifies_local_model_without_loading_it(self):
        cache, checkpoint, url = self.make_cache()
        load_calls = []
        module = SimpleNamespace(
            _MODELS={"small": url},
            load_model=lambda *args, **kwargs: load_calls.append((args, kwargs)),
        )
        recognizer = WhisperSpeechRecognizer(
            WhisperConfig(model="small", cache_directory=cache),
            module_loader=lambda name: module,
        )

        resolved = recognizer.verify_local_model()

        self.assertEqual(resolved, checkpoint.resolve())
        self.assertEqual(load_calls, [])
        self.assertIsNone(recognizer._model)

    def test_uses_explicit_local_checkpoint_language_and_device(self):
        _, checkpoint, _ = self.make_cache()
        model = FakeModel(
            {
                "language": "es",
                "segments": [{"start": 0, "end": 1, "text": "Hola"}],
            }
        )
        load_calls = []
        module = SimpleNamespace(
            load_model=lambda path, **options: (
                load_calls.append((path, options)) or model
            )
        )
        recognizer = WhisperSpeechRecognizer(
            WhisperConfig(
                model=str(checkpoint),
                device="cpu",
                language="es",
            ),
            module_loader=lambda name: module,
            audio_loader=lambda path: "samples",
        )

        transcript = recognizer.transcribe(Path("selected.wav"))

        self.assertEqual(
            load_calls,
            [(str(checkpoint.resolve()), {"device": "cpu"})],
        )
        self.assertEqual(
            model.calls[0][1],
            {"task": "transcribe", "language": "es"},
        )
        self.assertEqual(transcript.language, "spa")

    def test_loads_the_selected_pcm_wave_without_a_second_ffmpeg_process(self):
        root, checkpoint, _ = self.make_cache()
        audio = root / "selected.wav"
        frames = b"\x00\x00\x01\x00"
        with wave.open(str(audio), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16_000)
            output.writeframes(frames)
        model = FakeModel(
            {
                "language": "en",
                "segments": [{"start": 0, "end": 1, "text": "Hello"}],
            }
        )
        whisper_module = SimpleNamespace(load_model=lambda *args, **kwargs: model)

        def module_loader(name):
            return FakeNumpy if name == "numpy" else whisper_module

        recognizer = WhisperSpeechRecognizer(
            WhisperConfig(model=str(checkpoint)),
            module_loader=module_loader,
        )

        recognizer.transcribe(audio)

        self.assertEqual(
            model.calls[0][0],
            (frames, "float32", 32768.0),
        )
        self.assertEqual(model.calls[0][1], {"task": "transcribe"})

    def test_reports_install_command_for_the_active_python_environment(self):
        def missing_module(name):
            raise ModuleNotFoundError("No module named whisper")

        recognizer = WhisperSpeechRecognizer(
            module_loader=missing_module,
            python_executable="/custom/.venv/bin/python",
            audio_loader=lambda path: "samples",
        )

        with self.assertRaisesRegex(
            TranscriptionDependencyError,
            "/custom/.venv/bin/python.*openai-whisper",
        ):
            recognizer.transcribe(Path("selected.wav"))

    def test_refuses_missing_or_corrupt_cached_model_without_loading(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        cache = Path(temporary_directory.name)
        expected_content = b"expected"
        checksum = sha256(expected_content).hexdigest()
        url = f"https://models.example/{checksum}/small.pt"
        load_calls = []
        module = SimpleNamespace(
            _MODELS={"small": url},
            load_model=lambda *args, **kwargs: load_calls.append(args),
        )
        recognizer = WhisperSpeechRecognizer(
            WhisperConfig(model="small", cache_directory=cache),
            module_loader=lambda name: module,
            python_executable="/env/bin/python",
            audio_loader=lambda path: "samples",
        )

        with self.assertRaisesRegex(TranscriptionDependencyError, "Preload"):
            recognizer.transcribe(Path("selected.wav"))

        (cache / "small.pt").write_bytes(b"corrupt")
        with self.assertRaisesRegex(TranscriptionDependencyError, "checksum"):
            recognizer.transcribe(Path("selected.wav"))

        self.assertEqual(load_calls, [])

    def test_propagates_model_failure_and_rejects_malformed_result(self):
        _, checkpoint, _ = self.make_cache()
        cases = (
            (FakeModel(error=RuntimeError("decode failed")), "decode failed"),
            (FakeModel({"language": "en"}), "does not contain segments"),
            (
                FakeModel(
                    {
                        "language": "en",
                        "segments": [{"start": 2, "end": 1, "text": "bad"}],
                    }
                ),
                "invalid segment",
            ),
        )

        for model, message in cases:
            with self.subTest(message=message):
                module = SimpleNamespace(load_model=lambda *args, model=model: model)
                recognizer = WhisperSpeechRecognizer(
                    WhisperConfig(model=str(checkpoint)),
                    module_loader=lambda name, module=module: module,
                    audio_loader=lambda path: "samples",
                )
                with self.assertRaisesRegex(TranscriptionError, message):
                    recognizer.transcribe(Path("selected.wav"))


if __name__ == "__main__":
    unittest.main()
