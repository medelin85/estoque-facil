"""Persistência SQLite com chaves estrangeiras e conexões por requisição."""
import sqlite3
from pathlib import Path
from flask import current_app, g

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(
 id INTEGER PRIMARY KEY, login TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN(0,1)), token TEXT,
 last_seen REAL NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0,
 locked_until REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS products(
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, unit TEXT NOT NULL CHECK(unit IN('un','kg')),
 minimum INTEGER NOT NULL DEFAULT 0 CHECK(minimum>=0));
CREATE TABLE IF NOT EXISTS lots(
 id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
 code TEXT NOT NULL, expiry TEXT NOT NULL, UNIQUE(product_id,code));
CREATE TABLE IF NOT EXISTS movements(
 id INTEGER PRIMARY KEY, lot_id INTEGER NOT NULL REFERENCES lots(id),
 user_id INTEGER NOT NULL REFERENCES users(id),
 kind TEXT NOT NULL CHECK(kind IN('entrada','saida')),
 quantity INTEGER NOT NULL CHECK(quantity>0), reason TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_movements_lot ON movements(lot_id);
CREATE INDEX IF NOT EXISTS idx_lots_expiry ON lots(expiry);
'''

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'], timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db

def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    Path(current_app.config['DATABASE']).parent.mkdir(parents=True, exist_ok=True)
    get_db().executescript(SCHEMA)
