"""
System event log model for tracking admin-level operations.
"""
from app import db
from app.utils.timezone import now_eastern


class SystemEventLog(db.Model):
    """Persistent log for system-level admin operations."""
    __tablename__ = 'system_event_logs'

    id               = db.Column(db.Integer,       primary_key=True)
    event_type       = db.Column(db.String(100),   nullable=False, index=True)
    status           = db.Column(db.String(20),    nullable=False)
    log_text         = db.Column(db.Text,          nullable=True)
    started_by       = db.Column(db.String(200),   nullable=True)
    started_at       = db.Column(db.DateTime,      nullable=False, default=now_eastern, index=True)
    ended_at         = db.Column(db.DateTime,      nullable=True)
    duration_seconds = db.Column(db.Float,         nullable=True)

    def __repr__(self):
        return f'<SystemEventLog {self.event_type} [{self.status}] by {self.started_by}>'

    def to_dict(self):
        return {
            'id':               self.id,
            'event_type':       self.event_type,
            'status':           self.status,
            'log_text':         self.log_text,
            'started_by':       self.started_by,
            'started_at':       self.started_at.isoformat() if self.started_at else None,
            'ended_at':         self.ended_at.isoformat()   if self.ended_at   else None,
            'duration_seconds': self.duration_seconds,
        }
