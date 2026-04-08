"""Helpers for loading and saving the app's static runtime settings."""
import json
import os
from copy import deepcopy


SETTINGS_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static_config.json')
FIXED_NOTIFICATION_MAILBOX = 'procurementdatateam@montefiore.org'


DEFAULT_STATIC_SETTINGS = {
    'email': {
        'from_email': FIXED_NOTIFICATION_MAILBOX,
        'graph_sender_user_id': FIXED_NOTIFICATION_MAILBOX,
        'creator_notification_to': '',
        'review_notification_to': FIXED_NOTIFICATION_MAILBOX,
        'approval_notification_to': '',
        'weekly_reminder_to': FIXED_NOTIFICATION_MAILBOX,
        'cc_addresses': FIXED_NOTIFICATION_MAILBOX,
    },
    'files': {
        'file_storage_path': '',
        'uploads_fallback_path': 'uploads',
        'rebate_attachments_folder': 'Rebate_Attachments',
        'logs_path': 'logs',
    },
}


def _deep_merge(base, updates):
    """Merge nested dictionaries without losing defaults."""
    merged = deepcopy(base)
    for key, value in (updates or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _build_defaults_from_config(config=None):
    """Create defaults using the current Flask configuration when available."""
    config = config or {}
    return {
        'email': {
            'from_email': FIXED_NOTIFICATION_MAILBOX,
            'graph_sender_user_id': FIXED_NOTIFICATION_MAILBOX,
            'creator_notification_to': config.get('CREATOR_NOTIFICATION_TO_OVERRIDE', ''),
            'review_notification_to': config.get(
                'REVIEW_NOTIFICATION_TO',
                config.get('PROCUREMENT_DATA_TEAM_EMAIL', DEFAULT_STATIC_SETTINGS['email']['review_notification_to'])
            ),
            'approval_notification_to': config.get('APPROVAL_NOTIFICATION_TO_OVERRIDE', ''),
            'weekly_reminder_to': config.get(
                'WEEKLY_REMINDER_TO',
                config.get('REVIEW_NOTIFICATION_TO', config.get('PROCUREMENT_DATA_TEAM_EMAIL', DEFAULT_STATIC_SETTINGS['email']['weekly_reminder_to']))
            ),
            'cc_addresses': FIXED_NOTIFICATION_MAILBOX,
        },
        'files': {
            'file_storage_path': config.get('FILE_STORAGE_PATH', DEFAULT_STATIC_SETTINGS['files']['file_storage_path']),
            'uploads_fallback_path': config.get('UPLOADS_FALLBACK_PATH', DEFAULT_STATIC_SETTINGS['files']['uploads_fallback_path']),
            'rebate_attachments_folder': config.get('REBATE_ATTACHMENTS_FOLDER', DEFAULT_STATIC_SETTINGS['files']['rebate_attachments_folder']),
            'logs_path': config.get('LOGS_DIR', DEFAULT_STATIC_SETTINGS['files']['logs_path']),
        },
    }


def load_static_settings(config=None):
    """Load settings from the static JSON file, creating it if needed."""
    defaults = _build_defaults_from_config(config)

    if not os.path.exists(SETTINGS_FILE_PATH):
        save_static_settings(defaults)
        return defaults

    try:
        with open(SETTINGS_FILE_PATH, 'r', encoding='utf-8') as handle:
            stored = json.load(handle)
    except (json.JSONDecodeError, OSError):
        stored = {}

    merged = _deep_merge(defaults, stored)

    # Keep the existing environment storage path when the static file is blank,
    # and write it back so admins can see and edit the active location.
    env_storage_path = defaults.get('files', {}).get('file_storage_path', '')
    if not merged.get('files', {}).get('file_storage_path') and env_storage_path:
        merged.setdefault('files', {})['file_storage_path'] = env_storage_path

    merged.setdefault('email', {})
    merged['email']['from_email'] = FIXED_NOTIFICATION_MAILBOX
    merged['email']['graph_sender_user_id'] = FIXED_NOTIFICATION_MAILBOX
    merged['email']['cc_addresses'] = FIXED_NOTIFICATION_MAILBOX

    if merged != stored:
        save_static_settings(merged)
    return merged


def save_static_settings(settings):
    """Persist settings to the static JSON file."""
    folder = os.path.dirname(SETTINGS_FILE_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)

    with open(SETTINGS_FILE_PATH, 'w', encoding='utf-8') as handle:
        json.dump(settings, handle, indent=2)

    return SETTINGS_FILE_PATH


def apply_static_settings(app):
    """Apply persisted settings to the active Flask app config."""
    settings = load_static_settings(app.config)
    email_settings = settings.get('email', {})
    file_settings = settings.get('files', {})

    app.config['STATIC_APP_SETTINGS'] = settings
    app.config['STATIC_CONFIG_FILE'] = SETTINGS_FILE_PATH

    app.config['FROM_EMAIL'] = FIXED_NOTIFICATION_MAILBOX
    app.config['MS_GRAPH_SENDER_USER_ID'] = FIXED_NOTIFICATION_MAILBOX
    app.config['CREATOR_NOTIFICATION_TO_OVERRIDE'] = email_settings.get('creator_notification_to', '')
    app.config['REVIEW_NOTIFICATION_TO'] = email_settings.get('review_notification_to', '')
    app.config['APPROVAL_NOTIFICATION_TO_OVERRIDE'] = email_settings.get('approval_notification_to', '')
    app.config['WEEKLY_REMINDER_TO'] = email_settings.get('weekly_reminder_to', '')
    app.config['PROCUREMENT_DATA_TEAM_EMAIL'] = FIXED_NOTIFICATION_MAILBOX

    app.config['FILE_STORAGE_PATH'] = file_settings.get('file_storage_path') or app.config.get('FILE_STORAGE_PATH', '')
    app.config['UPLOADS_FALLBACK_PATH'] = file_settings.get('uploads_fallback_path') or app.config.get('UPLOADS_FALLBACK_PATH', 'uploads')
    app.config['REBATE_ATTACHMENTS_FOLDER'] = file_settings.get('rebate_attachments_folder', app.config.get('REBATE_ATTACHMENTS_FOLDER', 'Rebate_Attachments'))
    app.config['LOGS_DIR'] = file_settings.get('logs_path', app.config.get('LOGS_DIR', 'logs'))

    return settings
