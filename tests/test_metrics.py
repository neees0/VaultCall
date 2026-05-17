"""
Tests unitaires — Module d'analyse métriques VaultCall.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
import numpy as np
from analysis.metrics import LatencyAnalyzer, AudioQualityAnalyzer


class TestLatencyAnalyzer:

    def test_latence_calculee(self):
        ana = LatencyAnalyzer()
        t0 = time.time()
        ana.record(t0, t0 + 0.05, seq=0)   # 50 ms
        s = ana.stats()
        assert abs(s["latence_moy_ms"] - 50.0) < 1.0

    def test_detection_perte(self):
        ana = LatencyAnalyzer()
        t = time.time()
        ana.record(t, t + 0.01, seq=0)
        ana.record(t, t + 0.01, seq=3)   # seq 1 et 2 manquants
        assert ana.stats()["paquets_perdus"] == 2

    def test_taux_perte_zero_si_aucune_perte(self):
        ana = LatencyAnalyzer()
        t = time.time()
        for i in range(10):
            ana.record(t, t + 0.02, seq=i)
        assert ana.stats()["taux_perte_pct"] == 0.0


class TestAudioQualityAnalyzer:

    def _pcm(self, amplitude=1000, n=1024):
        samples = (np.ones(n) * amplitude).astype(np.int16)
        return samples.tobytes()

    def test_rms_signal_pur(self):
        qa = AudioQualityAnalyzer()
        pcm = self._pcm(amplitude=10000)
        rms = qa.record_rms(pcm)
        assert rms < 0, "RMS dBFS doit être négatif"
        assert rms > -40, "Signal fort → RMS élevé"

    def test_snr_infini_si_identique(self):
        qa  = AudioQualityAnalyzer()
        pcm = self._pcm()
        snr = qa.compute_snr(pcm, pcm)
        assert snr == float("inf")

    def test_snr_degrade_si_bruit(self):
        qa   = AudioQualityAnalyzer()
        orig = self._pcm(amplitude=8000)
        # Signal bruité : on ajoute du bruit
        samples = np.frombuffer(orig, np.int16).astype(np.float32)
        samples += np.random.normal(0, 500, len(samples))
        samples = np.clip(samples, -32768, 32767).astype(np.int16)
        noisy = samples.tobytes()
        snr = qa.compute_snr(orig, noisy)
        assert snr < 100, "SNR doit être fini si bruit présent"
