from datetime import datetime, timezone
from flask import current_app
from .db import get_db

def audit(event_type, message, payload=None, migration_id=None):
    db = get_db()
    db.execute("INSERT INTO audit_events (migration_id,event_type,message,payload,created_at) VALUES (?,?,?,?,?)",
               (migration_id, event_type, message, __import__('json').dumps(payload or {}, default=str), datetime.now(timezone.utc).isoformat()))
    db.commit()
