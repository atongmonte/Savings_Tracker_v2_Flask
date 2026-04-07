"""
File tracking model.
"""
from datetime import datetime
from app import db
from app.utils.timezone import now_eastern


class FileTracking(db.Model):
    """File attachments for initiatives."""
    __tablename__ = 'file_tracking'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign key to initiative
    initiative_id = db.Column(db.Integer, db.ForeignKey('initiatives.id'), nullable=False, index=True)
    initiative = db.relationship('Initiative', back_populates='files')
    
    # File details
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.BigInteger)  # Size in bytes
    file_type = db.Column(db.String(50))  # MIME type or extension
    
    # Upload details
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id])
    upload_time = db.Column(db.DateTime, default=now_eastern, nullable=False)
    
    # Soft delete
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    deleted_by = db.relationship('User', foreign_keys=[deleted_by_id])
    
    created_at = db.Column(db.DateTime, default=now_eastern)
    updated_at = db.Column(db.DateTime, default=now_eastern, onupdate=now_eastern)
    
    def __repr__(self):
        return f'<FileTracking {self.file_name}>'
    
    def to_dict(self):
        """Convert file tracking to dictionary."""
        return {
            'id': self.id,
            'initiative_id': self.initiative_id,
            'file_name': self.file_name,
            'file_size': self.file_size,
            'file_type': self.file_type,
            'uploaded_by': self.uploaded_by.to_dict() if self.uploaded_by else None,
            'upload_time': self.upload_time.isoformat() if self.upload_time else None,
            'is_deleted': self.is_deleted
        }
