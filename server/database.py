"""Base de données SQLite asynchrone — VaultCall."""

import aiosqlite
import uuid
import random
from datetime import datetime
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "vaultcall.db")

AVATAR_COLORS = [
    "#7c3aed", "#2563eb", "#dc2626", "#16a34a",
    "#d97706", "#0891b2", "#be185d", "#059669",
]


class Database:
    def __init__(self):
        self.path = DB_PATH

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id           TEXT PRIMARY KEY,
                    username     TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    avatar_color TEXT NOT NULL,
                    created_at   TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS contacts (
                    id         TEXT PRIMARY KEY,
                    user_id    TEXT NOT NULL,
                    contact_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, contact_id)
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id          TEXT PRIMARY KEY,
                    sender_id   TEXT NOT NULL,
                    receiver_id TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    timestamp   TEXT NOT NULL,
                    is_read     INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS public_keys (
                    user_id    TEXT PRIMARY KEY,
                    public_key TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
            await db.commit()

    # ── Utilisateurs ──────────────────────────────────────────────────────────

    async def create_user(self, username: str, password_hash: str, display_name: str) -> dict:
        uid   = str(uuid.uuid4())
        color = random.choice(AVATAR_COLORS)
        now   = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO users VALUES (?,?,?,?,?,?)",
                (uid, username, password_hash, display_name, color, now),
            )
            await db.commit()
        return {"id": uid, "username": username, "display_name": display_name, "avatar_color": color}

    async def get_user_by_username(self, username: str):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE username=?", (username,)) as c:
                row = await c.fetchone()
                return dict(row) if row else None

    async def get_user_by_id(self, uid: str):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE id=?", (uid,)) as c:
                row = await c.fetchone()
                return dict(row) if row else None

    # ── Contacts ──────────────────────────────────────────────────────────────

    async def add_contact(self, user_id: str, contact_id: str):
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO contacts VALUES (?,?,?,?)",
                (str(uuid.uuid4()), user_id, contact_id, now),
            )
            await db.execute(
                "INSERT OR IGNORE INTO contacts VALUES (?,?,?,?)",
                (str(uuid.uuid4()), contact_id, user_id, now),
            )
            await db.commit()

    async def get_contacts(self, user_id: str) -> list:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT u.id, u.username, u.display_name, u.avatar_color
                FROM contacts c JOIN users u ON c.contact_id = u.id
                WHERE c.user_id = ? ORDER BY u.display_name
            """, (user_id,)) as c:
                return [dict(r) for r in await c.fetchall()]

    # ── Messages ──────────────────────────────────────────────────────────────

    async def save_message(self, sender_id: str, receiver_id: str, content: str) -> dict:
        mid = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO messages VALUES (?,?,?,?,?,0)",
                (mid, sender_id, receiver_id, content, now),
            )
            await db.commit()
        return {"id": mid, "sender_id": sender_id, "receiver_id": receiver_id,
                "content": content, "timestamp": now, "is_read": False}

    async def get_messages(self, user_id: str, other_id: str) -> list:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM messages
                WHERE (sender_id=? AND receiver_id=?)
                   OR (sender_id=? AND receiver_id=?)
                ORDER BY timestamp ASC LIMIT 200
            """, (user_id, other_id, other_id, user_id)) as c:
                return [dict(r) for r in await c.fetchall()]

    async def get_last_message(self, user_id: str, other_id: str):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM messages
                WHERE (sender_id=? AND receiver_id=?)
                   OR (sender_id=? AND receiver_id=?)
                ORDER BY timestamp DESC LIMIT 1
            """, (user_id, other_id, other_id, user_id)) as c:
                row = await c.fetchone()
                return dict(row) if row else None

    async def count_unread(self, user_id: str, sender_id: str) -> int:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM messages WHERE receiver_id=? AND sender_id=? AND is_read=0",
                (user_id, sender_id),
            ) as c:
                row = await c.fetchone()
                return row[0] if row else 0

    async def mark_read(self, user_id: str, sender_id: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE messages SET is_read=1 WHERE receiver_id=? AND sender_id=?",
                (user_id, sender_id),
            )
            await db.commit()

    # ── Clés publiques ────────────────────────────────────────────────────────

    async def save_public_key(self, user_id: str, public_key: str):
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO public_keys VALUES (?,?,?)",
                (user_id, public_key, now),
            )
            await db.commit()

    async def get_public_key(self, user_id: str):
        async with aiosqlite.connect(self.path) as db:
            async with db.execute("SELECT public_key FROM public_keys WHERE user_id=?", (user_id,)) as c:
                row = await c.fetchone()
                return row[0] if row else None
