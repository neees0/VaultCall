"""
Client MQTT sécurisé avec authentification mutuelle TLS (mTLS).

Sécurité :
    • TLS 1.2+ obligatoire (PROTOCOL_TLS_CLIENT).
    • Certificat client présenté au broker (authentification mutuelle).
    • Vérification du certificat serveur via la CA interne.
    • MQTT v5 pour les propriétés étendues (expiry, user properties).

Référence :
    MQTT v5 spec § 4.6 (QoS), RFC 5246 (TLS), RFC 8446 (TLS 1.3).
"""

import ssl
import time
from typing import Callable

import paho.mqtt.client as mqtt

from config import CA_CERT, CLIENT_CERT, CLIENT_KEY, MQTT_QOS


class SecureMQTTClient:
    def __init__(
        self,
        broker: str,
        port: int,
        client_id: str,
    ):
        self.broker    = broker
        self.port      = port
        self.connected = False
        self._callbacks: dict[str, Callable[[str, bytes], None]] = {}
        self._latency_log: list[float] = []

        self._client = mqtt.Client(
            client_id=client_id,
            protocol=mqtt.MQTTv5,
        )

        # ── TLS — authentification mutuelle ───────────────────────────────────
        self._client.tls_set(
            ca_certs=CA_CERT,
            certfile=CLIENT_CERT,
            keyfile=CLIENT_KEY,
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
        self._client.tls_insecure_set(False)   # hostname verification activée

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    # ── Connexion ─────────────────────────────────────────────────────────────

    def connect(self, timeout: float = 5.0):
        self._client.connect(self.broker, self.port, keepalive=60)
        self._client.loop_start()

        deadline = time.time() + timeout
        while not self.connected and time.time() < deadline:
            time.sleep(0.05)

        if not self.connected:
            raise ConnectionError(f"Impossible de joindre le broker {self.broker}:{self.port}")

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()

    # ── Publication / Abonnement ──────────────────────────────────────────────

    def publish(self, topic: str, payload: bytes, qos: int = MQTT_QOS) -> float:
        """Publie un message. Retourne l'horodatage d'émission."""
        ts = time.time()
        self._client.publish(topic, payload, qos=qos)
        return ts

    def subscribe(self, topic: str, callback: Callable[[str, bytes], None], qos: int = MQTT_QOS):
        self._callbacks[topic] = callback
        self._client.subscribe(topic, qos=qos)

    # ── Callbacks internes ────────────────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        self.connected = True
        print(f"[MQTT] Connecté au broker {self.broker}:{self.port} (TLS mTLS actif)")

    def _on_message(self, client, userdata, msg):
        for pattern, cb in self._callbacks.items():
            if mqtt.topic_matches_sub(pattern, msg.topic):
                cb(msg.topic, msg.payload)
