import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── MQTT ──────────────────────────────────────────────────────────────────────
MQTT_BROKER = "localhost"
MQTT_PORT   = 8883          # 8883 = TLS  |  1883 = non chiffré
MQTT_QOS    = 1

MQTT_AUDIO_TOPIC  = "vaultcall/audio/{session_id}"
MQTT_SIGNAL_TOPIC = "vaultcall/signal/{session_id}"

# ── TLS / PKI ─────────────────────────────────────────────────────────────────
CERTS_DIR   = os.path.join(BASE_DIR, "certs")
CA_CERT     = os.path.join(CERTS_DIR, "ca.crt")
CLIENT_CERT = os.path.join(CERTS_DIR, "client.crt")
CLIENT_KEY  = os.path.join(CERTS_DIR, "client.key")

# ── Audio ─────────────────────────────────────────────────────────────────────
SAMPLE_RATE    = 16000   # 16 kHz — bande téléphonique étendue
CHANNELS       = 1       # Mono
CHUNK_SIZE     = 1024    # ~64 ms par trame à 16 kHz
JITTER_BUF_MAX = 50      # taille max du tampon de gigue (paquets)

# ── Chiffrement ───────────────────────────────────────────────────────────────
DEFAULT_CIPHER  = "AES-GCM"          # alternative : "ChaCha20-Poly1305"
SESSION_KEY_LEN = 32                  # 256 bits
HKDF_INFO       = b"VaultCall-v1-SessionKey"
