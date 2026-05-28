"""
Flask application factory.
"""
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()


def create_app(config_name='default'):
    """
    Application factory pattern.
    
    Args:
        config_name: Configuration to use (development, testing, production)
        
    Returns:
        Flask application instance
    """
    app = Flask(__name__)
    
    # Load configuration
    from app.config import config
    app.config.from_object(config[config_name])

    # Apply editable static settings from JSON
    from app.utils.runtime_settings import apply_static_settings
    apply_static_settings(app)
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app)
    
    # Create logs directory
    logs_dir = app.config.get('LOGS_DIR') or os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    if not os.path.isabs(logs_dir):
        logs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), logs_dir)
    logs_dir = os.path.normpath(logs_dir)
    app.config['LOGS_DIR'] = logs_dir
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)

    # Register blueprints
    from app.api import initiatives_bp, cost_savings_bp, rebate_bp, cost_avoidance_bp, auth_bp, analytics_bp, admin_bp
    app.register_blueprint(initiatives_bp, url_prefix='/api/initiatives')
    app.register_blueprint(cost_savings_bp, url_prefix='/api/cost-savings')
    app.register_blueprint(rebate_bp, url_prefix='/api/rebates')
    app.register_blueprint(cost_avoidance_bp, url_prefix='/api/cost-avoidance')
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    
    # Register main routes (for serving HTML pages)
    from app.views import main_bp
    app.register_blueprint(main_bp)
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return {'error': 'Not found'}, 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return {'error': 'Internal server error'}, 500
    
    return app
