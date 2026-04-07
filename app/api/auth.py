"""
Authentication API endpoints.
"""
from flask import jsonify, g
from app.api import auth_bp
from app.utils.decorators import get_current_user, login_required
from datetime import datetime
from app.utils.timezone import now_eastern


@auth_bp.route('/current-user', methods=['GET'])
@login_required
def current_user():
    """Get current authenticated user information."""
    user = g.current_user
    
    # Update last login
    user.last_login = now_eastern()
    from app import db
    db.session.commit()
    
    return jsonify(user.to_dict()), 200


@auth_bp.route('/check', methods=['GET'])
def check_auth():
    """Check if user is authenticated (without requiring login)."""
    user = get_current_user()
    if user:
        return jsonify({
            'authenticated': True,
            'user': user.to_dict()
        }), 200
    else:
        return jsonify({
            'authenticated': False
        }), 200
