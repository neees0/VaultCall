/**
 * VaultCall — Application principale
 * Gère : authentification, contacts, messages E2EE, appels WebRTC, WebSocket.
 */

const API  = "";          // même origin que le serveur FastAPI
// wss:// sur HTTPS (Render/production), ws:// sur HTTP (local)
const WS_BASE = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;

// ── État global ────────────────────────────────────────────────────────────────
const S = {
  user:        null,
  token:       null,
  contacts:    [],
  activeChat:  null,   // contact courant
  messages:    {},     // {contact_id: [...]}
  onlineUsers: new Set(),
  ws:          null,
  webrtc:      null,
  callState:   null,   // {type:"outgoing"|"incoming", with: contact}
  callTimer:   null,
  callSeconds: 0,
  typingTimer: null,
};

// ══════════════════════════════════════════════════════════════════════════════
// INITIALISATION
// ══════════════════════════════════════════════════════════════════════════════
window.addEventListener("DOMContentLoaded", async () => {
  await e2ee.init();

  const token = localStorage.getItem("vc_token");
  const user  = localStorage.getItem("vc_user");
  if (token && user) {
    S.token = token;
    S.user  = JSON.parse(user);
    await enterApp();
  }
});

// ══════════════════════════════════════════════════════════════════════════════
// AUTH
// ══════════════════════════════════════════════════════════════════════════════
function switchTab(tab) {
  document.getElementById("login-form").classList.toggle("hidden", tab !== "login");
  document.getElementById("register-form").classList.toggle("hidden", tab !== "register");
  document.getElementById("tab-login").classList.toggle("active", tab === "login");
  document.getElementById("tab-register").classList.toggle("active", tab === "register");
}

document.getElementById("login-form").addEventListener("submit", async e => {
  e.preventDefault();
  const btn = document.getElementById("login-btn");
  btn.disabled = true; btn.textContent = "Connexion…";
  const err = document.getElementById("login-error");
  err.classList.remove("show");

  try {
    const res = await apiPost("/api/login", {
      username: document.getElementById("login-username").value.trim(),
      password: document.getElementById("login-password").value,
    });
    S.token = res.token;
    S.user  = res.user;
    localStorage.setItem("vc_token", res.token);
    localStorage.setItem("vc_user",  JSON.stringify(res.user));
    await enterApp();
  } catch (ex) {
    err.textContent = ex.message;
    err.classList.add("show");
  } finally {
    btn.disabled = false; btn.textContent = "Se connecter";
  }
});

document.getElementById("register-form").addEventListener("submit", async e => {
  e.preventDefault();
  const btn = document.getElementById("register-btn");
  btn.disabled = true; btn.textContent = "Création…";
  const err = document.getElementById("register-error");
  err.classList.remove("show");

  try {
    const res = await apiPost("/api/register", {
      username:     document.getElementById("reg-username").value.trim(),
      password:     document.getElementById("reg-password").value,
      display_name: document.getElementById("reg-display").value.trim(),
    });
    S.token = res.token;
    S.user  = res.user;
    localStorage.setItem("vc_token", res.token);
    localStorage.setItem("vc_user",  JSON.stringify(res.user));
    await enterApp();
  } catch (ex) {
    err.textContent = ex.message;
    err.classList.add("show");
  } finally {
    btn.disabled = false; btn.textContent = "Créer mon compte";
  }
});

function logout() {
  S.token = null; S.user = null;
  localStorage.removeItem("vc_token");
  localStorage.removeItem("vc_user");
  if (S.ws) S.ws.close();
  document.getElementById("app").classList.add("hidden");
  document.getElementById("auth-screen").classList.remove("hidden");
}

// ══════════════════════════════════════════════════════════════════════════════
// ENTER APP
// ══════════════════════════════════════════════════════════════════════════════
async function enterApp() {
  document.getElementById("auth-screen").classList.add("hidden");
  document.getElementById("app").classList.remove("hidden");

  // Afficher le profil dans la sidebar
  const av = document.getElementById("me-avatar");
  av.textContent = initials(S.user.display_name);
  av.style.background = S.user.avatar_color;
  document.getElementById("me-name").textContent = S.user.display_name;

  // Publier la clé publique ECDH
  const pubKey = await e2ee.exportPublicKey();
  await apiPost("/api/public_key", { public_key: pubKey });

  // Charger contacts + connecter WS
  await loadContacts();
  connectWebSocket();
}

// ══════════════════════════════════════════════════════════════════════════════
// CONTACTS
// ══════════════════════════════════════════════════════════════════════════════
async function loadContacts() {
  const res = await apiGet("/api/contacts");
  S.contacts = res.contacts;
  renderContacts(S.contacts);
}

function renderContacts(list) {
  const el = document.getElementById("contacts-list");
  if (!list.length) {
    el.innerHTML = `<div class="empty-contacts"><div class="icon">💬</div><p>Aucun contact.<br>Cliquez sur + pour en ajouter.</p></div>`;
    return;
  }
  el.innerHTML = list.map(c => `
    <div class="contact-item ${S.activeChat?.id === c.id ? 'active' : ''}" onclick="openChat('${c.id}')">
      <div class="avatar" style="background:${c.avatar_color}">${initials(c.display_name)}</div>
      ${S.onlineUsers.has(c.id) ? '<div class="online-dot"></div>' : ''}
      <div class="contact-info">
        <div class="contact-name">
          ${esc(c.display_name)}
          <span class="time">${c.last_message ? relativeTime(c.last_message.timestamp) : ''}</span>
        </div>
        <div class="contact-preview">
          <span class="text">${c.last_message ? '🔒 Message chiffré' : 'Démarrer la conversation'}</span>
          ${c.unread_count > 0 ? `<span class="badge">${c.unread_count}</span>` : ''}
        </div>
      </div>
    </div>
  `).join('');
}

function filterContacts(q) {
  const filtered = S.contacts.filter(c =>
    c.display_name.toLowerCase().includes(q.toLowerCase()) ||
    c.username.toLowerCase().includes(q.toLowerCase())
  );
  renderContacts(filtered);
}

// ── Ajout de contact ──────────────────────────────────────────────────────────
function openAddContact()  { document.getElementById("add-modal").classList.remove("hidden"); document.getElementById("add-username").focus(); }
function closeAddContact() { document.getElementById("add-modal").classList.add("hidden"); document.getElementById("add-error").style.display = "none"; document.getElementById("add-username").value = ""; }

async function confirmAddContact() {
  const username = document.getElementById("add-username").value.trim();
  const errEl    = document.getElementById("add-error");
  errEl.style.display = "none";
  if (!username) return;
  try {
    await apiPost("/api/contacts/add", { username });
    closeAddContact();
    await loadContacts();
    toast("Contact ajouté ✓", "success");
  } catch (ex) {
    errEl.textContent   = ex.message;
    errEl.style.display = "block";
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// CHAT
// ══════════════════════════════════════════════════════════════════════════════
async function openChat(contactId) {
  const contact = S.contacts.find(c => c.id === contactId);
  if (!contact) return;
  S.activeChat = contact;

  // UI header
  const av = document.getElementById("chat-avatar");
  av.textContent   = initials(contact.display_name);
  av.style.background = contact.avatar_color;
  document.getElementById("chat-name").textContent   = contact.display_name;
  document.getElementById("chat-status").textContent =
    S.onlineUsers.has(contactId) ? "🟢 en ligne" : "⚫ hors ligne";

  // Afficher la zone de chat
  document.getElementById("welcome-screen").classList.add("hidden");
  document.getElementById("chat-screen").classList.remove("hidden");

  // Marquer actif dans la liste
  document.querySelectorAll(".contact-item").forEach(el => el.classList.remove("active"));
  event?.currentTarget?.classList.add("active");

  // Clé de session E2EE
  if (!e2ee.hasSessionKey(contactId)) {
    try {
      const pkRes = await apiGet(`/api/public_key/${contactId}`);
      await e2ee.deriveSessionKey(contactId, pkRes.public_key);
    } catch {
      toast("Clé E2EE du contact indisponible", "error");
    }
  }

  // Charger les messages
  await loadMessages(contactId);

  document.getElementById("msg-input").focus();
}

async function loadMessages(contactId) {
  const res = await apiGet(`/api/messages/${contactId}`);
  S.messages[contactId] = res.messages;
  await renderMessages(contactId);

  // Rafraîchir les non-lus dans les contacts
  const c = S.contacts.find(c => c.id === contactId);
  if (c) c.unread_count = 0;
}

async function renderMessages(contactId) {
  const area = document.getElementById("messages-area");
  const msgs = S.messages[contactId] || [];
  area.innerHTML = "";

  let lastDate = null;
  for (const m of msgs) {
    const date = m.timestamp.substring(0, 10);
    if (date !== lastDate) {
      const sep = document.createElement("div");
      sep.className   = "msg-date-sep";
      sep.textContent = formatDate(m.timestamp);
      area.appendChild(sep);
      lastDate = date;
    }
    const out   = m.sender_id === S.user.id;
    const plain = await e2ee.decrypt(contactId, m.content);
    const wrap  = document.createElement("div");
    wrap.className = `msg-wrap ${out ? "out" : "in"}`;
    wrap.innerHTML = `
      <div class="bubble">
        ${esc(plain)}
        <span class="msg-time"><span class="lock-icon">🔒</span>${formatTime(m.timestamp)}</span>
      </div>`;
    area.appendChild(wrap);
  }
  area.scrollTop = area.scrollHeight;
}

async function sendMessage() {
  const input   = document.getElementById("msg-input");
  const text    = input.value.trim();
  if (!text || !S.activeChat) return;
  input.value = "";
  input.style.height = "";

  const contactId = S.activeChat.id;

  let encrypted;
  try {
    encrypted = await e2ee.encrypt(contactId, text);
  } catch {
    encrypted = JSON.stringify({ iv: "plain", ct: btoa(text) });
  }

  try {
    const res = await apiPost("/api/messages", {
      receiver_id: contactId,
      content:     encrypted,
    });
    if (!S.messages[contactId]) S.messages[contactId] = [];
    S.messages[contactId].push(res.message);
    await renderMessages(contactId);

    // Mettre à jour l'aperçu dans la sidebar
    const c = S.contacts.find(c => c.id === contactId);
    if (c) { c.last_message = res.message; renderContacts(S.contacts); }
  } catch {
    toast("Échec d'envoi du message", "error");
  }
}

function handleInputKey(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
  // Auto-resize textarea
  const ta = document.getElementById("msg-input");
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 120) + "px";
}

let _typingTimeout = null;
function handleTyping() {
  if (!S.ws || !S.activeChat) return;
  wsSend({ type: "typing", to: S.activeChat.id });
  clearTimeout(_typingTimeout);
  _typingTimeout = setTimeout(() => {
    document.getElementById("typing-indicator").textContent = "";
  }, 3000);
}

// ══════════════════════════════════════════════════════════════════════════════
// WEBSOCKET
// ══════════════════════════════════════════════════════════════════════════════
function connectWebSocket() {
  if (S.ws && S.ws.readyState < 2) S.ws.close();
  S.ws = new WebSocket(`${WS_BASE}/${S.token}`);

  S.ws.onopen  = () => console.log("[WS] Connecté");
  S.ws.onclose = () => { console.log("[WS] Déconnecté"); setTimeout(connectWebSocket, 3000); };
  S.ws.onerror = e => console.error("[WS]", e);
  S.ws.onmessage = e => handleWSMessage(JSON.parse(e.data));
}

function wsSend(data) {
  if (S.ws?.readyState === WebSocket.OPEN) S.ws.send(JSON.stringify(data));
}

async function handleWSMessage(data) {
  switch (data.type) {

    case "online_status":
      S.onlineUsers = new Set(data.online);
      renderContacts(S.contacts);
      if (S.activeChat) {
        document.getElementById("chat-status").textContent =
          S.onlineUsers.has(S.activeChat.id) ? "🟢 en ligne" : "⚫ hors ligne";
      }
      break;

    case "message": {
      const { sender_id, content, timestamp, id } = data;
      if (!S.messages[sender_id]) S.messages[sender_id] = [];
      S.messages[sender_id].push({ id, sender_id, receiver_id: S.user.id, content, timestamp });
      if (S.activeChat?.id === sender_id) {
        await renderMessages(sender_id);
      } else {
        // Badge non-lu
        const c = S.contacts.find(c => c.id === sender_id);
        if (c) { c.unread_count = (c.unread_count || 0) + 1; c.last_message = { content, timestamp }; }
        renderContacts(S.contacts);
        toast(`Nouveau message de ${S.contacts.find(c=>c.id===sender_id)?.display_name || sender_id}`, "info");
      }
      break;
    }

    case "typing":
      if (S.activeChat?.id === data.from) {
        document.getElementById("typing-indicator").textContent = "est en train d'écrire…";
        clearTimeout(_typingTimeout);
        _typingTimeout = setTimeout(() => {
          document.getElementById("typing-indicator").textContent = "";
        }, 3000);
      }
      break;

    case "call_request":
      handleCallRequest(data);
      break;

    case "call_accept":
      handleCallAccepted();
      break;

    case "call_reject":
      handleCallRejected();
      break;

    case "call_end":
      endCall();
      break;

    case "webrtc_offer":
      await handleWebRTCOffer(data);
      break;

    case "webrtc_answer":
      if (S.webrtc) await S.webrtc.handleAnswer(data.answer);
      break;

    case "webrtc_ice":
      if (S.webrtc) await S.webrtc.handleIce(data.candidate);
      break;
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// APPELS AUDIO (WebRTC)
// ══════════════════════════════════════════════════════════════════════════════
function initiateCall() {
  if (!S.activeChat) return;
  const contact = S.activeChat;

  S.callState = { type: "outgoing", with: contact };
  S.webrtc    = new VaultCallWebRTC(wsSend);
  S.webrtc.onRemoteStream = stream => {
    document.getElementById("remote-audio").srcObject = stream;
    startCallTimer();
    document.getElementById("call-overlay-status").textContent = "Appel chiffré en cours";
    document.getElementById("call-timer").style.display = "block";
  };
  S.webrtc.onCallEnded = endCall;

  // Afficher l'overlay appelant
  showCallOverlay(contact, "Appel en cours…");
  wsSend({ type: "call_request", to: contact.id });
  S.webrtc.startCall(contact.id);
}

function handleCallRequest(data) {
  const caller = S.contacts.find(c => c.id === data.from);
  if (!caller) return;

  document.getElementById("incoming-caller-name").textContent =
    `📞 ${caller.display_name} vous appelle…`;
  document.getElementById("incoming-call").classList.remove("hidden");
  S.callState = { type: "incoming", with: caller, data };
}

async function acceptCall() {
  document.getElementById("incoming-call").classList.add("hidden");
  const { with: caller } = S.callState;

  S.webrtc = new VaultCallWebRTC(wsSend);
  S.webrtc.onRemoteStream = stream => {
    document.getElementById("remote-audio").srcObject = stream;
    startCallTimer();
    document.getElementById("call-overlay-status").textContent = "Appel chiffré en cours";
    document.getElementById("call-timer").style.display = "block";
  };
  S.webrtc.onCallEnded = endCall;

  wsSend({ type: "call_accept", to: caller.id });
  showCallOverlay(caller, "Connexion…");
}

function handleCallAccepted() {
  document.getElementById("call-overlay-status").textContent = "Connexion…";
}

async function handleWebRTCOffer(data) {
  if (!S.webrtc || S.callState?.type !== "incoming") return;
  await S.webrtc.handleOffer(data.from, data.offer);
}

function handleCallRejected() {
  toast("Appel refusé", "error");
  _cleanupCall();
}

function rejectCall() {
  if (S.callState?.with) wsSend({ type: "call_reject", to: S.callState.with.id });
  document.getElementById("incoming-call").classList.add("hidden");
  S.callState = null;
}

function endCall() {
  if (S.callState?.with) wsSend({ type: "call_end", to: S.callState.with.id });
  _cleanupCall();
}

function _cleanupCall() {
  if (S.webrtc) { S.webrtc.endCall(); S.webrtc = null; }
  if (S.callTimer) { clearInterval(S.callTimer); S.callTimer = null; }
  S.callState = null;
  S.callSeconds = 0;
  document.getElementById("call-overlay").classList.add("hidden");
  document.getElementById("incoming-call").classList.add("hidden");
  document.getElementById("call-timer").style.display = "none";
  document.getElementById("mute-btn").className = "ctrl-btn mute";
}

function showCallOverlay(contact, status) {
  const av = document.getElementById("call-overlay-avatar");
  av.textContent      = initials(contact.display_name);
  av.style.background = contact.avatar_color;
  document.getElementById("call-overlay-name").textContent   = contact.display_name;
  document.getElementById("call-overlay-status").textContent = status;
  document.getElementById("call-overlay").classList.remove("hidden");
}

function toggleMute() {
  if (!S.webrtc) return;
  const muted = S.webrtc.toggleMute();
  const btn   = document.getElementById("mute-btn");
  btn.className   = muted ? "ctrl-btn muted" : "ctrl-btn mute";
  btn.innerHTML   = `${muted ? "🔇" : "🎤"}<span>${muted ? "Activé" : "Micro"}</span>`;
}

function startCallTimer() {
  S.callSeconds = 0;
  S.callTimer = setInterval(() => {
    S.callSeconds++;
    const m = String(Math.floor(S.callSeconds / 60)).padStart(2, "0");
    const s = String(S.callSeconds % 60).padStart(2, "0");
    document.getElementById("call-timer").textContent = `${m}:${s}`;
  }, 1000);
}

// ══════════════════════════════════════════════════════════════════════════════
// HELPERS API
// ══════════════════════════════════════════════════════════════════════════════
async function apiPost(path, body) {
  const res = await fetch(API + path, {
    method:  "POST",
    headers: {
      "Content-Type":  "application/json",
      ...(S.token ? { Authorization: `Bearer ${S.token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Erreur serveur");
  return data;
}

async function apiGet(path) {
  const res = await fetch(API + path, {
    headers: S.token ? { Authorization: `Bearer ${S.token}` } : {},
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Erreur serveur");
  return data;
}

// ══════════════════════════════════════════════════════════════════════════════
// UTILS
// ══════════════════════════════════════════════════════════════════════════════
function initials(name = "") {
  return name.split(" ").map(w => w[0]).join("").toUpperCase().slice(0, 2);
}

function esc(str = "") {
  return str.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/\n/g,"<br>");
}

function formatTime(ts) {
  return new Date(ts + "Z").toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

function formatDate(ts) {
  const d = new Date(ts + "Z");
  const today = new Date();
  if (d.toDateString() === today.toDateString()) return "Aujourd'hui";
  const yest = new Date(); yest.setDate(yest.getDate() - 1);
  if (d.toDateString() === yest.toDateString()) return "Hier";
  return d.toLocaleDateString("fr-FR");
}

function relativeTime(ts) {
  const diff = (Date.now() - new Date(ts + "Z").getTime()) / 1000;
  if (diff < 60)   return "maintenant";
  if (diff < 3600) return Math.floor(diff / 60) + "m";
  if (diff < 86400)return Math.floor(diff / 3600) + "h";
  return formatDate(ts);
}

let _toastTimer;
function toast(msg, type = "info") {
  const el = document.querySelector(".toast");
  if (el) el.remove();
  const t = document.createElement("div");
  t.className   = `toast ${type}`;
  t.textContent = msg;
  document.body.appendChild(t);
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => t.remove(), 3500);
}

// Fermer le modal add-contact sur Escape
document.addEventListener("keydown", e => {
  if (e.key === "Escape") closeAddContact();
});
document.getElementById("add-modal").addEventListener("click", e => {
  if (e.target === document.getElementById("add-modal")) closeAddContact();
});
document.getElementById("add-username").addEventListener("keydown", e => {
  if (e.key === "Enter") confirmAddContact();
});
