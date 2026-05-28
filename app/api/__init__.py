"""
API Blueprints initialization.
"""
from flask import Blueprint

# Create blueprints
initiatives_bp = Blueprint('initiatives', __name__)
cost_savings_bp = Blueprint('cost_savings', __name__)
rebate_bp = Blueprint('rebate', __name__)
cost_avoidance_bp = Blueprint('cost_avoidance', __name__)
auth_bp = Blueprint('auth', __name__)
analytics_bp = Blueprint('analytics', __name__)
admin_bp = Blueprint('admin', __name__)

# Import routes (import after blueprint creation to avoid circular imports)
from app.api import initiatives, cost_savings, rebate, cost_avoidance, auth, analytics, admin
