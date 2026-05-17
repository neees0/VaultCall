"""
VaultCall — Serveur FastAPI
    • API REST  : inscription, connexion, contacts, messages, clés publiques
    • WebSocket : messagerie temps réel + signalisation WebRTC (offre/réponse/ICE + appels)
    • Fichiers statiques : sert le client web depuis client/web/
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import Database

# ── Config ────────────────────────────────────────────────────────────────────
SECRET_KEY = "vaultcall-e2ee-secret-2026"
ALGORITHM  = "HS256"
TOKEN_DAYS = 7

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR  = os.path.join(BASE_DIR, "client", "web")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="VaultCall API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = Database()


# ── WebSocket Manager ─────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.active[user_id] = ws
        await self._broadcast_status()

    def disconnect(self, user_id: str):
        self.active.pop(user_id, None)

    async def send(self, user_id: str, data: dict):
        ws = self.active.get(user_id)
        if ws:
            try:
                await ws.send_text(json.dumps(data))
            except Exception:
                self.disconnect(user_id)

    async def _broadcast_status(self):
        online = list(self.active.keys())
        for ws in list(self.active.values()):
            try:
                await ws.send_text(json.dumps({"type": "online_status", "online": online}))
            except Exception:
                pass


manager = ConnectionManager()


# ── Auth helpers ──────────────────────────────────────────────────────────────
def make_token(user_id: str, username: str) -> str:
    return jwt.encode(
        {"sub": user_id, "username": username,
         "exp": datetime.utcnow() + timedelta(days=TOKEN_DAYS)},
        SECRET_KEY, algorithm=ALGORITHM,
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expiré")
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide")


async def current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Non authentifié")
    return decode_token(authorization.split(" ", 1)[1])


# ── Lifecycle ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    await db.init()
    print("✓ Base de données initialisée")
    print(f"✓ Fichiers web servis depuis : {WEB_DIR}")


# ── Static files ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
async def root():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


# ── Pydantic models ───────────────────────────────────────────────────────────
class RegisterReq(BaseModel):
    username: str
    password: str
    display_name: str

class LoginReq(BaseModel):
    username: str
    password: str

class AddContactReq(BaseModel):
    username: str

class SendMsgReq(BaseModel):
    receiver_id: str
    content: str          # JSON stringifié de {iv, ct} chiffré côté client

class PublicKeyReq(BaseModel):
    public_key: str


# ── Auth endpoints ────────────────────────────────────────────────────────────
@app.post("/api/register")
async def register(req: RegisterReq):
    if len(req.username) < 3:
        raise HTTPException(400, "Le nom d'utilisateur doit faire au moins 3 caractères")
    existing = await db.get_user_by_username(req.username)
    if existing:
        raise HTTPException(400, "Nom d'utilisateur déjà pris")
    pw_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    user    = await db.create_user(req.username, pw_hash, req.display_name)
    return {"token": make_token(user["id"], user["username"]), "user": user}


@app.post("/api/login")
async def login(req: LoginReq):
    user = await db.get_user_by_username(req.username)
    if not user or not bcrypt.checkpw(req.password.encode(), user["password_hash"].encode()):
        raise HTTPException(401, "Identifiants incorrects")
    safe = {k: v for k, v in user.items() if k != "password_hash"}
    return {"token": make_token(user["id"], user["username"]), "user": safe}


@app.get("/api/me")
async def me(payload: dict = Depends(current_user)):
    user = await db.get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")
    return {k: v for k, v in user.items() if k != "password_hash"}


# ── Contacts ──────────────────────────────────────────────────────────────────
@app.post("/api/contacts/add")
async def add_contact(req: AddContactReq, payload: dict = Depends(current_user)):
    me_id   = payload["sub"]
    contact = await db.get_user_by_username(req.username)
    if not contact:
        raise HTTPException(404, "Utilisateur introuvable")
    if contact["id"] == me_id:
        raise HTTPException(400, "Vous ne pouvez pas vous ajouter vous-même")
    await db.add_contact(me_id, contact["id"])
    safe = {k: v for k, v in contact.items() if k != "password_hash"}
    return {"contact": safe}


@app.get("/api/contacts")
async def get_contacts(payload: dict = Depends(current_user)):
    contacts = await db.get_contacts(payload["sub"])
    # Ajouter le dernier message et le nombre de non-lus
    for c in contacts:
        last = await db.get_last_message(payload["sub"], c["id"])
        c["last_message"]  = last
        c["unread_count"]  = await db.count_unread(payload["sub"], c["id"])
    return {"contacts": contacts}


# ── Messages ──────────────────────────────────────────────────────────────────
@app.get("/api/messages/{other_id}")
async def get_messages(other_id: str, payload: dict = Depends(current_user)):
    msgs = await db.get_messages(payload["sub"], other_id)
    await db.mark_read(payload["sub"], other_id)
    return {"messages": msgs}


@app.post("/api/messages")
async def send_message(req: SendMsgReq, payload: dict = Depends(current_user)):
    user_id = payload["sub"]
    msg = await db.save_message(user_id, req.receiver_id, req.content)

    # Notifier le destinataire via WebSocket (si connecté)
    await manager.send(req.receiver_id, {
        "type":      "message",
        "id":        msg["id"],
        "sender_id": user_id,
        "content":   req.content,
        "timestamp": msg["timestamp"],
    })
    return {"message": msg}


# ── Clés publiques (E2EE) ─────────────────────────────────────────────────────
@app.post("/api/public_key")
async def set_public_key(req: PublicKeyReq, payload: dict = Depends(current_user)):
    await db.save_public_key(payload["sub"], req.public_key)
    return {"status": "ok"}


@app.get("/api/public_key/{user_id}")
async def get_public_key(user_id: str):
    key = await db.get_public_key(user_id)
    if not key:
        raise HTTPException(404, "Clé publique non trouvée")
    return {"public_key": key}


# ── WebSocket (temps réel + signalisation WebRTC) ─────────────────────────────
RELAY_TYPES = {
    "webrtc_offer", "webrtc_answer", "webrtc_ice",
    "call_request", "call_accept", "call_reject", "call_end",
}

@app.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload["sub"]
    except Exception:
        await websocket.close(code=1008)
        return

    await manager.connect(user_id, websocket)
    try:
        while True:
            raw  = await websocket.receive_text()
            data = json.loads(raw)
            to   = data.get("to")

            if to and data.get("type") in RELAY_TYPES:
                await manager.send(to, {**data, "from": user_id})

            elif data.get("type") == "typing":
                if to:
                    await manager.send(to, {"type": "typing", "from": user_id})

    except WebSocketDisconnect:
        manager.disconnect(user_id)
        await manager._broadcast_status()


# ── Lancement direct ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
