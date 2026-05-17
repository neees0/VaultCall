/**
 * E2EECrypto — Chiffrement de bout en bout côté navigateur
 *
 * Algorithmes :
 *   • Échange de clés : ECDH P-256
 *   • Chiffrement     : AES-256-GCM
 *
 * La paire de clés est persistée dans sessionStorage pour survivre
 * aux rechargements de page (même session navigateur).
 */
class E2EECrypto {
  constructor() {
    this._myKeyPair   = null;
    this._sessionKeys = {};
  }

  // ── Génération / restauration de la paire de clés ─────────────────────────

  async init() {
    // Essaie de restaurer la paire depuis sessionStorage
    const stored = sessionStorage.getItem("vc_keypair");
    if (stored) {
      try {
        const { pub, priv } = JSON.parse(stored);
        const pubBytes  = Uint8Array.from(atob(pub),  c => c.charCodeAt(0));
        const privBytes = Uint8Array.from(atob(priv), c => c.charCodeAt(0));

        const publicKey = await crypto.subtle.importKey(
          "raw", pubBytes,
          { name: "ECDH", namedCurve: "P-256" },
          true, [],
        );
        const privateKey = await crypto.subtle.importKey(
          "pkcs8", privBytes,
          { name: "ECDH", namedCurve: "P-256" },
          true, ["deriveKey", "deriveBits"],
        );
        this._myKeyPair = { publicKey, privateKey };
        return this;
      } catch { /* clé stockée corrompue → on en génère une nouvelle */ }
    }

    // Génère une nouvelle paire et la sauvegarde
    this._myKeyPair = await crypto.subtle.generateKey(
      { name: "ECDH", namedCurve: "P-256" },
      true,
      ["deriveKey", "deriveBits"],
    );
    await this._persist();
    return this;
  }

  async _persist() {
    const pubRaw   = await crypto.subtle.exportKey("raw",   this._myKeyPair.publicKey);
    const privPkcs = await crypto.subtle.exportKey("pkcs8", this._myKeyPair.privateKey);
    sessionStorage.setItem("vc_keypair", JSON.stringify({
      pub:  btoa(String.fromCharCode(...new Uint8Array(pubRaw))),
      priv: btoa(String.fromCharCode(...new Uint8Array(privPkcs))),
    }));
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

    const iv      = crypto.getRandomValues(new Uint8Array(12));
    const encoded = new TextEncoder().encode(plaintext);
    const cipher  = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, encoded);

    return JSON.stringify({
      iv: btoa(String.fromCharCode(...iv)),
      ct: btoa(String.fromCharCode(...new Uint8Array(cipher))),
    });
  }

  // ── Déchiffrement ──────────────────────────────────────────────────────────

  async decrypt(contactId, payload) {
    const key = this._sessionKeys[contactId];
    if (!key) return null;   // null = clé pas encore disponible

    try {
      const { iv, ct } = JSON.parse(payload);
      const ivBytes    = Uint8Array.from(atob(iv), c => c.charCodeAt(0));
      const ctBytes    = Uint8Array.from(atob(ct), c => c.charCodeAt(0));
      const plain      = await crypto.subtle.decrypt({ name: "AES-GCM", iv: ivBytes }, key, ctBytes);
      return new TextDecoder().decode(plain);
    } catch {
      return null;
    }
  }

  // Réinitialise la paire de clés (nouvelle session)
  reset() {
    sessionStorage.removeItem("vc_keypair");
    this._myKeyPair   = null;
    this._sessionKeys = {};
  }
}

const e2ee = new E2EECrypto();
