"""
Authentication and authorization utilities.
"""
import os
from functools import wraps
from flask import request, jsonify, g, session
from app import db
from app.models import User


def get_authenticated_user():
    """
    Get current user from IIS Windows Authentication.
    IIS passes the authenticated username via REMOTE_USER or AUTH_USER.
    In development, first-time users are automatically assigned the Admin role.
    In all other environments, first-time users are assigned the ReadOnly role.
    """
    from app.models import UserRole

    username = request.environ.get('REMOTE_USER') or request.environ.get('AUTH_USER')

    if not username:
        username = request.headers.get('X-Remote-User')

    if not username:
        from flask import current_app
        if current_app.config.get('DEV_BYPASS_AUTH', False):
            username = os.environ.get('USERNAME') or os.environ.get('USER') or 'devuser'
        else:
            return None

    # Remove domain prefix if present (DOMAIN\username -> username)
    if '\\' in username:
        username = username.split('\\')[-1]

    user = User.query.filter_by(username=username).first()
    if not user:
        from flask import current_app
        dev_auto_admin = current_app.config.get('DEV_AUTO_ADMIN', False)

        if dev_auto_admin:
            # Development: auto-assign Admin role
            assigned_role = UserRole.query.filter_by(name='Admin').first()
            if not assigned_role:
                assigned_role = UserRole(
                    name='Admin',
                    description='System administrator with full access',
                    can_create=True,
                    can_edit_own=True,
                    can_edit_all=True,
                    can_delete_own=True,
                    can_delete_all=True,
                    can_review=True,
                    can_approve=True,
                    can_export=True,
                    can_manage_users=True,
                )
                db.session.add(assigned_role)
                db.session.flush()
        else:
            # All other environments: auto-assign ReadOnly role
            assigned_role = UserRole.query.filter_by(name='ReadOnly').first()
            if not assigned_role:
                assigned_role = UserRole.query.filter_by(name='Read Only').first()
            if not assigned_role:
                assigned_role = UserRole.query.filter_by(name='Read-Only').first()
            if not assigned_role:
                assigned_role = UserRole(
                    name='ReadOnly',
                    description='Can view initiatives; cannot modify data or download attachments',
                    can_create=False,
                    can_edit_own=False,
                    can_edit_all=False,
                    can_delete_own=False,
                    can_delete_all=False,
                    can_review=False,
                    can_approve=False,
                    can_export=False,
                    can_manage_users=False,
                )
                db.session.add(assigned_role)
                db.session.flush()

        user = User(
            username=username,
            full_name=username,
            email='',
            role_id=assigned_role.id,
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()

    return user


class RolePreviewUser:
    """Request-local permissions without modifying the persistent user record."""

    def __init__(self, user, role):
        self._user = user
        self.role = role
        self.role_id = role.id

    def __getattr__(self, name):
        return getattr(self._user, name)

    is_read_only = User.is_read_only
    has_permission = User.has_permission
    to_dict = User.to_dict


def get_current_user():
    user = get_authenticated_user()
    preview = session.get('role_preview')
    if not preview:
        return user
    if (not user or not user.is_active or not user.role or
            user.role.name != 'Admin' or not isinstance(preview, dict) or
            preview.get('user_id') != user.id):
        session.pop('role_preview', None)
        return user
    from app.models import UserRole
    role = db.session.get(UserRole, preview.get('role_id'))
    if role is None:
        session.pop('role_preview', None)
        return user
    return RolePreviewUser(user, role)


def login_required(f):
    """Decorator to require authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if user is None:
            return jsonify({'error': 'Authentication required'}), 401
        if not user.is_active:
            return jsonify({'error': 'User account is inactive'}), 403
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function


def permission_required(permission):
    """Decorator to require specific permission."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if user is None:
                return jsonify({'error': 'Authentication required'}), 401
            if not user.is_active:
                return jsonify({'error': 'User account is inactive'}), 403
            if not user.has_permission(permission):
                return jsonify({'error': 'Insufficient permissions'}), 403
            g.current_user = user
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def role_required(*role_names):
    """Decorator to require specific role(s)."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if user is None:
                return jsonify({'error': 'Authentication required'}), 401
            if not user.is_active:
                return jsonify({'error': 'User account is inactive'}), 403
            if user.role.name not in role_names:
                return jsonify({'error': 'Insufficient permissions'}), 403
            g.current_user = user
            return f(*args, **kwargs)
        return decorated_function
    return decorator

