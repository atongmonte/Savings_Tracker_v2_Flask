"""
Authentication and authorization utilities.
"""
from functools import wraps
from flask import request, jsonify, g
from app import db
from app.models import User

# ============================================================================
# TEMPORARY: IIS Authentication Disabled for Local Development
# UNCOMMENT THE SECTION BELOW WHEN DEPLOYING TO IIS
# ============================================================================

def get_current_user():
    """
    TEMPORARY: Returns a mock user for local development.
    Replace this with actual IIS authentication when deploying.
    """
    # TEMPORARY: Return mock admin user for testing
    from app.models import UserRole
    
    # Try to get or create a test user
    test_username = 'atong'
    user = User.query.filter_by(username=test_username).first()
    
    if not user:
        # Create test user with Admin role
        admin_role = UserRole.query.filter_by(name='Admin').first()
        if admin_role:
            user = User(
                username=test_username,
                email='atong@montefiore.org',
                full_name='Andrew Tong',
                role_id=admin_role.id,
                is_active=True
            )
            db.session.add(user)
            db.session.commit()
    
    return user

# COMMENTED OUT - IIS Authentication (Uncomment for production)
# def get_current_user():
#     """
#     Get current user from IIS Windows Authentication.
#     IIS will pass the username in REMOTE_USER or AUTH_USER header.
#     """
#     # Try to get username from IIS authentication
#     username = request.environ.get('REMOTE_USER') or request.environ.get('AUTH_USER')
#     
#     if not username:
#         # For development, check custom header
#         username = request.headers.get('X-Remote-User')
#     
#     if username:
#         # Remove domain prefix if present (DOMAIN\username -> username)
#         if '\\' in username:
#             username = username.split('\\')[-1]
#         
#         # Get or create user
#         user = User.query.filter_by(username=username).first()
#         if not user:
#             # Auto-create user (you may want to disable this in production)
#             # For now, return None and handle in endpoint
#             return None
#         
#         return user
#     
#     return None


def login_required(f):
    """
    TEMPORARY: Decorator bypassed for local development.
    Uncomment the real version when deploying to IIS.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # TEMPORARY: Just set current user without checking authentication
        user = get_current_user()
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function

# COMMENTED OUT - Real authentication (Uncomment for production)
# def login_required(f):
#     """Decorator to require authentication."""
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         user = get_current_user()
#         if user is None:
#             return jsonify({'error': 'Authentication required'}), 401
#         if not user.is_active:
#             return jsonify({'error': 'User account is inactive'}), 403
#         g.current_user = user
#         return f(*args, **kwargs)
#     return decorated_function


def permission_required(permission):
    """
    TEMPORARY: Decorator bypassed for local development.
    Uncomment the real version when deploying to IIS.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # TEMPORARY: Just set current user without checking permissions
            user = get_current_user()
            g.current_user = user
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# COMMENTED OUT - Real permission check (Uncomment for production)
# def permission_required(permission):
#     """Decorator to require specific permission."""
#     def decorator(f):
#         @wraps(f)
#         def decorated_function(*args, **kwargs):
#             user = get_current_user()
#             if user is None:
#                 return jsonify({'error': 'Authentication required'}), 401
#             if not user.is_active:
#                 return jsonify({'error': 'User account is inactive'}), 403
#             if not user.has_permission(permission):
#                 return jsonify({'error': 'Insufficient permissions'}), 403
#             g.current_user = user
#             return f(*args, **kwargs)
#         return decorated_function
#     return decorator


def role_required(*role_names):
    """
    TEMPORARY: Decorator bypassed for local development.
    Uncomment the real version when deploying to IIS.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # TEMPORARY: Just set current user without checking role
            user = get_current_user()
            g.current_user = user
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# COMMENTED OUT - Real role check (Uncomment for production)
# def role_required(*role_names):
#     """Decorator to require specific role(s)."""
#     def decorator(f):
#         @wraps(f)
#         def decorated_function(*args, **kwargs):
#             user = get_current_user()
#             if user is None:
#                 return jsonify({'error': 'Authentication required'}), 401
#             if not user.is_active:
#                 return jsonify({'error': 'User account is inactive'}), 403
#             if user.role.name not in role_names:
#                 return jsonify({'error': 'Insufficient permissions'}), 403
#             g.current_user = user
#             return f(*args, **kwargs)
#         return decorated_function
#     return decorator

