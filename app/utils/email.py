"""
Email notification utilities using Microsoft Graph API.
"""
import html
import json
import os
from datetime import date, datetime
from urllib import error, parse, request

from dotenv import load_dotenv
from flask import current_app


GRAPH_SCOPE = 'https://graph.microsoft.com/.default'
FIXED_NOTIFICATION_MAILBOX = 'procurementdatateam@montefiore.org'


def _email_result(success, message, status_code=None, **extra):
    """Build a consistent result payload for email operations."""
    payload = {
        'success': success,
        'message': message,
        'status_code': status_code,
    }
    payload.update(extra)
    return payload


def _as_list(value):
    """Normalize strings or iterables into a clean list of email addresses."""
    if not value:
        return []
    if isinstance(value, str):
        normalized = value.replace(';', ',')
        return [item.strip() for item in normalized.split(',') if item and item.strip()]
    if isinstance(value, (list, tuple, set)):
        addresses = []
        for item in value:
            addresses.extend(_as_list(item))
        return addresses
    return [str(value).strip()]


def _unique_addresses(value):
    """Deduplicate email addresses while preserving order."""
    seen = set()
    addresses = []
    for address in _as_list(value):
        key = address.lower()
        if key not in seen:
            seen.add(key)
            addresses.append(address)
    return addresses


def _graph_recipients(addresses):
    """Convert addresses into Microsoft Graph recipient objects."""
    return [
        {'emailAddress': {'address': address}}
        for address in _unique_addresses(addresses)
    ]


def _get_user_email(user):
    """Return the best available email address for a user."""
    if not user:
        return None

    email = (getattr(user, 'email', '') or '').strip()
    if email:
        return email

    username = (getattr(user, 'username', '') or '').strip()
    if username and '@' not in username:
        return f'{username}@montefiore.org'
    return username or None


def _get_notification_recipient(user, override_key=None):
    """Return the configured override recipient when present, otherwise the user email."""
    override_value = current_app.config.get(override_key, '') if override_key else ''
    if override_value:
        return override_value
    return _get_user_email(user)


def _format_value(value):
    """Format values safely for display in email templates."""
    if value in (None, '', []):
        return 'N/A'
    if isinstance(value, datetime):
        return value.strftime('%m/%d/%Y %I:%M %p')
    if isinstance(value, date):
        return value.strftime('%m/%d/%Y')
    if isinstance(value, (int, float)):
        return f'${value:,.2f}'
    return html.escape(str(value))


def _get_initiative_summary(initiative):
    """Build a summary dictionary from an initiative record."""
    details = None
    amount = None

    if initiative.initiative_type == 'Cost Savings' and initiative.cost_savings:
        details = initiative.cost_savings
        amount = details.total_savings_amount
    elif initiative.initiative_type == 'Rebate' and initiative.rebate:
        details = initiative.rebate
        amount = details.rebate_amount
    elif initiative.initiative_type == 'Cost Avoidance' and initiative.cost_avoidance:
        details = initiative.cost_avoidance
        amount = details.avoidance_amount

    return {
        'Initiative ID': initiative.id,
        'Initiative Type': initiative.initiative_type,
        'Status': initiative.status,
        'Created By': getattr(initiative.creator, 'full_name', 'N/A'),
        'Owner': getattr(initiative.owner, 'full_name', 'N/A'),
        'Created On': _format_value(getattr(initiative, 'created_at', None)),
        'Description': _format_value(getattr(initiative, 'description', None)),
        'Contract Category': _format_value(getattr(details, 'contract_category', None)),
        'Contract Number': _format_value(getattr(details, 'contract_number', None)),
        'Vendor Name': _format_value(getattr(details, 'vendor_name', None)),
        'Estimated Impact': _format_value(amount),
        'Wave ID': _format_value(getattr(initiative, 'wave_id', None)),
    }


def _render_summary_table(summary):
    """Render the initiative summary as a simple HTML table."""
    rows = ''.join(
        f"<tr><td style='padding:8px 10px;border:1px solid #d9e1ea;background:#f7f9fc;'><strong>{html.escape(label)}</strong></td>"
        f"<td style='padding:8px 10px;border:1px solid #d9e1ea;'>{value}</td></tr>"
        for label, value in summary.items()
    )
    return (
        "<table style='border-collapse:collapse;width:100%;max-width:760px;margin:16px 0;font-family:Arial,sans-serif;font-size:14px;'>"
        f"{rows}</table>"
    )


def _render_email_layout(message_html, summary_html='', footer_note='- Procurement Data Team'):
    """Wrap content in a consistent HTML email layout."""
    app_url = current_app.config.get('APP_URL', '#')
    return f"""
    <div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.6;color:#1f2d3d;max-width:800px;">
        {message_html}
        {summary_html}
        <p>Please log in to Savings Tracker for additional details:</p>
        <p><a href="{app_url}">{app_url}</a></p>
        <p style="margin-top:24px;"><strong>{html.escape(footer_note)}</strong></p>
    </div>
    """


def _get_graph_access_token():
    """Acquire an application token for Microsoft Graph."""
    # Reload `.env` so a running dev server can pick up newly added Graph secrets
    # without needing a full application restart.
    load_dotenv(override=True)

    tenant_id = current_app.config.get('MS_GRAPH_TENANT_ID') or os.getenv('MS_GRAPH_TENANT_ID', '')
    client_id = current_app.config.get('MS_GRAPH_CLIENT_ID') or os.getenv('MS_GRAPH_CLIENT_ID', '')
    client_secret = current_app.config.get('MS_GRAPH_CLIENT_SECRET') or os.getenv('MS_GRAPH_CLIENT_SECRET', '')

    current_app.config['MS_GRAPH_TENANT_ID'] = tenant_id
    current_app.config['MS_GRAPH_CLIENT_ID'] = client_id
    current_app.config['MS_GRAPH_CLIENT_SECRET'] = client_secret

    if not all([tenant_id, client_id, client_secret]):
        missing = []
        if not tenant_id:
            missing.append('MS_GRAPH_TENANT_ID')
        if not client_id:
            missing.append('MS_GRAPH_CLIENT_ID')
        if not client_secret:
            missing.append('MS_GRAPH_CLIENT_SECRET')
        current_app.logger.warning(
            'Microsoft Graph email settings are not fully configured. Missing: %s',
            ', '.join(missing) or 'unknown'
        )
        return None

    token_url = f'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token'
    payload = parse.urlencode({
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret,
        'scope': GRAPH_SCOPE,
    }).encode('utf-8')

    try:
        token_request = request.Request(
            token_url,
            data=payload,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            method='POST',
        )
        with request.urlopen(token_request, timeout=20) as response:
            token_data = json.loads(response.read().decode('utf-8'))
        return token_data.get('access_token')
    except error.HTTPError as exc:
        details = exc.read().decode('utf-8', errors='replace')
        current_app.logger.error(f'Unable to get Microsoft Graph token: {exc.code} {details}')
        return None
    except error.URLError as exc:
        current_app.logger.error(f'Unable to reach Microsoft Graph token endpoint: {exc}')
        return None


def is_graph_mail_configured():
    """Return True when the required Microsoft Graph settings are present."""
    load_dotenv(override=True)
    return all([
        current_app.config.get('MS_GRAPH_TENANT_ID') or os.getenv('MS_GRAPH_TENANT_ID'),
        current_app.config.get('MS_GRAPH_CLIENT_ID') or os.getenv('MS_GRAPH_CLIENT_ID'),
        current_app.config.get('MS_GRAPH_CLIENT_SECRET') or os.getenv('MS_GRAPH_CLIENT_SECRET'),
        current_app.config.get('MS_GRAPH_SENDER_USER_ID') or os.getenv('MS_GRAPH_SENDER_USER_ID') or current_app.config.get('FROM_EMAIL') or os.getenv('FROM_EMAIL'),
    ])


def send_email(to_addresses, subject, html_content, cc_addresses=None, bcc_addresses=None, return_details=False):
    """Send an HTML email using Microsoft Graph."""
    to_list = _unique_addresses(to_addresses)
    cc_list = _unique_addresses(FIXED_NOTIFICATION_MAILBOX)
    bcc_list = _unique_addresses(bcc_addresses)

    try:
        if not current_app.config.get('EMAIL_ENABLED', True):
            result = _email_result(False, 'Email sending is disabled in configuration.')
            current_app.logger.info(f"Email sending disabled. Skipping: {subject}")
            return result if return_details else result['success']

        to_recipients = _graph_recipients(to_list)
        cc_recipients = _graph_recipients(cc_list)
        bcc_recipients = _graph_recipients(bcc_list)

        if not to_recipients:
            result = _email_result(False, 'No recipients were provided for the email.')
            current_app.logger.warning(f'No recipients found for email: {subject}')
            return result if return_details else result['success']

        access_token = _get_graph_access_token()
        if not access_token:
            result = _email_result(False, 'Microsoft Graph access token could not be acquired.')
            return result if return_details else result['success']

        sender_user = FIXED_NOTIFICATION_MAILBOX
        current_app.config['FROM_EMAIL'] = FIXED_NOTIFICATION_MAILBOX
        current_app.config['MS_GRAPH_SENDER_USER_ID'] = FIXED_NOTIFICATION_MAILBOX
        current_app.config['PROCUREMENT_DATA_TEAM_EMAIL'] = FIXED_NOTIFICATION_MAILBOX

        current_app.logger.info(
            'Microsoft Graph email attempt | sender=%s | to=%s | cc=%s | subject=%s',
            sender_user,
            ', '.join(to_list),
            ', '.join(cc_list),
            subject,
        )

        endpoint = f'https://graph.microsoft.com/v1.0/users/{sender_user}/sendMail'
        payload = {
            'message': {
                'subject': subject,
                'body': {
                    'contentType': 'HTML',
                    'content': html_content,
                },
                'toRecipients': to_recipients,
                'ccRecipients': cc_recipients,
                'bccRecipients': bcc_recipients,
            },
            'saveToSentItems': True,
        }

        email_request = request.Request(
            endpoint,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
            },
            method='POST',
        )

        with request.urlopen(email_request, timeout=30) as response:
            status_code = response.getcode()
            response_body = response.read().decode('utf-8', errors='replace')

        if status_code == 202:
            message = 'Microsoft Graph accepted the email request (202).'
            current_app.logger.info(f'Email sent successfully via Microsoft Graph: {subject}')
            result = _email_result(True, message, status_code=status_code, response=response_body)
            return result if return_details else result['success']

        current_app.logger.error(
            f'Failed to send Microsoft Graph email ({status_code}): {response_body}'
        )
        result = _email_result(False, response_body or 'Microsoft Graph did not accept the email.', status_code=status_code)
        return result if return_details else result['success']

    except error.HTTPError as exc:
        details = exc.read().decode('utf-8', errors='replace')
        current_app.logger.error(f'Error sending Microsoft Graph email: {exc.code} {details}')
        result = _email_result(False, details or str(exc), status_code=exc.code)
        return result if return_details else result['success']
    except Exception as exc:
        current_app.logger.error(f'Error sending Microsoft Graph email: {exc}')
        result = _email_result(False, str(exc))
        return result if return_details else result['success']


def send_initiative_creator_notification(initiative, creator, return_details=False):
    """Send the creator confirmation email after a new initiative is submitted."""
    subject = f'Savings Tracker : New initiative created - {initiative.id}'
    summary_html = _render_summary_table(_get_initiative_summary(initiative))
    message_html = f"""
    <p>Hello {html.escape(getattr(creator, 'full_name', 'User'))},</p>
    <p>Your initiative has been successfully created in Savings Tracker and submitted for review.</p>
    <p>The initiative summary is included below for reference.</p>
    """

    return send_email(
        to_addresses=_get_notification_recipient(creator, 'CREATOR_NOTIFICATION_TO_OVERRIDE'),
        subject=subject,
        html_content=_render_email_layout(message_html, summary_html),
        cc_addresses=current_app.config.get('PROCUREMENT_DATA_TEAM_EMAIL'),
        return_details=return_details,
    )


def send_initiative_review_notification(initiative, creator, reviewers=None, return_details=False):
    """Send the reviewer notification for a newly created initiative."""
    reviewer_override = current_app.config.get('REVIEW_NOTIFICATION_TO')
    if reviewer_override:
        to_addresses = reviewer_override
    else:
        to_addresses = [
            _get_user_email(reviewer)
            for reviewer in (reviewers or [])
            if getattr(reviewer, 'is_active', False)
        ]

    subject = f'Savings Tracker : New initiative(ID: {initiative.id}) is available for review'
    summary_html = _render_summary_table(_get_initiative_summary(initiative))
    message_html = f"""
    <p>Hello Team,</p>
    <p>A new initiative is now available for review in Savings Tracker.</p>
    <p>Please review the submission details below and take action when ready.</p>
    """

    return send_email(
        to_addresses=to_addresses,
        subject=subject,
        html_content=_render_email_layout(message_html, summary_html),
        cc_addresses=current_app.config.get('PROCUREMENT_DATA_TEAM_EMAIL'),
        return_details=return_details,
    )


def send_initiative_created_notification(initiative, creator, reviewers):
    """Send the creator and reviewer notifications for a newly created initiative."""
    creator_sent = send_initiative_creator_notification(initiative, creator)
    reviewer_sent = send_initiative_review_notification(initiative, creator, reviewers)
    return creator_sent or reviewer_sent


def send_initiative_approved_notification(initiative, approver, return_details=False):
    """Send notification when an initiative is approved."""
    subject = f'Savings Tracker : Initiative approved - #{initiative.id}'
    summary_html = _render_summary_table(_get_initiative_summary(initiative))
    approval_date = _format_value(getattr(initiative, 'review_date', None))
    message_html = f"""
    <p>Hello {html.escape(getattr(initiative.creator, 'full_name', 'User'))},</p>
    <p>Your initiative has been approved in Savings Tracker.</p>
    <p><strong>Approved By:</strong> {html.escape(getattr(approver, 'full_name', 'N/A'))}<br>
       <strong>Approval Date:</strong> {approval_date}</p>
    """

    return send_email(
        to_addresses=_get_notification_recipient(initiative.creator, 'APPROVAL_NOTIFICATION_TO_OVERRIDE'),
        subject=subject,
        html_content=_render_email_layout(message_html, summary_html),
        cc_addresses=current_app.config.get('PROCUREMENT_DATA_TEAM_EMAIL'),
        return_details=return_details,
    )


def send_initiative_rejected_notification(initiative, reviewer, comments, return_details=False):
    """Send notification when an initiative is rejected."""
    subject = f'Savings Tracker : Initiative rejected - #{initiative.id}'
    summary_html = _render_summary_table(_get_initiative_summary(initiative))
    rejection_reason = html.escape(comments or 'No comments provided.')
    message_html = f"""
    <p>Hello {html.escape(getattr(initiative.creator, 'full_name', 'User'))},</p>
    <p>Your initiative has been reviewed and requires updates before approval.</p>
    <p><strong>Reviewed By:</strong> {html.escape(getattr(reviewer, 'full_name', 'N/A'))}</p>
    <p><strong>Comments:</strong><br>{rejection_reason}</p>
    """

    return send_email(
        to_addresses=_get_notification_recipient(initiative.creator, 'CREATOR_NOTIFICATION_TO_OVERRIDE'),
        subject=subject,
        html_content=_render_email_layout(message_html, summary_html),
        cc_addresses=current_app.config.get('PROCUREMENT_DATA_TEAM_EMAIL'),
        return_details=return_details,
    )


def send_weekly_review_reminder(initiatives=None, return_details=False):
    """Send the weekly reminder email for initiatives pending review."""
    if initiatives is None:
        from app.models import Initiative

        initiatives = (
            Initiative.query
            .filter_by(status='Pending Review', is_deleted=False)
            .order_by(Initiative.created_at.asc())
            .all()
        )

    subject = 'Savings Tracker : Weekly Reminder Email'
    reminder_to = current_app.config.get('WEEKLY_REMINDER_TO') or current_app.config.get('REVIEW_NOTIFICATION_TO') or current_app.config.get('PROCUREMENT_DATA_TEAM_EMAIL')

    if initiatives:
        rows = ''.join(
            f"<tr>"
            f"<td style='padding:8px;border:1px solid #d9e1ea;'>#{initiative.id}</td>"
            f"<td style='padding:8px;border:1px solid #d9e1ea;'>{html.escape(initiative.initiative_type or 'N/A')}</td>"
            f"<td style='padding:8px;border:1px solid #d9e1ea;'>{html.escape(getattr(initiative.creator, 'full_name', 'N/A'))}</td>"
            f"<td style='padding:8px;border:1px solid #d9e1ea;'>{_format_value(getattr(initiative, 'created_at', None))}</td>"
            f"<td style='padding:8px;border:1px solid #d9e1ea;'>{_get_initiative_summary(initiative)['Vendor Name']}</td>"
            f"<td style='padding:8px;border:1px solid #d9e1ea;'>{html.escape(initiative.status or 'N/A')}</td>"
            f"</tr>"
            for initiative in initiatives[:50]
        )
        summary_html = f"""
        <table style='border-collapse:collapse;width:100%;max-width:900px;margin:16px 0;font-family:Arial,sans-serif;font-size:14px;'>
            <thead>
                <tr style='background:#112B46;color:#ffffff;'>
                    <th style='padding:8px;border:1px solid #d9e1ea;'>Initiative</th>
                    <th style='padding:8px;border:1px solid #d9e1ea;'>Type</th>
                    <th style='padding:8px;border:1px solid #d9e1ea;'>Created By</th>
                    <th style='padding:8px;border:1px solid #d9e1ea;'>Created On</th>
                    <th style='padding:8px;border:1px solid #d9e1ea;'>Vendor</th>
                    <th style='padding:8px;border:1px solid #d9e1ea;'>Status</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
        """
        message_html = f"""
        <p>Hello Team,</p>
        <p>This is the weekly reminder for initiatives that are still pending review in Savings Tracker.</p>
        <p><strong>Total Pending Review:</strong> {len(initiatives)}</p>
        """
    else:
        summary_html = ''
        message_html = """
        <p>Hello Team,</p>
        <p>This is the weekly reminder from Savings Tracker.</p>
        <p>There are currently no initiatives pending review.</p>
        """

    return send_email(
        to_addresses=reminder_to,
        subject=subject,
        html_content=_render_email_layout(message_html, summary_html),
        cc_addresses=current_app.config.get('PROCUREMENT_DATA_TEAM_EMAIL'),
        return_details=return_details,
    )
