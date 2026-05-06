"""
Authentication and authorization utilities.
"""
from functools import wraps
from flask import request, jsonify, g
from app import db
from app.models import User


def get_current_user():
    """
    Get current user from IIS Windows Authentication.
    IIS passes the authenticated username via REMOTE_USER or AUTH_USER.
    First-time users are automatically assigned the Read-Only role.
    """
    from app.models import UserRole

    username = request.environ.get('REMOTE_USER') or request.environ.get('AUTH_USER')

    if not username:
        username = request.headers.get('X-Remote-User')

    if not username:
        return None

    # Remove domain prefix if present (DOMAIN\username -> username)
    if '\\' in username:
        username = username.split('\\')[-1]

    user = User.query.filter_by(username=username).first()
    if not user:
        # Auto-create first-time login user with Read-Only role
        readonly_role = UserRole.query.filter_by(name='Read-Only').first()
        if not readonly_role:
            return None  # DB not seeded yet
        user = User(
            username=username,
            full_name=username,
            email='',
            role_id=readonly_role.id,
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()

    return user


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

