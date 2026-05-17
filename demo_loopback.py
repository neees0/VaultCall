"""
Démo loopback — Test du pipeline crypto SANS broker MQTT ni micro réel.

Ce script simule un appel complet en local :
    1. Génère un signal audio synthétique (sinusoïde).
    2. Effectue l'échange de clés X25519 entre Alice et Bob.
    3. Alice chiffre → Bob déchiffre (AES-GCM et ChaCha20-Poly1305).
    4. Mesure et affiche latence, SNR, intégrité des données.

Usage :
    python demo_loopback.py
"""

import time
import numpy as np

from crypto.key_exchange import KeyExchange
from crypto.symmetric    import AudioEncryptor
from analysis.metrics    import LatencyAnalyzer, AudioQualityAnalyzer

SAMPLE_RATE = 16000
CHUNK_SIZE  = 1024
N_PACKETS   = 200       # nombre de trames simulées
FREQ_HZ     = 440       # fréquence de la sinusoïde (La4)


def generate_sine(freq: int, n: int, rate: int, amplitude: int = 16000) -> bytes:
    t = np.linspace(0, n / rate, n, endpoint=False)
    samples = (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.int16)
    return samples.tobytes()


def run_demo(cipher: str):
    print(f"\n{'=' * 55}")
    print(f"  VaultCall — Démo loopback ({cipher})")
    print(f"{'=' * 55}")

    # ── Échange de clés ───────────────────────────────────────────────────────
    kex_alice = KeyExchange()
    kex_bob   = KeyExchange()

    key_alice = kex_alice.derive_session_key(kex_bob.get_public_bytes())
    key_bob   = kex_bob.derive_session_key(kex_alice.get_public_bytes())

    assert key_alice == key_bob, "Les clés doivent être identiques !"
    print(f"  ✓ Clé de session X25519+HKDF : {key_alice.hex()[:32]}…")

    enc_alice = AudioEncryptor(key_alice, cipher)
    enc_bob   = AudioEncryptor(key_bob,   cipher)

    # ── Analyse ───────────────────────────────────────────────────────────────
    lat  = LatencyAnalyzer()
    qa   = AudioQualityAnalyzer()

    pcm_original = generate_sine(FREQ_HZ, CHUNK_SIZE, SAMPLE_RATE)

    print(f"  Simulation de {N_PACKETS} trames audio ({CHUNK_SIZE} échantillons chacune)…\n")

    for i in range(N_PACKETS):
        send_ts = time.time()

        packet = enc_alice.encrypt(pcm_original, send_ts)

        # Simulation d'un délai réseau réaliste (10–40 ms)
        simulated_delay = np.random.uniform(0.010, 0.040)
        time.sleep(simulated_delay)

        recv_ts = time.time()
        pcm_decoded, seq, embedded_ts = enc_bob.decrypt(packet)

        lat.record(embedded_ts, recv_ts, seq)
        qa.record_rms(pcm_decoded)
        qa.compute_snr(pcm_original, pcm_decoded)

    # ── Résultats ─────────────────────────────────────────────────────────────
    print("  [QoS — Réseau]")
    for k, v in lat.stats().items():
        print(f"    {k:<30} {v}")

    print("\n  [QoE — Qualité audio]")
    for k, v in qa.stats().items():
        print(f"    {k:<30} {v}")


if __name__ == "__main__":
    run_demo("AES-GCM")
    run_demo("ChaCha20-Poly1305")
    print("\n  ✓ Démo terminée. Le pipeline cryptographique fonctionne correctement.")
