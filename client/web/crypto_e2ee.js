/**
 * E2EECrypto — Chiffrement de bout en bout côté navigateur
 *
 * Algorithmes :
 *   • Échange de clés : ECDH P-256 (équivalent de X25519 côté Python)
 *   • Chiffrement     : AES-256-GCM (Web Crypto API — accéléré matériellement)
 *
 * La clé privée ne quitte JAMAIS le navigateur.
 * Seule la clé publique est transmise au serveur pour relai.
 */
class E2EECrypto {
  constructor() {
    this._myKeyPair   = null;           // {privateKey, publicKey}
    this._sessionKeys = {};             // {contact_id: CryptoKey}
  }

  // ── Génération de la paire de clés ─────────────────────────────────────────

  async init() {
    this._myKeyPair = await crypto.subtle.generateKey(
      { name: "ECDH", namedCurve: "P-256" },
      true,                              // exportable pour envoi au serveur
      ["deriveKey", "deriveBits"],
    );
    return this;
  }

  async exportPublicKey() {
    const raw = await crypto.subtle.exportKey("raw", this._myKeyPair.publicKey);
    return btoa(String.fromCharCode(...new Uint8Array(raw)));
  }

  // ── Dérivation de clé de session ───────────────────────────────────────────

  async _importPeerKey(b64) {
    const raw = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    return crypto.subtle.importKey(
      "raw", raw,
      { name: "ECDH", namedCurve: "P-256" },
      false, [],
    );
  }

  async deriveSessionKey(contactId, peerPublicKeyB64) {
    const peerKey = await this._importPeerKey(peerPublicKeyB64);
    const sessionKey = await crypto.subtle.deriveKey(
      { name: "ECDH", public: peerKey },
      this._myKeyPair.privateKey,
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"],
    );
    this._sessionKeys[contactId] = sessionKey;
    return sessionKey;
  }

  hasSessionKey(contactId) {
    return !!this._sessionKeys[contactId];
  }

  // ── Chiffrement ────────────────────────────────────────────────────────────

  async encrypt(contactId, plaintext) {
    const key = this._sessionKeys[contactId];
    if (!key) throw new Error("Pas de clé de session pour " + contactId);

    const iv       = crypto.getRandomValues(new Uint8Array(12));
    const encoded  = new TextEncoder().encode(plaintext);
    const cipher   = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, encoded);

    return JSON.stringify({
      iv: btoa(String.fromCharCode(...iv)),
      ct: btoa(String.fromCharCode(...new Uint8Array(cipher))),
    });
  }

  // ── Déchiffrement ──────────────────────────────────────────────────────────

  async decrypt(contactId, payload) {
    const key = this._sessionKeys[contactId];
    if (!key) return "[🔒 Clé de session non disponible]";

    try {
      const { iv, ct } = JSON.parse(payload);
      const ivBytes    = Uint8Array.from(atob(iv), c => c.charCodeAt(0));
      const ctBytes    = Uint8Array.from(atob(ct), c => c.charCodeAt(0));
      const plain      = await crypto.subtle.decrypt({ name: "AES-GCM", iv: ivBytes }, key, ctBytes);
      return new TextDecoder().decode(plain);
    } catch {
      return "[🔒 Message chiffré — clé introuvable]";
    }
  }
}

const e2ee = new E2EECrypto();
