"""
Initiative master model.
"""
from datetime import datetime
from app import db
from app.utils.timezone import now_eastern


class Initiative(db.Model):
    """Master initiative table."""
    __tablename__ = 'initiatives'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Initiative details
    initiative_type = db.Column(
        db.String(50),
        nullable=False,
        index=True
    )  # Cost Savings, Rebate, Cost Avoidance
    description = db.Column(db.Text)
    wave_id = db.Column(db.String(50))
    
    # Status
    status = db.Column(
        db.String(50),
        nullable=False,
        default='Pending Review',
        index=True
    )  # Pending Review, Approved, Rejected
    
    # User relationships
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    owner = db.relationship('User', foreign_keys=[owner_id], back_populates='owned_initiatives')
    
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    creator = db.relationship('User', foreign_keys=[created_by_id], back_populates='created_initiatives')
    
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewer = db.relationship('User', foreign_keys=[reviewed_by_id], back_populates='reviewed_initiatives')
    
    # Review details
    review_comments = db.Column(db.Text)
    review_date = db.Column(db.DateTime)
    
    # Soft delete
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)
    deleted_at = db.Column(db.DateTime)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=now_eastern, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_eastern, onupdate=now_eastern, nullable=False)
    
    # Relationships
    cost_savings = db.relationship('CostSavings', back_populates='initiative', uselist=False, cascade='all, delete-orphan')
    rebate = db.relationship('Rebate', back_populates='initiative', uselist=False, cascade='all, delete-orphan')
    cost_avoidance = db.relationship('CostAvoidance', back_populates='initiative', uselist=False, cascade='all, delete-orphan')
    facility_allocations = db.relationship('FacilityAllocation', back_populates='initiative', cascade='all, delete-orphan')
    files = db.relationship('FileTracking', back_populates='initiative', cascade='all, delete-orphan')
    audit_logs = db.relationship('AuditLog', back_populates='initiative', cascade='all, delete-orphan')
    
    # Indexes
    __table_args__ = (
        db.Index('idx_initiative_status_type', 'status', 'initiative_type'),
        db.Index('idx_initiative_created_at', 'created_at'),
    )
    
    def __repr__(self):
        return f'<Initiative {self.id} - {self.initiative_type}>'
    
    def to_dict(self, include_details=False):
        """Convert initiative to dictionary."""
        data = {
            'id': self.id,
            'initiative_type': self.initiative_type,
            'description': self.description,
            'wave_id': self.wave_id,
            'status': self.status,
            'owner': self.owner.to_dict() if self.owner else None,
            'created_by': self.creator.to_dict() if self.creator else None,
            'reviewed_by': self.reviewer.to_dict() if self.reviewer else None,
            'review_comments': self.review_comments,
            'review_date': self.review_date.isoformat() if self.review_date else None,
            'is_deleted': self.is_deleted,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_details:
            # Include type-specific details
            if self.initiative_type == 'Cost Savings' and self.cost_savings:
                data['cost_savings'] = self.cost_savings.to_dict()
            elif self.initiative_type == 'Rebate' and self.rebate:
                data['rebate'] = self.rebate.to_dict()
            elif self.initiative_type == 'Cost Avoidance' and self.cost_avoidance:
                data['cost_avoidance'] = self.cost_avoidance.to_dict()
            
            # Include facility allocations
            data['facility_allocations'] = [alloc.to_dict() for alloc in self.facility_allocations]
            
            # Include files
            data['files'] = [f.to_dict() for f in self.files if not f.is_deleted]
        
        return data
    
    def soft_delete(self, user_id):
        """Soft delete the initiative."""
        self.is_deleted = True
        self.deleted_at = now_eastern()
        self.deleted_by_id = user_id
        self.updated_at = now_eastern()
