"""
Capture microphone et lecture haut-parleur via PyAudio.

Architecture :
    • AudioCapture  — lit le micro en callback non-bloquant, place les trames dans une file.
    • AudioPlayback — lit la file dans un thread dédié ; tampon de gigue intégré.
"""

import threading
import queue

import pyaudio
import numpy as np

from config import SAMPLE_RATE, CHANNELS, CHUNK_SIZE, JITTER_BUF_MAX


class AudioCapture:
    def __init__(self):
        self._pa     = pyaudio.PyAudio()
        self._queue  = queue.Queue()
        self._stream = None
        self._active = False

    def start(self):
        self._active = True
        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE,
            stream_callback=self._callback,
        )
        self._stream.start_stream()

    def _callback(self, in_data, frame_count, time_info, status):
        if self._active:
            self._queue.put(in_data)
        return (None, pyaudio.paContinue)

    def read(self, timeout: float = 1.0) -> bytes:
        """Bloque jusqu'à ce qu'une trame PCM soit disponible."""
        return self._queue.get(timeout=timeout)

    def stop(self):
        self._active = False
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        self._pa.terminate()


class AudioPlayback:
    def __init__(self):
        self._pa     = pyaudio.PyAudio()
        self._queue  = queue.Queue(maxsize=JITTER_BUF_MAX)
        self._stream = None
        self._thread = None
        self._active = False

        # Silence d'une trame (pour le remplissage en cas de sous-débit)
        self._silence = b"\x00" * CHUNK_SIZE * 2

    def start(self):
        self._active = True
        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            output=True,
            frames_per_buffer=CHUNK_SIZE,
        )
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while self._active:
            try:
                data = self._queue.get(timeout=0.1)
            except queue.Empty:
                data = self._silence   # insertion de silence (PLC basique)
            self._stream.write(data)

    def play(self, pcm: bytes):
        """Enqueue une trame PCM ; abandonne si le tampon est plein (stratégie drop-tail)."""
        try:
            self._queue.put_nowait(pcm)
        except queue.Full:
            pass

    def stop(self):
        self._active = False
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        self._pa.terminate()

    # ── Utilitaire : niveau RMS ───────────────────────────────────────────────

    @staticmethod
    def rms_dbfs(pcm: bytes) -> float:
        """Niveau RMS en dBFS d'une trame PCM 16 bits."""
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        rms = np.sqrt(np.mean(samples ** 2))
        if rms == 0:
            return -96.0
        return float(20 * np.log10(rms / 32768.0))
