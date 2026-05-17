/**
 * VaultCallWebRTC — Appels audio P2P via WebRTC
 *
 * Le chiffrement de la voix est assuré par DTLS-SRTP (intégré dans WebRTC).
 * La signalisation (offre/réponse/ICE) transite par le WebSocket chiffré TLS.
 *
 * Flux :
 *   Appelant : getUserMedia → createOffer → setLocalDesc → envoie offer via WS
 *   Appelé   : getUserMedia → setRemoteDesc → createAnswer → setLocalDesc → envoie answer
 *   Les deux : échangent les candidats ICE pour la traversée NAT
 */
class VaultCallWebRTC {
  constructor(sendSignal) {
    this._sendSignal  = sendSignal;   // fonction(data) → envoie via WebSocket
    this._pc          = null;
    this._localStream = null;
    this._muted       = false;
    this.onRemoteStream = null;       // callback(MediaStream)
    this.onCallEnded    = null;       // callback()
    this._peerId = null;

    this._iceConfig = {
      iceServers: [
        { urls: "stun:stun.l.google.com:19302" },
        { urls: "stun:stun1.l.google.com:19302" },
      ],
    };
  }

  // ── Appelant ───────────────────────────────────────────────────────────────

  async startCall(peerId) {
    this._peerId = peerId;
    this._localStream = await this._getMedia();
    this._pc = this._createPC(peerId);
    this._localStream.getTracks().forEach(t => this._pc.addTrack(t, this._localStream));

    const offer = await this._pc.createOffer({ offerToReceiveAudio: true });
    await this._pc.setLocalDescription(offer);
    this._sendSignal({ type: "webrtc_offer", to: peerId, offer });
  }

  // ── Appelé ─────────────────────────────────────────────────────────────────

  async handleOffer(peerId, offer) {
    this._peerId = peerId;
    this._localStream = await this._getMedia();
    this._pc = this._createPC(peerId);
    this._localStream.getTracks().forEach(t => this._pc.addTrack(t, this._localStream));

    await this._pc.setRemoteDescription(new RTCSessionDescription(offer));
    const answer = await this._pc.createAnswer();
    await this._pc.setLocalDescription(answer);
    this._sendSignal({ type: "webrtc_answer", to: peerId, answer });
  }

  async handleAnswer(answer) {
    if (this._pc) {
      await this._pc.setRemoteDescription(new RTCSessionDescription(answer));
    }
  }

  async handleIce(candidate) {
    if (this._pc && candidate) {
      try { await this._pc.addIceCandidate(new RTCIceCandidate(candidate)); }
      catch { /* ICE trickling — ignorer les erreurs bénignes */ }
    }
  }

  // ── Contrôles ──────────────────────────────────────────────────────────────

  toggleMute() {
    if (!this._localStream) return false;
    const track = this._localStream.getAudioTracks()[0];
    if (!track) return false;
    this._muted = !this._muted;
    track.enabled = !this._muted;
    return this._muted;
  }

  endCall() {
    if (this._pc)          { this._pc.close(); this._pc = null; }
    if (this._localStream) { this._localStream.getTracks().forEach(t => t.stop()); this._localStream = null; }
    this._peerId = null;
    this._muted  = false;
  }

  // ── Privé ──────────────────────────────────────────────────────────────────

  async _getMedia() {
    return navigator.mediaDevices.getUserMedia({ audio: true, video: false });
  }

  _createPC(peerId) {
    const pc = new RTCPeerConnection(this._iceConfig);

    pc.onicecandidate = e => {
      if (e.candidate) {
        this._sendSignal({ type: "webrtc_ice", to: peerId, candidate: e.candidate });
      }
    };

    pc.ontrack = e => {
      if (this.onRemoteStream) this.onRemoteStream(e.streams[0]);
    };

    pc.onconnectionstatechange = () => {
      if (["disconnected", "failed", "closed"].includes(pc.connectionState)) {
        if (this.onCallEnded) this.onCallEnded();
      }
    };

    return pc;
  }
}
