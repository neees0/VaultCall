"""
VaultCall — Application de communication audio chiffrée de bout en bout.

Architecture :
    Appelant (caller)                     Appelé (callee)
    ──────────────────                    ──────────────────
    Génère clé X25519          ──pub──>   Génère clé X25519
    Reçoit clé pair            <──pub──
    HKDF → clé session AES-GCM            HKDF → clé session AES-GCM
    Capture micro → Chiffre → MQTT ──>   MQTT → Déchiffre → Haut-parleur
    Haut-parleur  ← Déchiffre ← MQTT <── MQTT ← Chiffre ← Capture micro

Usage :
    python main.py caller --session test123 --cipher AES-GCM
    python main.py callee --session test123 --cipher AES-GCM
"""

import argparse
import signal
import sys
import threading
import time

from config import (
    DEFAULT_CIPHER, MQTT_BROKER, MQTT_PORT,
    MQTT_AUDIO_TOPIC, MQTT_SIGNAL_TOPIC,
)
from crypto.key_exchange import KeyExchange
from crypto.symmetric    import AudioEncryptor
from audio.audio_handler import AudioCapture, AudioPlayback
from network.mqtt_client import SecureMQTTClient
from analysis.metrics    import LatencyAnalyzer, AudioQualityAnalyzer


class VaultCallApp:

    def __init__(self, mode: str, session: str, cipher: str):
        self.mode    = mode      # "caller" | "callee"
        self.session = session
        self.cipher  = cipher

        self._audio_topic  = MQTT_AUDIO_TOPIC.format(session_id=session)
        self._signal_topic = MQTT_SIGNAL_TOPIC.format(session_id=session)

        # Crypto
        self._kex       = KeyExchange()
        self._enc: AudioEncryptor | None = None

        # Audio
        self._capture  = AudioCapture()
        self._playback = AudioPlayback()

        # Réseau
        cid = f"vaultcall-{mode}-{session[:8]}"
        self._mqtt = SecureMQTTClient(MQTT_BROKER, MQTT_PORT, cid)

        # Analyse
        self._lat_analyzer = LatencyAnalyzer()
        self._qa_analyzer  = AudioQualityAnalyzer()

        self._running     = False
        self._key_ready   = threading.Event()
        self._stats_interval = 5.0   # secondes

    # ── Démarrage ─────────────────────────────────────────────────────────────

    def start(self):
        print(f"[VaultCall] Mode={self.mode}  Session={self.session}  Cipher={self.cipher}")

        self._mqtt.connect()

        # Abonnements
        self._mqtt.subscribe(self._signal_topic + "/+", self._on_signal)
        recv_topic = self._audio_topic + "/" + ("callee" if self.mode == "caller" else "caller")
        self._mqtt.subscribe(recv_topic, self._on_audio)

        # Échange de clés X25519
        self._publish_public_key()

        if not self._key_ready.wait(timeout=15.0):
            print("[VaultCall] ✗ Délai d'échange de clés dépassé.")
            self._mqtt.disconnect()
            return

        print(f"[VaultCall] ✓ Clé de session établie ({self.cipher}, 256 bits)")

        # Démarrage audio
        self._running = True
        self._playback.start()
        self._capture.start()

        threading.Thread(target=self._send_loop,  daemon=True).start()
        threading.Thread(target=self._stats_loop, daemon=True).start()

        print("[VaultCall] Appel en cours… (Ctrl+C pour raccrocher)\n")

    # ── Échange de clés ───────────────────────────────────────────────────────

    def _publish_public_key(self):
        topic = self._signal_topic + f"/pubkey_{self.mode}"
        self._mqtt.publish(topic, self._kex.get_public_bytes())

    def _on_signal(self, topic: str, payload: bytes):
        if self._key_ready.is_set():
            return

        # Le caller attend la clé du callee et vice-versa
        expected = "pubkey_callee" if self.mode == "caller" else "pubkey_caller"
        if expected not in topic:
            return

        session_key = self._kex.derive_session_key(payload)
        self._enc   = AudioEncryptor(session_key, self.cipher)
        self._key_ready.set()
        print(f"[VaultCall] ✓ Clé dérivée via X25519+HKDF depuis {expected}")

    # ── Boucle d'émission ─────────────────────────────────────────────────────

    def _send_loop(self):
        send_topic = self._audio_topic + f"/{self.mode}"
        while self._running:
            try:
                pcm = self._capture.read(timeout=0.5)
                if self._enc:
                    packet = self._enc.encrypt(pcm)
                    self._mqtt.publish(send_topic, packet)
            except Exception:
                pass

    # ── Réception audio ───────────────────────────────────────────────────────

    def _on_audio(self, topic: str, payload: bytes):
        if not self._enc:
            return
        recv_ts = time.time()
        try:
            pcm, seq, send_ts = self._enc.decrypt(payload)
        except Exception as e:
            print(f"[VaultCall] ✗ Déchiffrement échoué : {e}")
            return

        self._playback.play(pcm)
        self._lat_analyzer.record(send_ts, recv_ts, seq)
        self._qa_analyzer.record_rms(pcm)

    # ── Boucle de statistiques ────────────────────────────────────────────────

    def _stats_loop(self):
        while self._running:
            time.sleep(self._stats_interval)
            self._lat_analyzer.display()

    # ── Arrêt ─────────────────────────────────────────────────────────────────

    def stop(self):
        self._running = False
        try:
            self._capture.stop()
            self._playback.stop()
        except Exception:
            pass
        self._mqtt.disconnect()

        print("\n" + "=" * 55)
        print("  VaultCall — Rapport de fin d'appel")
        print("=" * 55)
        print("\n  [QoS — Réseau]")
        for k, v in self._lat_analyzer.stats().items():
            print(f"    {k:<25} {v}")
        print("\n  [QoE — Audio]")
        for k, v in self._qa_analyzer.stats().items():
            print(f"    {k:<25} {v}")
        print()


# ── Point d'entrée ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="VaultCall — Communication audio chiffrée E2EE sur MQTT/TLS"
    )
    parser.add_argument("mode", choices=["caller", "callee"],
                        help="Rôle dans l'appel")
    parser.add_argument("--session", default="demo",
                        help="Identifiant de session (même valeur des deux côtés)")
    parser.add_argument("--cipher",  default=DEFAULT_CIPHER,
                        choices=["AES-GCM", "ChaCha20-Poly1305"],
                        help="Algorithme de chiffrement symétrique")
    args = parser.parse_args()

    app = VaultCallApp(args.mode, args.session, args.cipher)

    def _on_sigint(sig, frame):
        app.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _on_sigint)

    app.start()

    # Maintenir le thread principal vivant
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        app.stop()


if __name__ == "__main__":
    main()
