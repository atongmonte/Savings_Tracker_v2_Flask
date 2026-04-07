"""
Audit log model for tracking all changes.
"""
from datetime import datetime
from app import db
import json
from app.utils.timezone import now_eastern


class AuditLog(db.Model):
    """Audit trail for all initiative changes."""
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Initiative reference
    initiative_id = db.Column(db.Integer, db.ForeignKey('initiatives.id'), nullable=False, index=True)
    initiative = db.relationship('Initiative', back_populates='audit_logs')
    
    # Action details
    action = db.Column(db.String(50), nullable=False)  # CREATE, UPDATE, DELETE, APPROVE, REJECT
    table_name = db.Column(db.String(100))  # Which table was affected
    record_id = db.Column(db.Integer)  # ID of the affected record
    
    # User who performed the action
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('User')
    
    # Changes
    old_values = db.Column(db.Text)  # JSON string of old values
    new_values = db.Column(db.Text)  # JSON string of new values
    
    # Context
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(500))
    
    # Timestamp
    created_at = db.Column(db.DateTime, default=now_eastern, nullable=False, index=True)
    
    def __repr__(self):
        return f'<AuditLog {self.action} Initiative:{self.initiative_id}>'
    
    def set_old_values(self, values_dict):
        """Set old values as JSON string."""
        self.old_values = json.dumps(values_dict, default=str)
    
    def set_new_values(self, values_dict):
        """Set new values as JSON string."""
        self.new_values = json.dumps(values_dict, default=str)
    
    def get_old_values(self):
        """Get old values as dictionary."""
        return json.loads(self.old_values) if self.old_values else {}
    
    def get_new_values(self):
        """Get new values as dictionary."""
        return json.loads(self.new_values) if self.new_values else {}
    
    def to_dict(self):
        """Convert audit log to dictionary."""
        return {
            'id': self.id,
            'initiative_id': self.initiative_id,
            'action': self.action,
            'table_name': self.table_name,
            'record_id': self.record_id,
            'user': self.user.to_dict() if self.user else None,
            'old_values': self.get_old_values(),
            'new_values': self.get_new_values(),
            'ip_address': self.ip_address,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
