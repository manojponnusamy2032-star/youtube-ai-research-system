"""Windows System.Speech text-to-speech service.

Implements the existing ``TTSService`` contract using Windows built-in
Speech (System.Speech). This is a local, zero-dependency narration
provider: it needs no API key, no network access and no downloaded voice
models. Audio is written as 16-bit PCM WAV files.

The implementation shells out to PowerShell's ``System.Speech`` assembly so
the Python process does not require the ``pywin32`` package.
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import sys
import tempfile
import wave
from typing import Any

from src.services.tts_service import TTSRequest, TTSService

logger = logging.getLogger(__name__)

_DEFAULT_SCRIPT = r"""
param([string]$textFile, [string]$outFile, [string]$voiceName)
try {
    Add-Type -AssemblyName System.Speech
    $speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
    if ($voiceName -and $voiceName -ne "") {
        $speaker.SelectVoice($voiceName)
    }
    $text = [System.IO.File]::ReadAllText($textFile)
    $speaker.SetOutputToWaveFile($outFile)
    $speaker.Speak($text)
    $speaker.Dispose()
    Write-Output "OK"
} catch {
    Write-Output ("ERR: " + $_.Exception.Message)
    exit 1
}
"""


class SystemSpeechTTSService(TTSService):
    """Generates narration audio using Windows built-in TTS voices."""

    def __init__(
        self,
        output_directory: str = "output/audio",
        voice: str | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        """Initialize the Windows TTS service.

        Args:
            output_directory: Directory where narration WAV files are written.
            voice: Optional installed SAPI voice name (e.g.
                ``Microsoft David Desktop``). Defaults to the system voice.
            timeout_seconds: Timeout for a single synthesis call.
        """
        self.output_directory = output_directory
        self.voice = voice or ""
        self.timeout_seconds = timeout_seconds
        self._script_path: str | None = None

    def is_available(self) -> bool:
        """Return True on Windows when PowerShell + System.Speech are usable."""
        if sys.platform != "win32":
            return False
        try:
            probe = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "try { Add-Type -AssemblyName System.Speech; "
                    "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices().Count } "
                    "catch { exit 1 }",
                ],
                shell=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return probe.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False

    def _ensure_script(self) -> str:
        """Write the embedded PowerShell synthesis script to a temp file."""
        if self._script_path is None or not os.path.exists(self._script_path):
            handle, path = tempfile.mkstemp(suffix=".ps1", prefix="system_speech_tts_")
            with os.fdopen(handle, "w", encoding="utf-8") as handle_file:
                handle_file.write(_DEFAULT_SCRIPT)
            self._script_path = path
        return self._script_path

    def generate(self, request: TTSRequest) -> dict[str, Any]:
        """Synthesize narration audio for a request.

        Args:
            request: TTS request containing the narration text.

        Returns:
            Dictionary with status, audio_reference and duration_seconds.
            On failure status is ``failed`` and ``error`` explains why.
        """
        if not isinstance(request, TTSRequest):
            raise ValueError("request must be a TTSRequest")
        if not request.text.strip():
            raise ValueError("text cannot be empty")

        if not self.is_available():
            return {
                "status": "failed",
                "audio_reference": None,
                "duration_seconds": 0.0,
                "error": "Windows System.Speech is not available",
            }

        output_path = self._build_output_path(request)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            duration = self.probe_duration(output_path)
            return {
                "status": "completed",
                "audio_reference": os.path.abspath(output_path),
                "duration_seconds": duration,
                "cached": True,
            }

        text_file: str | None = None
        try:
            handle, text_file = tempfile.mkstemp(suffix=".txt", prefix="narration_")
            with os.fdopen(handle, "w", encoding="utf-8") as handle_file:
                handle_file.write(request.text)

            command = [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                self._ensure_script(),
                "-textFile",
                text_file,
                "-outFile",
                output_path,
                "-voiceName",
                self.voice,
            ]
            result = subprocess.run(
                command,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "failed",
                "audio_reference": None,
                "duration_seconds": 0.0,
                "error": f"System.Speech timed out after {self.timeout_seconds}s",
            }
        except OSError as exc:
            return {
                "status": "failed",
                "audio_reference": None,
                "duration_seconds": 0.0,
                "error": f"System.Speech could not be executed: {exc}",
            }
        finally:
            if text_file and os.path.exists(text_file):
                try:
                    os.unlink(text_file)
                except OSError:
                    pass

        if result.returncode != 0:
            return {
                "status": "failed",
                "audio_reference": None,
                "duration_seconds": 0.0,
                "error": (
                    f"System.Speech failed with return code {result.returncode}: "
                    f"{(result.stderr or result.stdout or '').strip()[:400]}"
                ),
            }

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            return {
                "status": "failed",
                "audio_reference": None,
                "duration_seconds": 0.0,
                "error": f"System.Speech produced no audio at {output_path}",
            }

        duration = self.probe_duration(output_path)
        logger.info(f"System.Speech synthesized {output_path} ({duration}s)")
        return {
            "status": "completed",
            "audio_reference": os.path.abspath(output_path),
            "duration_seconds": duration,
            "command": command,
        }

    @staticmethod
    def probe_duration(wav_path: str) -> float:
        """Return the duration of a WAV file in seconds."""
        try:
            with wave.open(wav_path, "rb") as handle:
                frames = handle.getnframes()
                rate = handle.getframerate() or 1
            return round(frames / rate, 3)
        except (wave.Error, FileNotFoundError):
            return 0.0

    def _build_output_path(self, request: TTSRequest) -> str:
        """Build a deterministic output path for a request."""
        digest = hashlib.md5(
            f"{request.text}:{request.voice_reference}".encode("utf-8")
        ).hexdigest()[:12]
        os.makedirs(self.output_directory, exist_ok=True)
        return os.path.join(self.output_directory, f"narration_{digest}.wav")