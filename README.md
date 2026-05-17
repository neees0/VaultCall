# VaultCall — Communication Audio Chiffrée E2EE

**Projet de fin d'études M2 — USTHB**  
Étudiantes : MOSTEFAOUI Ines Sarra & KASSAB Nesrine  
Encadreur : Pr A. SERIR

---

## Vue d'ensemble

VaultCall est un prototype d'application VoIP avec chiffrement de **bout en bout (E2EE)** sur MQTT/TLS.  
Le contenu audio ne peut être déchiffré que par les deux pairs — même si le broker MQTT est compromis.

```
Micro → [AES-GCM/ChaCha20] → MQTT/TLS(mTLS) → [Déchiffrement] → Haut-parleur
         ↑                                        ↑
         └────── Clé session X25519+HKDF ─────────┘
```

---

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Échange de clés | X25519 (ECDH) + HKDF-SHA256 |
| Chiffrement audio | AES-256-GCM / ChaCha20-Poly1305 |
| Transport | MQTT v5 sur TLS 1.2+ |
| Authentification mutuelle | mTLS (certificats client + serveur) |
| Capture/lecture audio | PyAudio (PCM 16 bits, 16 kHz) |
| Analyse QoS/QoE | Latence, gigue, perte de paquets, SNR |

---

## Structure du projet

```
VaultCall/
├── main.py               ← Point d'entrée principal
├── demo_loopback.py      ← Test sans micro ni broker
├── generate_certs.py     ← Génération des certificats TLS
├── mosquitto.conf        ← Configuration du broker Mosquitto
├── config.py             ← Paramètres centralisés
├── requirements.txt
│
├── crypto/
│   ├── key_exchange.py   ← X25519 + HKDF
│   └── symmetric.py      ← AES-GCM / ChaCha20-Poly1305
│
├── audio/
│   └── audio_handler.py  ← Capture micro + lecture haut-parleur
│
├── network/
│   └── mqtt_client.py    ← MQTT sécurisé (mTLS)
│
├── analysis/
│   └── metrics.py        ← Latence, gigue, perte, SNR, RMS
│
├── certs/                ← Certificats générés (git-ignoré)
└── tests/
    ├── test_crypto.py
    └── test_metrics.py
```

---

## Installation

```bash
pip install -r requirements.txt
```

Installer Mosquitto (broker MQTT) : https://mosquitto.org/download/

---

## Démarrage rapide

### 1. Générer les certificats TLS
```bash
python generate_certs.py
```

### 2. Démarrer le broker Mosquitto
```bash
mosquitto -c mosquitto.conf -v
```

### 3. Lancer la démo loopback (sans micro)
```bash
python demo_loopback.py
```

### 4. Appel réel (deux terminaux)
```bash
# Terminal 1 — Appelant
python main.py caller --session test001 --cipher AES-GCM

# Terminal 2 — Appelé
python main.py callee --session test001 --cipher AES-GCM
```

### 5. Exécuter les tests
```bash
python -m pytest tests/ -v
```

---

## Protocole de sécurité

### Échange de clés
1. Chaque pair génère une paire éphémère **X25519**.
2. Les clés publiques s'échangent via le canal de signalisation MQTT (chiffré TLS).
3. **HKDF-SHA256** dérive une clé de session 256 bits à partir du secret Diffie-Hellman.

### Format des paquets audio
```
┌──────────────┬──────────┬───────────────┬─────────────────────────┐
│  Nonce (12B) │ Seq (4B) │ Timestamp (8B)│ Ciphertext + GCM Tag    │
└──────────────┴──────────┴───────────────┴─────────────────────────┘
          ← AAD (authentifié, non chiffré) →
```
- **Nonce** : aléatoire (96 bits) — unicité garantie.
- **AAD** (Seq + Timestamp) : authentifié mais non chiffré — détection des attaques par rejeu.
- **Tag GCM** (128 bits) : intégrité + authenticité.

### Authentification mutuelle MQTT (mTLS)
- Broker Mosquitto exige un certificat client valide signé par la CA interne.
- Connexions non TLS refusées (port 1883 désactivé).

---

## Métriques analysées

| Métrique | Description |
|----------|-------------|
| Latence moy/P95 | Délai one-way mesuré via horodatage AAD |
| Gigue | Variation inter-paquets (RFC 3550) |
| Taux de perte | Détection par saut de numéro de séquence |
| Niveau RMS (dBFS) | Énergie instantanée du signal |
| SNR (dB) | Rapport signal/bruit (test loopback) |

---

## Mots-clés
`E2EE` · `VoIP` · `AES-GCM` · `ChaCha20-Poly1305` · `X25519` · `HKDF` · `MQTT` · `mTLS` · `SRTP` · `QoS`
