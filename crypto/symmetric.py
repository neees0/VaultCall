"""
Chiffrement symétrique authentifié pour les trames audio VoIP.

Deux algorithmes supportés :
    • AES-256-GCM         — accéléré matériellement (AES-NI), standard SRTP.
    • ChaCha20-Poly1305   — performant sur CPU sans AES-NI (embarqué, mobile).

Format d'un paquet chiffré :
    ┌──────────────┬──────────┬───────────────┬─────────────────────────┐
    │  Nonce (12B) │ Seq (4B) │ Timestamp (8B)│ Ciphertext + Tag (16B)  │
    └──────────────┴──────────┴───────────────┴─────────────────────────┘
    Les champs Seq + Timestamp constituent l'AAD (Additional Authenticated Data)
    ce qui permet de détecter les attaques par rejeu et les altérations.

Référence : NIST SP 800-38D (AES-GCM), RFC 8439 (ChaCha20-Poly1305).
"""

import os
import struct
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305


_NONCE_LEN = 12   # 96 bits — recommandé par NIST pour AES-GCM
_AAD_LEN   = 12   # 4 (seq) + 8 (timestamp ms)


class AudioEncryptor:
    def __init__(self, key: bytes, cipher: str = "AES-GCM"):
        """
        Args:
            key:    clé symétrique 256 bits (32 octets).
            cipher: "AES-GCM" ou "ChaCha20-Poly1305".
        """
        self.cipher_name = cipher
        self.key         = key
        self._seq        = 0

        if cipher == "AES-GCM":
            self._cipher = AESGCM(key)
        elif cipher == "ChaCha20-Poly1305":
            self._cipher = ChaCha20Poly1305(key)
        else:
            raise ValueError(f"Cipher inconnu : {cipher}")

    # ── Chiffrement ───────────────────────────────────────────────────────────

    def encrypt(self, audio_data: bytes, timestamp: float | None = None) -> bytes:
        """
        Chiffre une trame audio.

        Args:
            audio_data: PCM brut (16 bits, mono).
            timestamp:  horodatage d'émission (time.time()). Généré si None.

        Returns:
            Paquet chiffré prêt à être publié sur MQTT.
        """
        if timestamp is None:
            timestamp = time.time()

        nonce = os.urandom(_NONCE_LEN)
        aad   = struct.pack(">IQ", self._seq, int(timestamp * 1000))

        ciphertext = self._cipher.encrypt(nonce, audio_data, aad)
        self._seq += 1

        return nonce + aad + ciphertext

    # ── Déchiffrement ─────────────────────────────────────────────────────────

    def decrypt(self, packet: bytes) -> tuple[bytes, int, float]:
        """
        Déchiffre un paquet reçu.

        Returns:
            (audio_pcm, numero_sequence, timestamp_emission)

        Raises:
            cryptography.exceptions.InvalidTag si le paquet est altéré/rejoué.
        """
        nonce      = packet[:_NONCE_LEN]
        aad        = packet[_NONCE_LEN: _NONCE_LEN + _AAD_LEN]
        ciphertext = packet[_NONCE_LEN + _AAD_LEN:]

        seq_num, ts_ms = struct.unpack(">IQ", aad)
        timestamp = ts_ms / 1000.0

        audio_pcm = self._cipher.decrypt(nonce, ciphertext, aad)
        return audio_pcm, seq_num, timestamp
