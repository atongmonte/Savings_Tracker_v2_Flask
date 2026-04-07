"""
Facility allocation models (normalized).
"""
from datetime import datetime
from app import db
from app.utils.timezone import now_eastern


class Facility(db.Model):
    """Facility reference table."""
    __tablename__ = 'facilities'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)  # MMC, BURKE, AECOM, etc.
    name = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    created_at = db.Column(db.DateTime, default=now_eastern)
    updated_at = db.Column(db.DateTime, default=now_eastern, onupdate=now_eastern)
    
    # Relationships
    allocations = db.relationship('FacilityAllocation', back_populates='facility', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Facility {self.code}>'
    
    def to_dict(self):
        """Convert facility to dictionary."""
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'is_active': self.is_active
        }


class FacilityAllocation(db.Model):
    """Facility allocation percentages and amounts for initiatives."""
    __tablename__ = 'facility_allocations'
    
    id = db.Column(db.Integer, primary_key=True)
    
    initiative_id = db.Column(db.Integer, db.ForeignKey('initiatives.id'), nullable=False, index=True)
    initiative = db.relationship('Initiative', back_populates='facility_allocations')
    
    facility_id = db.Column(db.Integer, db.ForeignKey('facilities.id'), nullable=False)
    facility = db.relationship('Facility', back_populates='allocations')
    
    allocation_percentage = db.Column(db.Numeric(5, 2))  # 0.00 to 100.00 (nullable - either % or amount)
    allocation_amount = db.Column(db.Numeric(15, 2))  # Dollar amount (nullable - either % or amount)
    
    created_at = db.Column(db.DateTime, default=now_eastern)
    updated_at = db.Column(db.DateTime, default=now_eastern, onupdate=now_eastern)
    
    # Constraints
    __table_args__ = (
        db.UniqueConstraint('initiative_id', 'facility_id', name='uq_initiative_facility'),
        db.CheckConstraint('allocation_percentage IS NULL OR (allocation_percentage >= 0 AND allocation_percentage <= 100)', name='chk_allocation_percentage'),
        db.CheckConstraint('allocation_amount IS NULL OR allocation_amount >= 0', name='chk_allocation_amount'),
        db.CheckConstraint('(allocation_percentage IS NOT NULL AND allocation_amount IS NULL) OR (allocation_percentage IS NULL AND allocation_amount IS NOT NULL)', name='chk_one_allocation_type'),
    )
    
    def __repr__(self):
        return f'<FacilityAllocation Initiative:{self.initiative_id} Facility:{self.facility_id}>'
    
    def to_dict(self):
        """Convert allocation to dictionary."""
        return {
            'id': self.id,
            'facility': self.facility.to_dict() if self.facility else None,
            'allocation_percentage': float(self.allocation_percentage) if self.allocation_percentage is not None else None,
            'allocation_amount': float(self.allocation_amount) if self.allocation_amount is not None else None
        }
