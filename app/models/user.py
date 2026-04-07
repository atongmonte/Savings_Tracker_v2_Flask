"""
User and Role models.
"""
from datetime import datetime
from app import db
from app.utils.timezone import now_eastern


class UserRole(db.Model):
    """User roles for authorization."""
    __tablename__ = 'user_roles'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255))
    
    # Permissions
    can_create = db.Column(db.Boolean, default=True)
    can_edit_own = db.Column(db.Boolean, default=True)
    can_edit_all = db.Column(db.Boolean, default=False)
    can_delete_own = db.Column(db.Boolean, default=True)
    can_delete_all = db.Column(db.Boolean, default=False)
    can_review = db.Column(db.Boolean, default=False)
    can_approve = db.Column(db.Boolean, default=False)
    can_export = db.Column(db.Boolean, default=True)
    can_manage_users = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=now_eastern)
    updated_at = db.Column(db.DateTime, default=now_eastern, onupdate=now_eastern)
    
    # Relationships
    users = db.relationship('User', back_populates='role', lazy='dynamic')
    
    def __repr__(self):
        return f'<UserRole {self.name}>'


class User(db.Model):
    """User model for authentication and authorization."""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False, index=True)
    
    # Role relationship
    role_id = db.Column(db.Integer, db.ForeignKey('user_roles.id'), nullable=False)
    role = db.relationship('UserRole', back_populates='users')
    
    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=now_eastern)
    updated_at = db.Column(db.DateTime, default=now_eastern, onupdate=now_eastern)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    created_initiatives = db.relationship(
        'Initiative',
        foreign_keys='Initiative.created_by_id',
        back_populates='creator',
        lazy='dynamic'
    )
    
    owned_initiatives = db.relationship(
        'Initiative',
        foreign_keys='Initiative.owner_id',
        back_populates='owner',
        lazy='dynamic'
    )
    
    reviewed_initiatives = db.relationship(
        'Initiative',
        foreign_keys='Initiative.reviewed_by_id',
        back_populates='reviewer',
        lazy='dynamic'
    )
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    def has_permission(self, permission):
        """Check if user has a specific permission."""
        return getattr(self.role, f'can_{permission}', False)
    
    def to_dict(self):
        """Convert user to dictionary."""
        return {
            'id': self.id,
            'username': self.username,
            'full_name': self.full_name,
            'email': self.email,
            'role': self.role.name if self.role else None,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'can_approve':    self.role.can_approve    if self.role else False,
            'can_review':      self.role.can_review      if self.role else False,
            'can_delete_all':  self.role.can_delete_all  if self.role else False,
            'can_delete_own':  self.role.can_delete_own  if self.role else False,
        }
