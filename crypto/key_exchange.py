"""
Échange de clés Diffie-Hellman sur courbe elliptique X25519 + dérivation HKDF.

Protocole :
    1. Chaque pair génère une paire de clés éphémère X25519.
    2. Les clés publiques s'échangent via le canal de signalisation MQTT (chiffré TLS).
    3. HKDF-SHA256 dérive la clé de session symétrique (256 bits) à partir du secret partagé.

Référence : RFC 7748 (X25519), RFC 5869 (HKDF).
"""

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization

from config import SESSION_KEY_LEN, HKDF_INFO


class KeyExchange:
    def __init__(self):
        self._private_key = X25519PrivateKey.generate()
        self.public_key   = self._private_key.public_key()

    # ── Sérialisation ─────────────────────────────────────────────────────────

    def get_public_bytes(self) -> bytes:
        """Retourne la clé publique brute (32 octets) à envoyer au pair."""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    # ── Dérivation de la clé de session ───────────────────────────────────────

    def derive_session_key(self, peer_public_bytes: bytes) -> bytes:
        """
        Effectue l'échange X25519 et dérive la clé de session via HKDF-SHA256.

        Args:
            peer_public_bytes: clé publique brute (32 octets) du pair.

        Returns:
            Clé symétrique de SESSION_KEY_LEN octets (256 bits).
        """
        peer_key     = X25519PublicKey.from_public_bytes(peer_public_bytes)
        shared_secret = self._private_key.exchange(peer_key)

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=SESSION_KEY_LEN,
            salt=None,
            info=HKDF_INFO,
        )
        return hkdf.derive(shared_secret)
