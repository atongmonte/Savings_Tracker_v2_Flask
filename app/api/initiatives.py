"""
Initiatives API endpoints (CRUD operations).
"""
import os
from flask import jsonify, request, g, current_app, send_file as flask_send_file
from sqlalchemy import or_, and_
from datetime import datetime
from app.utils.timezone import now_eastern
from werkzeug.utils import secure_filename
from app import db
from app.api import initiatives_bp
from app.models import Initiative, User, UserRole, FacilityAllocation, Facility, AuditLog, FileTracking
from app.utils.decorators import login_required, permission_required
from app.utils.email import send_initiative_approved_notification, send_initiative_rejected_notification
from app.utils.contract_categories import (
    get_contract_categories,
    get_prime_contract_numbers,
    get_prime_vendors_for_contract,
)


@initiatives_bp.route('', methods=['GET'])
@login_required
def get_initiatives():
    """
    Get all initiatives with filtering, pagination, and sorting.
    
    Query parameters:
        - page: Page number (default: 1)
        - per_page: Items per page (default: from config)
        - status: Filter by status
        - initiative_type: Filter by type
        - owner_id: Filter by owner
        - search: Search in initiative ID, owner, type, contract number/category, vendor name, status
        - sort_by: Field to sort by (default: created_at)
        - sort_order: asc or desc (default: desc)
    """
    user = g.current_user
    
    # Get query parameters
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 200)
    status = request.args.get('status')
    initiative_type = request.args.get('initiative_type')
    owner_id = request.args.get('owner_id', type=int)
    search = request.args.get('search', '')
    sort_by = request.args.get('sort_by', 'created_at')
    sort_order = request.args.get('sort_order', 'desc')
    include_deleted = request.args.get('include_deleted', 'false').lower() == 'true'
    initiative_year = request.args.get('initiative_year', type=int)
    
    # Build query — admins with delete_all can view deleted initiatives
    if include_deleted and user.has_permission('delete_all'):
        query = Initiative.query  # no is_deleted filter
    else:
        query = Initiative.query.filter_by(is_deleted=False)
    
    # Apply filters
    if status:
        query = query.filter_by(status=status)
    
    if initiative_type:
        query = query.filter_by(initiative_type=initiative_type)
    
    if owner_id:
        query = query.filter_by(owner_id=owner_id)
    
    # Track whether detail-table joins have been added
    from app.models import CostSavings, Rebate, CostAvoidance, User as OwnerUser
    from sqlalchemy import cast, String, func
    _detail_joined = False

    # Initiative year filter (by initiative date: start_date / rebate_check_date / avoidance_date)
    if initiative_year:
        if not _detail_joined:
            query = query \
                .outerjoin(CostSavings, CostSavings.initiative_id == Initiative.id) \
                .outerjoin(Rebate, Rebate.initiative_id == Initiative.id) \
                .outerjoin(CostAvoidance, CostAvoidance.initiative_id == Initiative.id)
            _detail_joined = True
        query = query.filter(
            or_(
                func.extract('year', CostSavings.start_date)       == initiative_year,
                func.extract('year', Rebate.rebate_check_date)     == initiative_year,
                func.extract('year', CostAvoidance.avoidance_date) == initiative_year,
            )
        )

    # Search filter
    if search:
        search_term = f'%{search}%'
        if not _detail_joined:
            query = query \
                .outerjoin(CostSavings, CostSavings.initiative_id == Initiative.id) \
                .outerjoin(Rebate, Rebate.initiative_id == Initiative.id) \
                .outerjoin(CostAvoidance, CostAvoidance.initiative_id == Initiative.id)
            _detail_joined = True
        query = query \
            .outerjoin(OwnerUser, OwnerUser.id == Initiative.owner_id) \
            .filter(
                or_(
                    cast(Initiative.id, String).ilike(search_term),
                    Initiative.initiative_type.ilike(search_term),
                    Initiative.status.ilike(search_term),
                    OwnerUser.full_name.ilike(search_term),
                    OwnerUser.username.ilike(search_term),
                    CostSavings.contract_number.ilike(search_term),
                    CostSavings.contract_category.ilike(search_term),
                    CostSavings.vendor_name.ilike(search_term),
                    Rebate.contract_number.ilike(search_term),
                    Rebate.contract_category.ilike(search_term),
                    Rebate.vendor_name.ilike(search_term),
                    CostAvoidance.contract_number.ilike(search_term),
                    CostAvoidance.contract_category.ilike(search_term),
                    CostAvoidance.vendor_name.ilike(search_term)
                )
            )

    # Sorting
    if sort_by == 'amount':
        # Add joins if not already present
        if not _detail_joined:
            query = query \
                .outerjoin(CostSavings, CostSavings.initiative_id == Initiative.id) \
                .outerjoin(Rebate, Rebate.initiative_id == Initiative.id) \
                .outerjoin(CostAvoidance, CostAvoidance.initiative_id == Initiative.id)
        amount_expr = func.abs(func.coalesce(
            CostSavings.total_savings_amount,
            Rebate.rebate_amount,
            CostAvoidance.avoidance_amount,
            0
        ))
        query = query.order_by(amount_expr.asc() if sort_order == 'asc' else amount_expr.desc())
    elif sort_by == 'initiative_date':
        if not _detail_joined:
            query = query \
                .outerjoin(CostSavings, CostSavings.initiative_id == Initiative.id) \
                .outerjoin(Rebate, Rebate.initiative_id == Initiative.id) \
                .outerjoin(CostAvoidance, CostAvoidance.initiative_id == Initiative.id)
        date_expr = func.coalesce(
            CostSavings.start_date,
            Rebate.rebate_check_date,
            CostAvoidance.avoidance_date
        )
        query = query.order_by(date_expr.asc() if sort_order == 'asc' else date_expr.desc())
    elif hasattr(Initiative, sort_by):
        order_column = getattr(Initiative, sort_by)
        if sort_order == 'asc':
            query = query.order_by(order_column.asc())
        else:
            query = query.order_by(order_column.desc())
    
    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Build response
    return jsonify({
        'initiatives': [initiative.to_dict(include_details=True) for initiative in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page,
        'per_page': per_page
    }), 200


def _reconcile_missing_files(initiative):
    """
    Check every active FileTracking record for this initiative.
    If the physical file no longer exists on disk, soft-delete the DB record
    so the frontend never shows a broken link.
    Returns the number of records that were auto-cleaned.
    """
    cleaned = 0
    for record in initiative.files:
        if record.is_deleted:
            continue
        if record.file_path and not os.path.exists(record.file_path):
            record.is_deleted   = True
            record.deleted_at   = now_eastern()
            # deleted_by_id left NULL — indicates system/auto-reconciliation
            cleaned += 1
    if cleaned:
        db.session.commit()
    return cleaned


@initiatives_bp.route('/<int:initiative_id>', methods=['GET'])
@login_required
def get_initiative(initiative_id):
    """Get a single initiative by ID."""
    initiative = Initiative.query.filter_by(id=initiative_id, is_deleted=False).first()

    if not initiative:
        return jsonify({'error': 'Initiative not found'}), 404

    # Auto-reconcile any files that were deleted from disk outside the application
    _reconcile_missing_files(initiative)

    return jsonify(initiative.to_dict(include_details=True)), 200


@initiatives_bp.route('/contract-categories', methods=['GET'])
@login_required
def get_contract_category_options():
    """Return contract categories for async dropdown loading."""
    return jsonify({'contract_categories': get_contract_categories()}), 200


@initiatives_bp.route('/prime-contract-lookup', methods=['GET'])
@login_required
def get_prime_contract_lookup_options():
    """Return PRIME contract number suggestions and vendor suggestions for a contract."""
    contract_number = (request.args.get('contract_number') or '').strip()

    return jsonify({
        'contract_numbers': get_prime_contract_numbers(),
        'vendors': get_prime_vendors_for_contract(contract_number) if contract_number else [],
    }), 200


@initiatives_bp.route('/<int:initiative_id>', methods=['DELETE'])
@login_required
def delete_initiative(initiative_id):
    """
    Soft delete an initiative.
    Users can delete their own initiatives.
    Users with delete_all permission can delete any initiative.
    """
    user = g.current_user
    initiative = Initiative.query.filter_by(id=initiative_id, is_deleted=False).first()
    
    if not initiative:
        return jsonify({'error': 'Initiative not found'}), 404
    
    # Check permissions
    can_delete = False
    if user.has_permission('delete_all'):
        can_delete = True
    elif user.has_permission('delete_own') and initiative.created_by_id == user.id:
        can_delete = True
    
    if not can_delete:
        return jsonify({'error': 'Insufficient permissions to delete this initiative'}), 403
    
    try:
        # Soft delete
        initiative.soft_delete(user.id)
        
        # Create audit log
        audit = AuditLog(
            initiative_id=initiative.id,
            action='DELETE',
            table_name='initiatives',
            record_id=initiative.id,
            user_id=user.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        audit.set_old_values({'is_deleted': False})
        audit.set_new_values({'is_deleted': True, 'deleted_at': now_eastern().isoformat()})
        
        db.session.add(audit)
        db.session.commit()
        
        return jsonify({'message': 'Initiative deleted successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@initiatives_bp.route('/<int:initiative_id>/restore', methods=['POST'])
@permission_required('delete_all')
def restore_initiative(initiative_id):
    """
    Restore (un-delete) a soft-deleted initiative.
    Requires delete_all permission (admin only).
    """
    user = g.current_user
    initiative = Initiative.query.filter_by(id=initiative_id, is_deleted=True).first()
    
    if not initiative:
        return jsonify({'error': 'Deleted initiative not found'}), 404
    
    try:
        initiative.is_deleted   = False
        initiative.deleted_at   = None
        initiative.deleted_by_id = None
        initiative.updated_at   = now_eastern()
        
        audit = AuditLog(
            initiative_id=initiative.id,
            action='RESTORE',
            table_name='initiatives',
            record_id=initiative.id,
            user_id=user.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        audit.set_old_values({'is_deleted': True})
        audit.set_new_values({'is_deleted': False})
        
        db.session.add(audit)
        db.session.commit()
        
        return jsonify({'message': 'Initiative restored successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@initiatives_bp.route('/<int:initiative_id>/approve', methods=['POST'])
@permission_required('approve')
def approve_initiative(initiative_id):
    """Approve an initiative."""
    user = g.current_user
    initiative = Initiative.query.filter_by(id=initiative_id, is_deleted=False).first()
    
    if not initiative:
        return jsonify({'error': 'Initiative not found'}), 404
    
    if initiative.status != 'Pending Review':
        return jsonify({'error': 'Initiative is not pending review'}), 400
    
    try:
        # Update initiative
        old_status = initiative.status
        data = request.get_json(silent=True) or {}
        initiative.status = 'Approved'
        initiative.reviewed_by_id = user.id
        initiative.review_date = now_eastern()
        initiative.review_comments = data.get('comments', '')
        initiative.updated_at = now_eastern()
        
        # Create audit log
        audit = AuditLog(
            initiative_id=initiative.id,
            action='APPROVE',
            table_name='initiatives',
            record_id=initiative.id,
            user_id=user.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        audit.set_old_values({'status': old_status})
        audit.set_new_values({
            'status': 'Approved',
            'reviewed_by_id': user.id,
            'review_date': initiative.review_date.isoformat()
        })
        
        db.session.add(audit)
        db.session.commit()
        
        # Send email notification
        send_initiative_approved_notification(initiative, user)
        
        return jsonify({
            'message': 'Initiative approved successfully',
            'initiative': initiative.to_dict(include_details=True)
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@initiatives_bp.route('/<int:initiative_id>/reject', methods=['POST'])
@permission_required('approve')
def reject_initiative(initiative_id):
    """Reject an initiative with comments."""
    user = g.current_user
    data = request.get_json()
    
    if not data or 'comments' not in data:
        return jsonify({'error': 'Rejection comments are required'}), 400
    
    initiative = Initiative.query.filter_by(id=initiative_id, is_deleted=False).first()
    
    if not initiative:
        return jsonify({'error': 'Initiative not found'}), 404
    
    if initiative.status not in ('Pending Review', 'Approved'):
        return jsonify({'error': 'Only Pending Review or Approved initiatives can be rejected'}), 400
    
    try:
        # Update initiative
        old_status = initiative.status
        initiative.status = 'Rejected'
        initiative.reviewed_by_id = user.id
        initiative.review_date = now_eastern()
        initiative.review_comments = data['comments']
        initiative.updated_at = now_eastern()
        
        # Create audit log
        audit = AuditLog(
            initiative_id=initiative.id,
            action='REJECT',
            table_name='initiatives',
            record_id=initiative.id,
            user_id=user.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        audit.set_old_values({'status': old_status})
        audit.set_new_values({
            'status': 'Rejected',
            'reviewed_by_id': user.id,
            'review_date': initiative.review_date.isoformat(),
            'review_comments': data['comments']
        })
        
        db.session.add(audit)
        db.session.commit()
        
        # Send email notification
        send_initiative_rejected_notification(initiative, user, data['comments'])
        
        return jsonify({
            'message': 'Initiative rejected successfully',
            'initiative': initiative.to_dict(include_details=True)
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@initiatives_bp.route('/<int:initiative_id>/unapprove', methods=['POST'])
@login_required
def unapprove_initiative(initiative_id):
    """Revert an Approved initiative back to Pending Review (reviewer/admin only)."""
    user = g.current_user
    if not (user.has_permission('approve') or user.has_permission('review')):
        return jsonify({'error': 'Permission denied'}), 403

    initiative = Initiative.query.filter_by(id=initiative_id, is_deleted=False).first()
    if not initiative:
        return jsonify({'error': 'Initiative not found'}), 404

    if initiative.status != 'Approved':
        return jsonify({'error': 'Only approved initiatives can be reverted to pending'}), 400

    try:
        data = request.get_json() or {}
        old_status = initiative.status
        initiative.status = 'Pending Review'
        initiative.reviewed_by_id = user.id
        initiative.review_date = now_eastern()
        initiative.review_comments = data.get('comments', '')
        initiative.updated_at = now_eastern()

        # Ensure the status change is recorded in audit log
        existing = AuditLog.query.filter_by(
            initiative_id=initiative.id, action='UNAPPROVE'
        ).first()
        audit = AuditLog(
            initiative_id=initiative.id,
            action='UNAPPROVE',
            table_name='initiatives',
            record_id=initiative.id,
            user_id=user.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        audit.set_old_values({'status': old_status})
        audit.set_new_values({
            'status': 'Pending Review',
            'reviewed_by_id': user.id,
            'review_date': initiative.review_date.isoformat(),
            'review_comments': data.get('comments', '')
        })

        db.session.add(audit)
        db.session.commit()

        return jsonify({
            'message': 'Initiative reverted to Pending Review',
            'initiative': initiative.to_dict(include_details=True)
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@initiatives_bp.route('/<int:initiative_id>/revert', methods=['POST'])
@login_required
def revert_initiative(initiative_id):
    """Revert a rejected initiative back to Pending Review, clearing review comments."""
    user = g.current_user
    if not (user.has_permission('approve') or user.has_permission('review')):
        return jsonify({'error': 'Permission denied'}), 403

    initiative = Initiative.query.filter_by(id=initiative_id, is_deleted=False).first()

    if not initiative:
        return jsonify({'error': 'Initiative not found'}), 404

    if initiative.status != 'Rejected':
        return jsonify({'error': 'Only rejected initiatives can be reverted'}), 400

    try:
        old_status = initiative.status
        old_comments = initiative.review_comments
        initiative.status = 'Pending Review'
        initiative.review_comments = ''
        initiative.reviewed_by_id = user.id
        initiative.review_date = now_eastern()
        initiative.updated_at = now_eastern()

        audit = AuditLog(
            initiative_id=initiative.id,
            action='REVERT',
            table_name='initiatives',
            record_id=initiative.id,
            user_id=user.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        audit.set_old_values({'status': old_status, 'review_comments': old_comments})
        audit.set_new_values({'status': 'Pending Review', 'review_comments': ''})

        db.session.add(audit)
        db.session.commit()

        return jsonify({
            'message': 'Initiative reverted to Pending Review',
            'initiative': initiative.to_dict(include_details=True)
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@initiatives_bp.route('/<int:initiative_id>/files', methods=['POST'])
@login_required
def upload_files(initiative_id):
    """Upload file attachments to an initiative."""
    user = g.current_user
    initiative = Initiative.query.filter_by(id=initiative_id, is_deleted=False).first()
    if not initiative:
        return jsonify({'error': 'Initiative not found'}), 404

    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400

    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'error': 'No files selected'}), 400

    storage_base = current_app.config.get('FILE_STORAGE_PATH')
    if not storage_base:
        fallback_path = current_app.config.get('UPLOADS_FALLBACK_PATH', 'uploads')
        storage_base = fallback_path if os.path.isabs(fallback_path) else os.path.join(
            current_app.root_path, '..', fallback_path
        )
    # python-dotenv reads \\\\ from .env as 4 literal backslashes; normalize
    # any UNC path that starts with multiple backslashes back to exactly \\
    if storage_base:
        stripped = storage_base.lstrip('\\')
        if stripped != storage_base:          # started with backslashes → UNC
            storage_base = '\\\\' + stripped
    storage_base = os.path.normpath(storage_base)
    initiative_folder = os.path.join(storage_base, str(initiative_id))
    os.makedirs(initiative_folder, exist_ok=True)

    allowed = current_app.config.get('ALLOWED_EXTENSIONS', set())
    saved = []
    for f in files:
        if not f.filename:
            continue
        original_name = secure_filename(f.filename)
        ext = os.path.splitext(original_name)[1].lower().lstrip('.')
        if allowed and ext not in allowed:
            continue
        file_path = os.path.join(initiative_folder, original_name)
        f.save(file_path)
        record = FileTracking(
            initiative_id=initiative_id,
            file_name=original_name,
            file_path=file_path,
            file_size=os.path.getsize(file_path),
            file_type=ext,
            uploaded_by_id=user.id,
        )
        db.session.add(record)
        saved.append(record)

    if not saved:
        return jsonify({'error': 'No valid files were uploaded (check allowed extensions)'}), 400

    db.session.commit()
    return jsonify({
        'message': f'{len(saved)} file(s) uploaded',
        'files': [f.to_dict() for f in initiative.files if not f.is_deleted]
    }), 201


@initiatives_bp.route('/<int:initiative_id>/files/<int:file_id>/download', methods=['GET'])
@login_required
def download_file(initiative_id, file_id):
    """Download a file attachment."""
    file_record = FileTracking.query.filter_by(
        id=file_id, initiative_id=initiative_id, is_deleted=False
    ).first()
    if not file_record:
        return jsonify({'error': 'File not found'}), 404
    if not os.path.exists(file_record.file_path):
        return jsonify({'error': 'File not found on disk'}), 404
    return flask_send_file(
        file_record.file_path,
        download_name=file_record.file_name,
        as_attachment=True
    )


@initiatives_bp.route('/<int:initiative_id>/files/<int:file_id>', methods=['DELETE'])
@login_required
def delete_file(initiative_id, file_id):
    """Delete a file attachment (soft-delete DB record + remove from disk)."""
    user = g.current_user
    file_record = FileTracking.query.filter_by(
        id=file_id, initiative_id=initiative_id, is_deleted=False
    ).first()
    if not file_record:
        return jsonify({'error': 'File not found'}), 404

    # Block deletion if this is the last remaining file
    remaining = FileTracking.query.filter_by(
        initiative_id=initiative_id, is_deleted=False
    ).count()
    if remaining <= 1:
        return jsonify({'error': 'At least one file attachment is required. Upload a replacement before deleting this one.'}), 400

    # Physically remove from disk
    try:
        if file_record.file_path and os.path.exists(file_record.file_path):
            os.remove(file_record.file_path)
    except OSError as e:
        return jsonify({'error': f'Could not delete file from disk: {e}'}), 500

    file_record.is_deleted = True
    file_record.deleted_at = now_eastern()
    file_record.deleted_by_id = user.id
    db.session.commit()
    initiative = Initiative.query.get(initiative_id)
    return jsonify({
        'message': 'File deleted',
        'files': [f.to_dict() for f in initiative.files if not f.is_deleted]
    }), 200


@initiatives_bp.route('/<int:initiative_id>/audit-log', methods=['GET'])
@login_required
def get_initiative_audit_log(initiative_id):
    """Get audit log for an initiative."""
    initiative = Initiative.query.filter_by(id=initiative_id).first()
    
    if not initiative:
        return jsonify({'error': 'Initiative not found'}), 404
    
    reviewer_actions = ('APPROVE', 'REJECT', 'REVERT', 'UNAPPROVE')
    audit_logs = AuditLog.query.filter(
        AuditLog.initiative_id == initiative_id,
        AuditLog.action.in_(reviewer_actions)
    ).order_by(AuditLog.created_at.desc()).all()
    
    return jsonify({
        'audit_logs': [log.to_dict() for log in audit_logs]
    }), 200


@initiatives_bp.route('/dashboard-stats', methods=['GET'])
@login_required
def get_dashboard_stats():
    """Lightweight aggregate stats for the dashboard cards (respects filters + optional year)."""
    from sqlalchemy import func, extract
    from app.models import CostSavings, Rebate, CostAvoidance, User as OwnerUser
    from datetime import date

    user = g.current_user
    status          = request.args.get('status')
    search          = request.args.get('search', '')
    include_deleted = request.args.get('include_deleted', 'false').lower() == 'true'
    stats_year      = request.args.get('stats_year', type=int)  # None = all time

    # Base query (same filters as get_initiatives)
    if include_deleted and user.has_permission('delete_all'):
        base_q = Initiative.query
    else:
        base_q = Initiative.query.filter_by(is_deleted=False)

    if status:
        base_q = base_q.filter_by(status=status)

    if search:
        from sqlalchemy import cast, String, or_
        search_term = f'%{search}%'
        base_q = base_q \
            .outerjoin(CostSavings, CostSavings.initiative_id == Initiative.id) \
            .outerjoin(Rebate, Rebate.initiative_id == Initiative.id) \
            .outerjoin(CostAvoidance, CostAvoidance.initiative_id == Initiative.id) \
            .outerjoin(OwnerUser, OwnerUser.id == Initiative.owner_id) \
            .filter(or_(
                cast(Initiative.id, String).ilike(search_term),
                Initiative.initiative_type.ilike(search_term),
                Initiative.status.ilike(search_term),
                OwnerUser.full_name.ilike(search_term),
                OwnerUser.username.ilike(search_term),
                CostSavings.contract_number.ilike(search_term),
                CostSavings.contract_category.ilike(search_term),
                CostSavings.vendor_name.ilike(search_term),
                Rebate.contract_number.ilike(search_term),
                Rebate.contract_category.ilike(search_term),
                Rebate.vendor_name.ilike(search_term),
                CostAvoidance.contract_number.ilike(search_term),
                CostAvoidance.contract_category.ilike(search_term),
                CostAvoidance.vendor_name.ilike(search_term),
            ))

    # Collect matching IDs (cheap — no serialization)
    matching_ids = [row.id for row in base_q.with_entities(Initiative.id).all()]

    if not matching_ids:
        return jsonify({'total': 0, 'savings': 0, 'rebate': 0, 'avoidance': 0}), 200

    if stats_year:
        year_start = date(stats_year, 1, 1)
        year_end   = date(stats_year, 12, 31)

        # ── Cost Savings: prorate annual_savings_amount by days overlapping the year ──
        cs_rows = db.session.query(
            CostSavings.annual_savings_amount,
            CostSavings.start_date,
            CostSavings.end_date
        ).filter(CostSavings.initiative_id.in_(matching_ids)).all()

        savings_sum = 0.0
        cs_count = 0
        for annual, sd, ed in cs_rows:
            if not annual:
                continue
            # If dates are missing, assume it falls in the year (use full annual amount)
            if not sd or not ed:
                savings_sum += float(annual)
                cs_count += 1
                continue
            overlap_start = max(sd, year_start)
            overlap_end   = min(ed, year_end)
            overlap_days  = (overlap_end - overlap_start).days + 1
            if overlap_days <= 0:
                continue  # contract doesn't touch this year
            contract_days = (ed - sd).days + 1 or 365
            savings_sum += float(annual) * overlap_days / contract_days
            cs_count += 1

        # ── Rebates: filter by transaction (rebate_check_date) year ──
        rebate_sum = db.session.query(func.sum(Rebate.rebate_amount)) \
            .filter(
                Rebate.initiative_id.in_(matching_ids),
                func.extract('year', Rebate.rebate_check_date) == stats_year
            ).scalar() or 0

        # ── Cost Avoidance: filter by avoidance_date year ──
        avoidance_sum = db.session.query(func.sum(CostAvoidance.avoidance_amount)) \
            .filter(
                CostAvoidance.initiative_id.in_(matching_ids),
                func.extract('year', CostAvoidance.avoidance_date) == stats_year
            ).scalar() or 0

        # Total count = initiatives with any activity in the year
        cs_ids_in_year = {row.initiative_id for row in db.session.query(CostSavings.initiative_id)
            .filter(CostSavings.initiative_id.in_(matching_ids),
                    CostSavings.end_date >= year_start,
                    CostSavings.start_date <= year_end).all()}
        rb_ids_in_year = {row.initiative_id for row in db.session.query(Rebate.initiative_id)
            .filter(Rebate.initiative_id.in_(matching_ids),
                    func.extract('year', Rebate.rebate_check_date) == stats_year).all()}
        ca_ids_in_year = {row.initiative_id for row in db.session.query(CostAvoidance.initiative_id)
            .filter(CostAvoidance.initiative_id.in_(matching_ids),
                    func.extract('year', CostAvoidance.avoidance_date) == stats_year).all()}
        total = len(cs_ids_in_year | rb_ids_in_year | ca_ids_in_year)

    else:
        # All-time totals
        savings_sum   = db.session.query(func.sum(CostSavings.total_savings_amount)) \
                          .filter(CostSavings.initiative_id.in_(matching_ids)).scalar() or 0
        rebate_sum    = db.session.query(func.sum(Rebate.rebate_amount)) \
                          .filter(Rebate.initiative_id.in_(matching_ids)).scalar() or 0
        avoidance_sum = db.session.query(func.sum(CostAvoidance.avoidance_amount)) \
                          .filter(CostAvoidance.initiative_id.in_(matching_ids)).scalar() or 0
        total = len(matching_ids)

    return jsonify({
        'total':     total,
        'savings':   float(savings_sum),
        'rebate':    float(rebate_sum),
        'avoidance': float(avoidance_sum),
    }), 200


@initiatives_bp.route('/statistics', methods=['GET'])
@login_required
def get_statistics():
    """Get initiative statistics."""
    from sqlalchemy import func
    
    # Total initiatives by status
    status_stats = db.session.query(
        Initiative.status,
        func.count(Initiative.id).label('count')
    ).filter_by(is_deleted=False).group_by(Initiative.status).all()
    
    # Total initiatives by type
    type_stats = db.session.query(
        Initiative.initiative_type,
        func.count(Initiative.id).label('count')
    ).filter_by(is_deleted=False).group_by(Initiative.initiative_type).all()
    
    # Total by owner
    owner_stats = db.session.query(
        User.full_name,
        func.count(Initiative.id).label('count')
    ).join(Initiative.owner).filter(Initiative.is_deleted == False)\
        .group_by(User.full_name).all()
    
    return jsonify({
        'by_status': [{'status': status, 'count': count} for status, count in status_stats],
        'by_type': [{'type': type_, 'count': count} for type_, count in type_stats],
        'by_owner': [{'owner': owner, 'count': count} for owner, count in owner_stats]
    }), 200
