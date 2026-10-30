"""
Wave File refresh API.

Users upload the weekly Wave export. It is validated, archived, loaded into
the PBI staging table and merged in one transaction, and the dashboard
savings totals are returned before and after. Every refresh attempt is
recorded in system_event_logs (event_type WAVE_REFRESH).
"""
import json
import os
import secrets

import pyodbc
from flask import current_app, g, jsonify, request, session

from app import db
from app.api import wave_refresh_bp
from app.models import SystemEventLog
from app.utils.decorators import login_required
from app.utils.timezone import now_eastern
from app.utils.wave_refresh import (
    DEFAULT_MAX_EXPORT_AGE_DAYS,
    PowerBiSchedule,
    WaveRefreshError,
    apply_refresh,
    archive_export,
    can_refresh_wave,
    compare_with_database,
    current_totals,
    parse_export,
    target_label,
)

EVENT_TYPE = 'WAVE_REFRESH'
CSRF_SESSION_KEY = 'wave_refresh_csrf'
ARCHIVE_FOLDER_NAME = 'Wave_Exports'
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
HISTORY_LIMIT = 10


def _archive_folder():
    """Wave exports are kept beside initiative attachments (see initiatives.upload_files)."""
    storage_base = current_app.config.get('FILE_STORAGE_PATH')
    if not storage_base:
        fallback_path = current_app.config.get('UPLOADS_FALLBACK_PATH', 'uploads')
        storage_base = fallback_path if os.path.isabs(fallback_path) else os.path.join(
            current_app.root_path, '..', fallback_path
        )
    stripped = storage_base.lstrip('\\')
    if stripped != storage_base:  # UNC path read from .env with extra backslashes
        storage_base = '\\\\' + stripped
    return os.path.join(os.path.normpath(storage_base), ARCHIVE_FOLDER_NAME)


def _database_message(exc):
    """Shorten a pyodbc error to the SQL Server message for display."""
    text = str(exc.args[1] if len(exc.args) > 1 else exc)
    return text.split('[SQL Server]')[-1].split(' (SQLExecDirectW)')[0].strip()[:400]


def _record_event(user, started_at, receipt):
    """Persist one refresh attempt; logging failures never mask the refresh result."""
    ended_at = now_eastern()
    try:
        db.session.add(SystemEventLog(
            event_type=EVENT_TYPE,
            status='success' if receipt.get('database_updated') else 'failed',
            log_text=json.dumps(receipt),
            started_by=user.full_name or user.username,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=(ended_at - started_at).total_seconds(),
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Could not record Wave refresh event')


def _history():
    rows = (
        SystemEventLog.query
        .filter_by(event_type=EVENT_TYPE)
        .order_by(SystemEventLog.started_at.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    history = []
    for row in rows:
        try:
            receipt = json.loads(row.log_text or '{}')
        except ValueError:
            receipt = {}
        history.append({
            'started_at': row.started_at.isoformat() if row.started_at else None,
            'started_by': row.started_by,
            'status': row.status,
            'file_name': receipt.get('file_name'),
            'rows': receipt.get('rows'),
            'message': receipt.get('message'),
        })
    return history


def _last_refresh(schedule):
    """When the latest successful refresh from this page should show in Power BI."""
    latest = (
        SystemEventLog.query
        .filter_by(event_type=EVENT_TYPE, status='success')
        .order_by(SystemEventLog.started_at.desc())
        .first()
    )
    if not latest or not latest.ended_at:
        return None
    return {**schedule.estimate(latest.ended_at), 'started_by': latest.started_by}


@wave_refresh_bp.route('/status', methods=['GET'])
@login_required
def refresh_status():
    """Current dashboard totals from PBI plus recent refresh history."""
    if not can_refresh_wave(g.current_user):
        return jsonify({'error': 'You do not have access to the Wave File refresh.'}), 403

    schedule = PowerBiSchedule.from_config(current_app.config)
    payload = {
        'history': _history(),
        'last_refresh': _last_refresh(schedule),
        'if_loaded_now': schedule.estimate(now_eastern()),
        'target': target_label(current_app.config),
    }
    try:
        payload['totals'] = current_totals(current_app.config, now_eastern().year)
    except pyodbc.Error as exc:
        current_app.logger.warning('Wave totals query failed: %s', exc)
        payload['totals_error'] = f'Could not read the dashboard totals: {_database_message(exc)}'
    return jsonify(payload)


@wave_refresh_bp.route('/upload', methods=['POST'])
@login_required
def upload_export():
    """Validate an export (mode=validate) or validate and load it (mode=refresh)."""
    user = g.current_user
    if not can_refresh_wave(user):
        return jsonify({'error': 'You do not have access to the Wave File refresh.'}), 403
    token = session.get(CSRF_SESSION_KEY)
    if not token or not secrets.compare_digest(token, request.form.get('csrf_token', '')):
        return jsonify({'error': 'Your session expired. Reload the page and try again.'}), 400

    mode = request.form.get('mode', 'validate')
    if mode not in ('validate', 'refresh'):
        return jsonify({'error': 'Unknown upload mode.'}), 400
    upload = request.files.get('file')
    if not upload or not upload.filename:
        return jsonify({'error': 'Choose the Wave export file to upload.'}), 400
    content = upload.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        return jsonify({'error': f'The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.'}), 400

    config = current_app.config
    started_at = now_eastern()
    year = started_at.year
    receipt = {
        'mode': mode,
        'status': 'failed',
        'database_updated': False,
        'file_name': upload.filename,
        'realization_year': year,
        'target': target_label(config),
    }
    status_code = 200

    try:
        export = parse_export(
            upload.filename,
            content,
            today=started_at.date(),
            max_age_days=config.get('WAVE_MAX_EXPORT_AGE_DAYS', DEFAULT_MAX_EXPORT_AGE_DAYS),
        )
        receipt.update(export.summary())

        if mode == 'validate':
            try:
                receipt.update(compare_with_database(config, export))
            except pyodbc.Error as exc:
                receipt['warnings'].append(
                    f'Could not compare with the data already loaded: {_database_message(exc)}'
                )
            receipt.update(status='validated', message='The file passed every check. Nothing was loaded.')
            return jsonify(receipt)

        try:
            receipt['archived_path'] = archive_export(_archive_folder(), export, started_at)
        except OSError as exc:
            current_app.logger.exception('Wave export archive failed')
            raise WaveRefreshError(
                'Could not save a copy of the export to the shared drive, so nothing was loaded.',
                details=[str(exc)],
                status_code=500,
            ) from exc

        receipt.update(apply_refresh(config, export, year))
        receipt.update(
            status='refreshed',
            database_updated=True,
            message='The export was loaded and merged into the dashboard tables.',
            power_bi=PowerBiSchedule.from_config(config).estimate(now_eastern()),
        )
    except WaveRefreshError as exc:
        receipt.update(message=str(exc), details=exc.details)
        status_code = exc.status_code
    except pyodbc.Error as exc:
        current_app.logger.exception('Wave refresh database error')
        receipt.update(
            message='The PBI database rejected the refresh. Nothing was changed.',
            details=[_database_message(exc)],
        )
        status_code = 502

    if mode == 'refresh':
        _record_event(user, started_at, receipt)
    return jsonify(receipt), status_code
