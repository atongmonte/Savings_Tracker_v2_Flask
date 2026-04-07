"""
Cost Savings model.
"""
from datetime import datetime
from app import db
from app.utils.timezone import now_eastern


class CostSavings(db.Model):
    """Cost Savings initiative details."""
    __tablename__ = 'cost_savings'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign key to initiative
    initiative_id = db.Column(db.Integer, db.ForeignKey('initiatives.id'), unique=True, nullable=False, index=True)
    initiative = db.relationship('Initiative', back_populates='cost_savings')
    
    # Cost savings details
    savings_type = db.Column(db.String(100))
    wave_initiative_id = db.Column(db.String(255))
    
    # Contract information
    contract_number = db.Column(db.String(100), index=True)
    contract_category = db.Column(db.String(100), index=True)
    contract_source = db.Column(db.String(100))
    gpo_tier = db.Column(db.String(500))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    vendor_name = db.Column(db.String(255), index=True)
    
    # Financial details
    baseline_spend = db.Column(db.Numeric(18, 2))
    expected_spend = db.Column(db.Numeric(18, 2))
    annual_savings_amount = db.Column(db.Numeric(18, 2))
    total_savings_amount = db.Column(db.Numeric(18, 2))
    is_fixed_cost = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=now_eastern)
    updated_at = db.Column(db.DateTime, default=now_eastern, onupdate=now_eastern)
    
    # Indexes
    __table_args__ = (
        db.Index('idx_cost_savings_contract', 'contract_number', 'vendor_name'),
    )
    
    def __repr__(self):
        return f'<CostSavings Initiative:{self.initiative_id}>'
    
    def to_dict(self):
        """Convert cost savings to dictionary."""
        return {
            'id': self.id,
            'initiative_id': self.initiative_id,
            'savings_type': self.savings_type,
            'wave_initiative_id': self.wave_initiative_id,
            'contract_number': self.contract_number,
            'contract_category': self.contract_category,
            'contract_source': self.contract_source,
            'gpo_tier': self.gpo_tier,
            'vendor_name': self.vendor_name,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'baseline_spend': float(self.baseline_spend) if self.baseline_spend else None,
            'expected_spend': float(self.expected_spend) if self.expected_spend else None,
            'annual_savings_amount': float(self.annual_savings_amount) if self.annual_savings_amount else None,
            'total_savings_amount': float(self.total_savings_amount) if self.total_savings_amount else None,
            'is_fixed_cost': self.is_fixed_cost,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
