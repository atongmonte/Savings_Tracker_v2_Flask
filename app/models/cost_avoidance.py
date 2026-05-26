"""
Cost Avoidance model.
"""
from datetime import datetime
from app import db
from app.utils.timezone import now_eastern


class CostAvoidance(db.Model):
    """Cost Avoidance initiative details."""
    __tablename__ = 'cost_avoidance'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign key to initiative
    initiative_id = db.Column(db.Integer, db.ForeignKey('initiatives.id'), unique=True, nullable=False, index=True)
    initiative = db.relationship('Initiative', back_populates='cost_avoidance')
    
    # Cost avoidance details
    avoidance_type = db.Column(db.String(100))  # Capital, Service, Value Analysis, Price Parity, NPR
    
    # Project details
    strata_project_id = db.Column(db.String(100))
    
    # Contract information
    contract_category = db.Column(db.String(100), index=True)
    contract_number = db.Column(db.String(100), index=True)
    contract_source = db.Column(db.String(100))
    vendor_name = db.Column(db.String(255), index=True)
    
    # Purchase order details
    po_number = db.Column(db.String(100), index=True)
    po_date = db.Column(db.Date)
    avoidance_date = db.Column(db.Date)
    
    # Financial details
    original_quote = db.Column(db.Numeric(18, 2))
    new_quote = db.Column(db.Numeric(18, 2))
    avoidance_amount = db.Column(db.Numeric(18, 2))
    
    created_at = db.Column(db.DateTime, default=now_eastern)
    updated_at = db.Column(db.DateTime, default=now_eastern, onupdate=now_eastern)
    
    # Indexes
    __table_args__ = (
        db.Index('idx_cost_avoidance_contract', 'contract_number', 'vendor_name'),
        db.Index('idx_cost_avoidance_po', 'po_number'),
    )
    
    def __repr__(self):
        return f'<CostAvoidance Initiative:{self.initiative_id}>'
    
    def to_dict(self):
        """Convert cost avoidance to dictionary."""
        return {
            'id': self.id,
            'initiative_id': self.initiative_id,
            'avoidance_type': self.avoidance_type,
            'strata_project_id': self.strata_project_id,
            'contract_number': self.contract_number,
            'contract_category': self.contract_category,
            'contract_source': self.contract_source,
            'vendor_name': self.vendor_name,
            'po_number': self.po_number,
            'po_date': self.po_date.isoformat() if self.po_date else None,
            'avoidance_date': self.avoidance_date.isoformat() if self.avoidance_date else None,
            'original_quote': float(self.original_quote) if self.original_quote else None,
            'new_quote': float(self.new_quote) if self.new_quote else None,
            'avoidance_amount': float(self.avoidance_amount) if self.avoidance_amount else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
