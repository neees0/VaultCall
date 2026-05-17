"""
Analyse de la latence et de la qualité audio — métriques QoS/QoE.

Métriques mesurées :
    • Latence (one-way delay) en ms — horodatage émetteur embarqué dans l'AAD.
    • Gigue (jitter) RFC 3550 — variation inter-paquets de la latence.
    • Taux de perte — détection des sauts de numéro de séquence.
    • Niveau RMS (dBFS) — énergie instantanée du signal audio.
    • SNR estimé — lorsque le signal de référence est disponible (loopback test).
"""

from collections import deque

import numpy as np


class LatencyAnalyzer:
    """Calcule latence, gigue et perte de paquets en temps réel."""

    def __init__(self, window: int = 200):
        self._latencies = deque(maxlen=window)
        self._jitters   = deque(maxlen=window)
        self._received  = 0
        self._lost      = 0
        self._last_seq  = -1

    def record(self, send_ts: float, recv_ts: float, seq: int):
        """Enregistre un paquet reçu."""
        lat_ms = (recv_ts - send_ts) * 1000.0
        self._latencies.append(lat_ms)
        self._received += 1

        # Détection de pertes par saut de séquence
        if self._last_seq >= 0 and seq > self._last_seq + 1:
            self._lost += seq - self._last_seq - 1
        self._last_seq = seq

        # Gigue (variation absolue entre deux latences consécutives)
        if len(self._latencies) >= 2:
            self._jitters.append(abs(lat_ms - list(self._latencies)[-2]))

    def stats(self) -> dict:
        if not self._latencies:
            return {}
        lats   = list(self._latencies)
        jits   = list(self._jitters) or [0.0]
        total  = self._received + self._lost
        return {
            "latence_moy_ms":  round(np.mean(lats), 2),
            "latence_min_ms":  round(np.min(lats),  2),
            "latence_max_ms":  round(np.max(lats),  2),
            "latence_p95_ms":  round(np.percentile(lats, 95), 2),
            "gigue_moy_ms":    round(np.mean(jits), 2),
            "taux_perte_pct":  round(self._lost / max(total, 1) * 100, 2),
            "paquets_recus":   self._received,
            "paquets_perdus":  self._lost,
        }

    def display(self):
        s = self.stats()
        if not s:
            return
        print(
            f"[QoS]  Latence moy={s['latence_moy_ms']} ms | "
            f"P95={s['latence_p95_ms']} ms | "
            f"Gigue={s['gigue_moy_ms']} ms | "
            f"Perte={s['taux_perte_pct']}%"
        )


class AudioQualityAnalyzer:
    """Analyse la qualité du signal audio reçu."""

    def __init__(self, window: int = 100):
        self._snr_log   = deque(maxlen=window)
        self._rms_log   = deque(maxlen=window)

    def record_rms(self, pcm: bytes):
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        rms = np.sqrt(np.mean(samples ** 2))
        dbfs = 20 * np.log10(rms / 32768.0) if rms > 0 else -96.0
        self._rms_log.append(dbfs)
        return dbfs

    def compute_snr(self, original: bytes, decoded: bytes) -> float:
        """
        SNR entre signal original et signal après chiffrement/déchiffrement.
        Utile pour le test en loopback local.
        """
        orig = np.frombuffer(original, dtype=np.int16).astype(np.float64)
        dec  = np.frombuffer(decoded,  dtype=np.int16).astype(np.float64)
        n = min(len(orig), len(dec))
        orig, dec = orig[:n], dec[:n]

        noise_power  = np.mean((orig - dec) ** 2)
        signal_power = np.mean(orig ** 2)

        if noise_power == 0:
            snr = float("inf")
        else:
            snr = 10 * np.log10(signal_power / max(noise_power, 1e-12))

        self._snr_log.append(snr)
        return snr

    def stats(self) -> dict:
        result = {}
        if self._rms_log:
            rms = list(self._rms_log)
            result.update({
                "niveau_rms_moy_dBFS": round(np.mean(rms), 2),
                "niveau_rms_max_dBFS": round(np.max(rms),  2),
            })
        if self._snr_log:
            snr = list(self._snr_log)
            result.update({
                "snr_moy_dB": round(np.mean(snr), 2),
                "snr_min_dB": round(np.min(snr),  2),
            })
        return result
