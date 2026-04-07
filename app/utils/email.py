"""
Email notification utilities using SendGrid.
"""
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from flask import current_app


def send_email(to_addresses, subject, html_content, cc_addresses=None, bcc_addresses=None):
    """
    Send email using SendGrid.
    
    Args:
        to_addresses: List of email addresses or single email
        subject: Email subject
        html_content: HTML email body
        cc_addresses: List of CC addresses (optional)
        bcc_addresses: List of BCC addresses (optional)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get SendGrid API key
        api_key = current_app.config.get('SENDGRID_API_KEY')
        if not api_key:
            current_app.logger.warning('SendGrid API key not configured')
            return False

        # In development, redirect ALL recipients to the developer email
        if current_app.debug:
            dev_email = current_app.config.get('FROM_EMAIL', 'atong@montefiore.org')
            to_addresses = [dev_email]
            cc_addresses = None
            bcc_addresses = None
            subject = f'[DEV] {subject}'
        
        # Prepare from email
        from_email = Email(current_app.config.get('FROM_EMAIL', 'noreply@montefiore.org'))
        
        # Prepare to addresses
        if isinstance(to_addresses, str):
            to_addresses = [to_addresses]
        to_list = [To(email) for email in to_addresses]
        
        # Create message
        message = Mail(
            from_email=from_email,
            to_emails=to_list,
            subject=subject,
            html_content=html_content
        )
        
        # Add CC if provided
        if cc_addresses:
            if isinstance(cc_addresses, str):
                cc_addresses = [cc_addresses]
            for cc_email in cc_addresses:
                message.add_cc(cc_email)
        
        # Add BCC if provided
        if bcc_addresses:
            if isinstance(bcc_addresses, str):
                bcc_addresses = [bcc_addresses]
            for bcc_email in bcc_addresses:
                message.add_bcc(bcc_email)
        
        # Send email
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        
        if response.status_code in [200, 201, 202]:
            current_app.logger.info(f'Email sent successfully: {subject}')
            return True
        else:
            current_app.logger.error(f'Failed to send email: {response.status_code}')
            return False
            
    except Exception as e:
        current_app.logger.error(f'Error sending email: {str(e)}')
        return False


def send_initiative_created_notification(initiative, creator, reviewers):
    """Send notification when initiative is created."""
    subject = f'Savings Tracker: New initiative created - #{initiative.id}'
    
    # Get initiative details based on type
    if initiative.initiative_type == 'Cost Savings' and initiative.cost_savings:
        details = initiative.cost_savings
        vendor = details.vendor_name
        contract = details.contract_number
        category = details.contract_category
    elif initiative.initiative_type == 'Rebate' and initiative.rebate:
        details = initiative.rebate
        vendor = details.vendor_name
        contract = details.contract_number
        category = details.contract_category
    elif initiative.initiative_type == 'Cost Avoidance' and initiative.cost_avoidance:
        details = initiative.cost_avoidance
        vendor = details.vendor_name
        contract = details.contract_number
        category = details.contract_category
    else:
        vendor = 'N/A'
        contract = 'N/A'
        category = 'N/A'
    
    # Email to creator
    creator_html = f"""
    <p>You have successfully created a new initiative (ID: {initiative.id}) on {initiative.created_at.strftime('%m/%d/%Y %I:%M %p')}.</p>
    <p>&nbsp;</p>
    <p><strong>Initiative details:</strong></p>
    <ul>
        <li>Created By: {creator.full_name}</li>
        <li>Initiative Type: {initiative.initiative_type}</li>
        <li>Contract Category: {category}</li>
        <li>Contract Number: {contract}</li>
        <li>Vendor Name: {vendor}</li>
    </ul>
    <p>&nbsp;</p>
    <p>Please login to the Savings Tracker for more details:</p>
    <p><a href="{current_app.config.get('APP_URL')}">{current_app.config.get('APP_URL')}</a></p>
    <p>&nbsp;</p>
    <p><strong>-from Procurement Data Team</strong></p>
    """
    
    send_email(
        to_addresses=creator.email,
        subject=subject,
        html_content=creator_html,
        cc_addresses=current_app.config.get('PROCUREMENT_DATA_TEAM_EMAIL')
    )
    
    # Email to reviewers
    if reviewers:
        reviewer_emails = [r.email for r in reviewers if r.is_active]
        if reviewer_emails:
            reviewer_html = f"""
            <p>A new savings initiative has been created (ID: {initiative.id}) on {initiative.created_at.strftime('%m/%d/%Y %I:%M %p')} and waiting for your review.</p>
            <p>&nbsp;</p>
            <p><strong>Initiative details:</strong></p>
            <ul>
                <li>Created By: {creator.full_name}</li>
                <li>Initiative Type: {initiative.initiative_type}</li>
                <li>Contract Category: {category}</li>
                <li>Contract Number: {contract}</li>
                <li>Vendor Name: {vendor}</li>
            </ul>
            <p>&nbsp;</p>
            <p>Please login to the Savings Tracker to Approve/Reject the initiative:</p>
            <p><a href="{current_app.config.get('APP_URL')}">{current_app.config.get('APP_URL')}</a></p>
            <p>&nbsp;</p>
            <p><strong>-from Procurement Data Team</strong></p>
            """
            
            send_email(
                to_addresses=reviewer_emails,
                subject=f'Savings Tracker: New initiative (ID: {initiative.id}) available for review',
                html_content=reviewer_html,
                cc_addresses=current_app.config.get('PROCUREMENT_DATA_TEAM_EMAIL')
            )


def send_initiative_approved_notification(initiative, approver):
    """Send notification when initiative is approved."""
    subject = f'Savings Tracker: Initiative approved - #{initiative.id}'
    
    html = f"""
    <p>Initiative (ID: {initiative.id}) has been approved on {initiative.review_date.strftime('%m/%d/%Y %I:%M %p')}.</p>
    <p>&nbsp;</p>
    <p><strong>Initiative details:</strong></p>
    <ul>
        <li>Created By: {initiative.creator.full_name}</li>
        <li>Initiative Type: {initiative.initiative_type}</li>
        <li>Reviewed By: {approver.full_name}</li>
    </ul>
    <p>&nbsp;</p>
    <p>Please login to the Savings Tracker for more details:</p>
    <p><a href="{current_app.config.get('APP_URL')}">{current_app.config.get('APP_URL')}</a></p>
    <p>&nbsp;</p>
    <p><strong>-from Procurement Data Team</strong></p>
    """
    
    send_email(
        to_addresses=initiative.creator.email,
        subject=subject,
        html_content=html,
        cc_addresses=[current_app.config.get('PROCUREMENT_DATA_TEAM_EMAIL'), approver.email]
    )


def send_initiative_rejected_notification(initiative, reviewer, comments):
    """Send notification when initiative is rejected."""
    subject = f'Savings Tracker: Initiative rejected - #{initiative.id}'
    
    html = f"""
    <p>Initiative (ID: {initiative.id}) has been rejected on {initiative.review_date.strftime('%m/%d/%Y %I:%M %p')}.</p>
    <p>&nbsp;</p>
    <p><strong>Rejection reason:</strong></p>
    <p>{comments}</p>
    <p>&nbsp;</p>
    <p><strong>Initiative details:</strong></p>
    <ul>
        <li>Created By: {initiative.creator.full_name}</li>
        <li>Initiative Type: {initiative.initiative_type}</li>
        <li>Reviewed By: {reviewer.full_name}</li>
    </ul>
    <p>&nbsp;</p>
    <p>Please login to the Savings Tracker for more details:</p>
    <p><a href="{current_app.config.get('APP_URL')}">{current_app.config.get('APP_URL')}</a></p>
    <p>&nbsp;</p>
    <p><strong>-from Procurement Data Team</strong></p>
    """
    
    send_email(
        to_addresses=initiative.creator.email,
        subject=subject,
        html_content=html,
        cc_addresses=[current_app.config.get('PROCUREMENT_DATA_TEAM_EMAIL'), reviewer.email]
    )
