"""
Tests unitaires — Module cryptographique VaultCall.

Couvre :
    • Échange de clés X25519 + HKDF (dérivation symétrique)
    • Chiffrement/déchiffrement AES-GCM et ChaCha20-Poly1305
    • Détection d'altération (tag invalide)
    • Numéro de séquence et horodatage embarqués dans l'AAD

Usage :
    python -m pytest tests/test_crypto.py -v
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from cryptography.exceptions import InvalidTag

from crypto.key_exchange import KeyExchange
from crypto.symmetric    import AudioEncryptor


# ── Échange de clés ───────────────────────────────────────────────────────────

class TestKeyExchange:

    def test_shared_secret_est_identique(self):
        """Les deux pairs doivent dériver la même clé de session."""
        kex_alice = KeyExchange()
        kex_bob   = KeyExchange()

        key_alice = kex_alice.derive_session_key(kex_bob.get_public_bytes())
        key_bob   = kex_bob.derive_session_key(kex_alice.get_public_bytes())

        assert key_alice == key_bob, "Les clés de session doivent être identiques"

    def test_cle_session_256_bits(self):
        kex_a = KeyExchange()
        kex_b = KeyExchange()
        key   = kex_a.derive_session_key(kex_b.get_public_bytes())
        assert len(key) == 32, "La clé doit faire 256 bits (32 octets)"

    def test_sessions_differentes(self):
        """Deux sessions distinctes doivent produire des clés différentes."""
        kex_a1, kex_b1 = KeyExchange(), KeyExchange()
        kex_a2, kex_b2 = KeyExchange(), KeyExchange()

        key1 = kex_a1.derive_session_key(kex_b1.get_public_bytes())
        key2 = kex_a2.derive_session_key(kex_b2.get_public_bytes())

        assert key1 != key2, "Des sessions différentes doivent donner des clés différentes"


# ── Chiffrement symétrique ────────────────────────────────────────────────────

SAMPLE_PCM = b"\x01\x02" * 512   # trame audio fictive (1024 octets)


@pytest.mark.parametrize("cipher", ["AES-GCM", "ChaCha20-Poly1305"])
class TestAudioEncryptor:

    def _fresh_key(self):
        kex_a, kex_b = KeyExchange(), KeyExchange()
        return kex_a.derive_session_key(kex_b.get_public_bytes())

    def test_chiffrement_dechiffrement(self, cipher):
        key = self._fresh_key()
        enc = AudioEncryptor(key, cipher)

        packet = enc.encrypt(SAMPLE_PCM)
        pcm, seq, ts = enc.decrypt(packet)

        assert pcm == SAMPLE_PCM, "Le déchiffrement doit restituer le PCM original"

    def test_sequence_croissante(self, cipher):
        key = self._fresh_key()
        enc = AudioEncryptor(key, cipher)

        seqs = []
        for _ in range(5):
            pkt = enc.encrypt(SAMPLE_PCM)
            _, s, _ = enc.decrypt(pkt)
            seqs.append(s)

        assert seqs == list(range(5)), "Les numéros de séquence doivent être croissants"

    def test_horodatage_correct(self, cipher):
        key = self._fresh_key()
        enc = AudioEncryptor(key, cipher)

        ts_avant = time.time()
        pkt = enc.encrypt(SAMPLE_PCM)
        ts_apres = time.time()
        _, _, ts_paquet = enc.decrypt(pkt)

        assert ts_avant <= ts_paquet <= ts_apres + 0.01

    def test_alteration_detectee(self, cipher):
        """Une modification du ciphertext doit lever InvalidTag."""
        key = self._fresh_key()
        enc = AudioEncryptor(key, cipher)

        pkt = bytearray(enc.encrypt(SAMPLE_PCM))
        pkt[-1] ^= 0xFF   # flip un bit dans le tag GCM

        with pytest.raises(InvalidTag):
            enc.decrypt(bytes(pkt))

    def test_nonce_unique(self, cipher):
        """Chaque paquet doit avoir un nonce différent."""
        key = self._fresh_key()
        enc = AudioEncryptor(key, cipher)

        nonces = {enc.encrypt(SAMPLE_PCM)[:12] for _ in range(100)}
        assert len(nonces) == 100, "Les nonces doivent être uniques"

    def test_cipher_inconnu(self, cipher):
        key = self._fresh_key()
        with pytest.raises(ValueError):
            AudioEncryptor(key, "DES")
