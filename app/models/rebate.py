"""
Rebate model.
"""
from datetime import datetime
from app import db
from app.utils.timezone import now_eastern


class Rebate(db.Model):
    """Rebate initiative details."""
    __tablename__ = 'rebates'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign key to initiative
    initiative_id = db.Column(db.Integer, db.ForeignKey('initiatives.id'), unique=True, nullable=False, index=True)
    initiative = db.relationship('Initiative', back_populates='rebate')
    
    # Rebate details
    rebate_type = db.Column(db.String(100))
    wave_initiative_id = db.Column(db.String(255))
    
    # Contract information (ordered by form appearance)
    contract_category = db.Column(db.String(100), index=True)
    contract_source = db.Column(db.String(100))
    contract_number = db.Column(db.String(100), index=True)
    vendor_name = db.Column(db.String(255), index=True)
    gpo_tier = db.Column(db.String(500))
    
    # Payment details
    rebate_check_date = db.Column(db.Date)
    rebate_payment_type = db.Column(db.String(50))  # Check, ACH, Credit Memo, EFT
    check_number = db.Column(db.String(500))
    
    # Financial details
    rebate_amount = db.Column(db.Numeric(18, 2))
    
    created_at = db.Column(db.DateTime, default=now_eastern)
    updated_at = db.Column(db.DateTime, default=now_eastern, onupdate=now_eastern)
    
    # Indexes
    __table_args__ = (
        db.Index('idx_rebate_contract', 'contract_number', 'vendor_name'),
        db.Index('idx_rebate_transaction', 'check_number'),
    )
    
    def __repr__(self):
        return f'<Rebate Initiative:{self.initiative_id}>'
    
    def to_dict(self):
        """Convert rebate to dictionary."""
        return {
            'id': self.id,
            'initiative_id': self.initiative_id,
            'rebate_type': self.rebate_type,
            'wave_initiative_id': self.wave_initiative_id,
            'contract_number': self.contract_number,
            'contract_category': self.contract_category,
            'contract_source': self.contract_source,
            'gpo_tier': self.gpo_tier,
            'vendor_name': self.vendor_name,
            'transaction_date': self.rebate_check_date.isoformat() if self.rebate_check_date else None,
            'transaction_type': self.rebate_payment_type,
            'transaction_number': self.check_number,
            'rebate_amount': float(self.rebate_amount) if self.rebate_amount else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
