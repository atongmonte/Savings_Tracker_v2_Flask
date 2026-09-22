"""
API Blueprints initialization.
"""
from flask import Blueprint, jsonify, request

# Create blueprints
initiatives_bp = Blueprint('initiatives', __name__)
cost_savings_bp = Blueprint('cost_savings', __name__)
rebate_bp = Blueprint('rebate', __name__)
cost_avoidance_bp = Blueprint('cost_avoidance', __name__)
auth_bp = Blueprint('auth', __name__)
analytics_bp = Blueprint('analytics', __name__)


def enforce_viewer_read_access():
    """Prevent viewing roles from mutating initiatives or attachments."""
    if request.method in {'GET', 'HEAD', 'OPTIONS'}:
        return None
    from app.utils.decorators import get_current_user
    user = get_current_user()
    if user and user.is_read_only:
        return jsonify({'error': 'Read-Only users cannot modify initiatives.'}), 403
    if user and user.role and user.role.name == 'Finance':
        return jsonify({'error': 'Finance has read-only access to initiatives.'}), 403
    return None


for blueprint in (initiatives_bp, cost_savings_bp, rebate_bp, cost_avoidance_bp):
    blueprint.before_request(enforce_viewer_read_access)

# Import routes (import after blueprint creation to avoid circular imports)
from app.api import initiatives, cost_savings, rebate, cost_avoidance, auth, analytics
