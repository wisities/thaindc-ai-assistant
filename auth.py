"""Authentication and session management for ThaiNDC AI Learning Assistant."""
import hashlib, os, secrets, sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from fastapi import Request, HTTPException, Depends

def hash_password(password: str) -> Tuple[str, str]:
    salt = os.urandom(16).hex()
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), 100000).hex()
    return pwd_hash, salt

def verify_password(password: str, pwd_hash: str, salt: str) -> bool:
    calc_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), 100000).hex()
    return secrets.compare_digest(calc_hash, pwd_hash)

def init_auth_tables(c: sqlite3.Connection):
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            display_name TEXT,
            created_at TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    # Check if lectures table has user_id and share_token columns
    cols = [r['name'] for r in c.execute('PRAGMA table_info(lectures)').fetchall()]
    if 'user_id' not in cols:
        c.execute('ALTER TABLE lectures ADD COLUMN user_id TEXT')
    if 'share_token' not in cols:
        c.execute('ALTER TABLE lectures ADD COLUMN share_token TEXT')

    # Check if users table has is_admin column
    user_cols = [r['name'] for r in c.execute('PRAGMA table_info(users)').fetchall()]
    if 'is_admin' not in user_cols:
        c.execute('ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0')

    # Ensure admin account exists with password 1234
    pwd_hash, salt = hash_password('1234')
    admin_row = c.execute('SELECT id FROM users WHERE username = ?', ('admin',)).fetchone()
    now_str = datetime.now(timezone.utc).isoformat()
    if not admin_row:
        c.execute('''
            INSERT INTO users (id, username, password_hash, salt, display_name, created_at, is_admin)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        ''', ('admin-system', 'admin', pwd_hash, salt, 'ผู้ดูแลระบบ (Admin)', now_str))
    else:
        c.execute('''
            UPDATE users SET password_hash = ?, salt = ?, is_admin = 1, display_name = ?
            WHERE username = ?
        ''', (pwd_hash, salt, 'ผู้ดูแลระบบ (Admin)', 'admin'))

def create_session(c: sqlite3.Connection, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=30)
    c.execute('INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)',
              (token, user_id, now.isoformat(), expires.isoformat()))
    return token

def get_user_by_token(c: sqlite3.Connection, token: str) -> Optional[dict]:
    if not token:
        return None
    now = datetime.now(timezone.utc).isoformat()
    row = c.execute('''
        SELECT u.id, u.username, u.display_name, u.is_admin, u.created_at, s.expires_at 
        FROM sessions s 
        JOIN users u ON s.user_id = u.id 
        WHERE s.token = ? AND s.expires_at > ?
    ''', (token, now)).fetchone()
    if not row:
        return None
    return dict(row)

def delete_session(c: sqlite3.Connection, token: str):
    if token:
        c.execute('DELETE FROM sessions WHERE token = ?', (token,))
