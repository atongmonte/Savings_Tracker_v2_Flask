"""
Configuration settings for different environments.
"""
import os
from datetime import timedelta
from urllib.parse import quote_plus


class Config:
    """Base configuration."""
    
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Database
    DB_SERVER = os.getenv('DB_SERVER', 'localhost')
    DB_NAME = os.getenv('DB_NAME', 'savingstracker_v2')
    DB_DRIVER = os.getenv('DB_DRIVER', 'ODBC Driver 17 for SQL Server')
    DB_TRUSTED_CONNECTION = os.getenv('DB_TRUSTED_CONNECTION', 'yes')
    DB_USER = os.getenv('DB_USER', '')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    
    # Build connection string (use format() instead of f-string to avoid backslash escaping)
    if DB_TRUSTED_CONNECTION.lower() == 'yes':
        connection_string = 'Driver={};Server={};Database={};Trusted_Connection=yes;'.format(DB_DRIVER, DB_SERVER, DB_NAME)
    else:
        connection_string = 'Driver={};Server={};Database={};UID={};PWD={};'.format(DB_DRIVER, DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD)
    
    # Don't use quote_plus as it double-escapes the backslash in server instance names
    SQLALCHEMY_DATABASE_URI = f'mssql+pyodbc:///?odbc_connect={connection_string}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    
    # File Storage
    FILE_STORAGE_PATH = os.getenv('FILE_STORAGE_PATH', '')
    UPLOADS_FALLBACK_PATH = os.getenv('UPLOADS_FALLBACK_PATH', 'uploads')
    REBATE_ATTACHMENTS_FOLDER = os.getenv('REBATE_ATTACHMENTS_FOLDER', 'Rebate_Attachments')
    LOGS_DIR = os.getenv('LOGS_DIR', 'logs')
    MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', 500))
    MAX_CONTENT_LENGTH = MAX_FILE_SIZE_MB * 1024 * 1024  # Convert to bytes
    ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'png', 'jpg', 'jpeg', 'gif', 'zip'}
    
    # Email / Microsoft Graph
    EMAIL_ENABLED = os.getenv('EMAIL_ENABLED', 'true').lower() == 'true'
    FROM_EMAIL = 'procurementdatateam@montefiore.org'
    PROCUREMENT_DATA_TEAM_EMAIL = 'procurementdatateam@montefiore.org'
    CREATOR_NOTIFICATION_TO_OVERRIDE = os.getenv('CREATOR_NOTIFICATION_TO_OVERRIDE', '')
    REVIEW_NOTIFICATION_TO = os.getenv('REVIEW_NOTIFICATION_TO', '')
    APPROVAL_NOTIFICATION_TO_OVERRIDE = os.getenv('APPROVAL_NOTIFICATION_TO_OVERRIDE', '')
    WEEKLY_REMINDER_TO = os.getenv('WEEKLY_REMINDER_TO', '')
    MS_GRAPH_TENANT_ID = os.getenv('MS_GRAPH_TENANT_ID', '')
    MS_GRAPH_CLIENT_ID = os.getenv('MS_GRAPH_CLIENT_ID', '')
    MS_GRAPH_CLIENT_SECRET = os.getenv('MS_GRAPH_CLIENT_SECRET', '')
    MS_GRAPH_SENDER_USER_ID = FROM_EMAIL
    
    # Pagination
    ITEMS_PER_PAGE = int(os.getenv('ITEMS_PER_PAGE', 50))
    
    # Application
    APP_URL = os.getenv('APP_URL', 'http://localhost:5000')
    
    # CORS
    CORS_HEADERS = 'Content-Type'


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_ECHO = True
    # In development, recipients can still be redirected, but sender and CC stay fixed.
    REVIEW_NOTIFICATION_TO = os.getenv('REVIEW_NOTIFICATION_TO', Config.PROCUREMENT_DATA_TEAM_EMAIL)


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    REVIEW_NOTIFICATION_TO = os.getenv('REVIEW_NOTIFICATION_TO', '')


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}


def test_database_connection():
    """Test database connection with current configuration."""
    import pyodbc
    from dotenv import load_dotenv
    
    # Load environment variables
    load_dotenv()
    
    # Get config values
    db_server = os.getenv('DB_SERVER', 'localhost')
    db_name = os.getenv('DB_NAME', 'savingstracker_v2')
    db_driver = os.getenv('DB_DRIVER', 'ODBC Driver 17 for SQL Server')
    db_trusted = os.getenv('DB_TRUSTED_CONNECTION', 'yes')
    
    # Build connection string (use format() instead of f-string to avoid backslash escaping)
    if db_trusted.lower() == 'yes':
        conn_str = 'Driver={{{}}};Server={};Database={};Trusted_Connection=yes;'.format(db_driver, db_server, db_name)
    else:
        db_user = os.getenv('DB_USER', '')
        db_password = os.getenv('DB_PASSWORD', '')
        conn_str = 'Driver={{{}}};Server={};Database={};UID={};PWD={};'.format(db_driver, db_server, db_name, db_user, db_password)
    
    print("Testing database connection...")
    print(f"Connection string: {conn_str}")
    print("-" * 80)
    
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute("SELECT @@VERSION")
        version = cursor.fetchone()
        print("✓ Connection successful!")
        print(f"SQL Server Version: {version[0][:80]}...")
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print("✗ Connection failed!")
        print(f"Error: {str(e)}")
        return False


if __name__ == '__main__':
    test_database_connection()
