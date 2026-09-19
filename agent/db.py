import sqlite3, os
from flask import current_app, g

SCHEMA = '''
CREATE TABLE IF NOT EXISTS migrations (
 id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 total_source_rows INTEGER DEFAULT 0, canonical_rows INTEGER DEFAULT 0, success_count INTEGER DEFAULT 0,
 failed_count INTEGER DEFAULT 0, rollback_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS records (
 id INTEGER PRIMARY KEY AUTOINCREMENT, migration_id TEXT, employee_id TEXT, payload TEXT, status TEXT,
 attempts INTEGER DEFAULT 0, target_id TEXT, error TEXT, previous_payload TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS escalations (
 id INTEGER PRIMARY KEY AUTOINCREMENT, migration_id TEXT, kind TEXT, title TEXT, reason TEXT,
 options TEXT, evidence TEXT, status TEXT DEFAULT 'open', resolution TEXT, created_at TEXT, resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS audit_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, migration_id TEXT, event_type TEXT, message TEXT, payload TEXT, created_at TEXT
);
'''

def get_db():
    if 'db' not in g:
        os.makedirs(os.path.dirname(current_app.config['DB_PATH']), exist_ok=True)
        g.db = sqlite3.connect(current_app.config['DB_PATH'])
        g.db.row_factory = sqlite3.Row
    return g.db

def init_db(app):
    with app.app_context():
        db = get_db(); db.executescript(SCHEMA); db.commit()

def close_db(_=None):
    db = g.pop('db', None)
    if db: db.close()
