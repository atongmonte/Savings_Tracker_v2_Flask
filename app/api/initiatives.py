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
from app.utils.sp_helpers import run_distribution_procedure
from app.utils.contract_categories import (
    get_contract_categories,
    get_prime_contract_numbers,
    get_prime_vendors_for_contract,
)


READ_ONLY_COST_SAVINGS_ERROR = 'Cost Savings initiatives are read-only.'


def _is_locked_cost_savings(initiative):
    return initiative and initiative.initiative_type == 'Cost Savings'


def _locked_cost_savings_response():
    return jsonify({'error': READ_ONLY_COST_SAVINGS_ERROR}), 403


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
        - sort_by: Field to sort by (default: updated_at)
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
    sort_by = request.args.get('sort_by', 'updated_at')
    sort_order = request.args.get('sort_order', 'desc')
    include_deleted = request.args.get('include_deleted', 'false').lower() == 'true'
    initiative_year = request.args.get('initiative_year', type=int)
    deleted_only = (status or '').strip().lower() == 'deleted'
    
    # Build query — deleted-only mode is driven by status=Deleted.
    if deleted_only:
        if user.has_permission('delete_all'):
            query = Initiative.query.filter_by(is_deleted=True)
        else:
            query = Initiative.query.filter_by(id=-1)
    elif include_deleted and user.has_permission('delete_all'):
        query = Initiative.query  # no is_deleted filter
    else:
        query = Initiative.query.filter_by(is_deleted=False)
    
    # Apply filters
    if status and not deleted_only:
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
                and_(
                    CostSavings.start_date.is_(None),
                    Rebate.rebate_check_date.is_(None),
                    CostAvoidance.avoidance_date.is_(None),
                    func.extract('year', Initiative.created_at) == initiative_year,
                ),
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
                    Rebate.wave_category.ilike(search_term),
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
            CostAvoidance.avoidance_date,
            func.cast(Initiative.created_at, db.Date)
        )
        if sort_order == 'asc':
            query = query.order_by(date_expr.asc(), Initiative.id.asc())
        else:
            query = query.order_by(date_expr.desc(), Initiative.id.desc())
    elif hasattr(Initiative, sort_by):
        order_column = getattr(Initiative, sort_by)
        if sort_order == 'asc':
            query = query.order_by(order_column.asc(), Initiative.id.asc())
        else:
            query = query.order_by(order_column.desc(), Initiative.id.desc())
    
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

    # Auto-reconcile any files that were deleted from disk outside the application.
    # Cost Savings records are locked to read-only, so avoid DB writes while viewing.
    if not _is_locked_cost_savings(initiative):
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


@initiatives_bp.route('/<int:initiative_id>', methods=['POST'])
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

    if _is_locked_cost_savings(initiative):
        return _locked_cost_savings_response()
    
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

        run_distribution_procedure()
        
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

    if _is_locked_cost_savings(initiative):
        return _locked_cost_savings_response()
    
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

    if _is_locked_cost_savings(initiative):
        return _locked_cost_savings_response()
    
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

        run_distribution_procedure()
        
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

    if _is_locked_cost_savings(initiative):
        return _locked_cost_savings_response()
    
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

        run_distribution_procedure()
        
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

    if _is_locked_cost_savings(initiative):
        return _locked_cost_savings_response()

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

        run_distribution_procedure()

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

    if _is_locked_cost_savings(initiative):
        return _locked_cost_savings_response()

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

        run_distribution_procedure()

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

    if _is_locked_cost_savings(initiative):
        return _locked_cost_savings_response()

    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400

    files = request.files.getlist('files')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'error': 'No files selected'}), 400

    _reconcile_missing_files(initiative)

    allowed = current_app.config.get('ALLOWED_EXTENSIONS', set())
    valid_uploads = []
    seen_upload_names = {}
    duplicate_names = set()
    for f in files:
        if not f.filename:
            continue
        original_name = secure_filename(f.filename)
        ext = os.path.splitext(original_name)[1].lower().lstrip('.')
        if allowed and ext not in allowed:
            continue

        name_key = original_name.casefold()
        if name_key in seen_upload_names:
            duplicate_names.add(original_name)
        else:
            seen_upload_names[name_key] = original_name
        valid_uploads.append((f, original_name, ext))

    if not valid_uploads:
        return jsonify({'error': 'No valid files were uploaded (check allowed extensions)'}), 400

    if duplicate_names:
        names = ', '.join(sorted(duplicate_names, key=str.lower))
        return jsonify({
            'error': f'Duplicate file name(s) are not allowed: {names}'
        }), 400

    force_new_names = {
        secure_filename(name).casefold()
        for name in request.form.getlist('force_new_names')
        if name
    }

    active_files_by_name = {
        (record.file_name or '').casefold(): record
        for record in FileTracking.query.filter_by(
            initiative_id=initiative_id,
            is_deleted=False
        ).all()
    }

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

    saved = []
    for f, original_name, ext in valid_uploads:
        original_name_key = original_name.casefold()
        existing_record = None if original_name_key in force_new_names else active_files_by_name.get(original_name_key)
        file_path = existing_record.file_path if existing_record else os.path.join(initiative_folder, original_name)
        f.save(file_path)
        if existing_record:
            record = existing_record
            record.file_name = original_name
            record.file_path = file_path
            record.file_size = os.path.getsize(file_path)
            record.file_type = ext
            record.uploaded_by_id = user.id
            record.upload_time = now_eastern()
            record.updated_at = now_eastern()
        else:
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

    db.session.commit()
    return jsonify({
        'message': f'{len(saved)} file(s) uploaded or updated',
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


@initiatives_bp.route('/<int:initiative_id>/files/<int:file_id>', methods=['POST'])
@login_required
def delete_file(initiative_id, file_id):
    """Delete a file attachment (soft-delete DB record + remove from disk)."""
    user = g.current_user

    initiative = Initiative.query.filter_by(id=initiative_id, is_deleted=False).first()
    if not initiative:
        return jsonify({'error': 'Initiative not found'}), 404

    if _is_locked_cost_savings(initiative):
        return _locked_cost_savings_response()

    # Auto-clean any files already removed from disk so the "remaining" count
    # only reflects files that actually exist, and ghost records don't block deletions.
    _reconcile_missing_files(initiative)

    file_record = FileTracking.query.filter_by(
        id=file_id, initiative_id=initiative_id, is_deleted=False
    ).first()
    if not file_record:
        # Already deleted (possibly just cleaned up by reconcile) — return current file list
        return jsonify({
            'message': 'File already removed',
            'files': [f.to_dict() for f in initiative.files if not f.is_deleted]
        }), 200

    # Block deletion if this is the last remaining file
    remaining = FileTracking.query.filter_by(
        initiative_id=initiative_id, is_deleted=False
    ).count()
    if remaining <= 1:
        return jsonify({'error': 'At least one file attachment is required. Upload another attachment before deleting this one.'}), 400

    # Physically remove from disk, but only when no other active record shares
    # the same path. This protects older duplicate records or externally-created
    # path conflicts from deleting content still referenced by another record.
    has_path_conflict = file_record.file_path and FileTracking.query.filter(
        FileTracking.initiative_id == initiative_id,
        FileTracking.is_deleted == False,
        FileTracking.file_path == file_record.file_path,
        FileTracking.id != file_id
    ).count() > 0
    if not has_path_conflict:
        try:
            if file_record.file_path and os.path.exists(file_record.file_path):
                os.remove(file_record.file_path)
        except OSError:
            # Physical removal failed — still soft-delete the DB record so
            # the broken reference doesn't surface to users again.
            pass

    file_record.is_deleted = True
    file_record.deleted_at = now_eastern()
    file_record.deleted_by_id = user.id
    db.session.commit()
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
    deleted_only    = (status or '').strip().lower() == 'deleted'

    # Base query (same filtering semantics as get_initiatives)
    if deleted_only:
        if user.has_permission('delete_all'):
            base_q = Initiative.query.filter_by(is_deleted=True)
        else:
            base_q = Initiative.query.filter_by(id=-1)
    elif include_deleted and user.has_permission('delete_all'):
        base_q = Initiative.query
    else:
        base_q = Initiative.query.filter_by(is_deleted=False)

    if status and not deleted_only:
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

    empty = {
        'total': 0,
        'savings': 0, 'savings_approved': 0, 'savings_pending': 0,
        'rebate': 0, 'rebate_approved': 0, 'rebate_pending': 0,
        'avoidance': 0, 'avoidance_approved': 0, 'avoidance_pending': 0,
    }
    if not matching_ids:
        return jsonify(empty), 200

    # Split matching IDs by status for the approved/pending breakdown
    status_rows = db.session.query(Initiative.id, Initiative.status) \
        .filter(Initiative.id.in_(matching_ids)).all()
    approved_ids = [r.id for r in status_rows if r.status == 'Approved']
    pending_ids  = [r.id for r in status_rows if r.status == 'Pending Review']

    def _calc_stats(ids):
        """Compute (savings, rebate, avoidance) for a set of initiative IDs."""
        if not ids:
            return 0.0, 0.0, 0.0

        if stats_year:
            _year_start = date(stats_year, 1, 1)
            _year_end   = date(stats_year, 12, 31)

            cs_rows = db.session.query(
                CostSavings.total_savings_amount,
                CostSavings.annual_savings_amount,
                CostSavings.start_date,
                CostSavings.end_date
            ).filter(CostSavings.initiative_id.in_(ids)).all()

            _savings = 0.0
            for total_savings, annual, sd, ed in cs_rows:
                if not sd or not ed:
                    if annual:
                        _savings += float(annual)
                    continue
                if not total_savings:
                    continue
                overlap_start = max(sd, _year_start)
                overlap_end   = min(ed, _year_end)
                overlap_days  = (overlap_end - overlap_start).days + 1
                if overlap_days <= 0:
                    continue
                contract_days = (ed - sd).days + 1 or 365
                _savings += float(total_savings) * overlap_days / contract_days

            _rebate = db.session.query(func.sum(Rebate.rebate_amount)) \
                .filter(
                    Rebate.initiative_id.in_(ids),
                    func.extract('year', Rebate.rebate_check_date) == stats_year
                ).scalar() or 0

            _avoidance = db.session.query(func.sum(CostAvoidance.avoidance_amount)) \
                .filter(
                    CostAvoidance.initiative_id.in_(ids),
                    func.extract('year', CostAvoidance.avoidance_date) == stats_year
                ).scalar() or 0

            return _savings, float(_rebate), float(_avoidance)
        else:
            _savings   = db.session.query(func.sum(CostSavings.total_savings_amount)) \
                           .filter(CostSavings.initiative_id.in_(ids)).scalar() or 0
            _rebate    = db.session.query(func.sum(Rebate.rebate_amount)) \
                           .filter(Rebate.initiative_id.in_(ids)).scalar() or 0
            _avoidance = db.session.query(func.sum(CostAvoidance.avoidance_amount)) \
                           .filter(CostAvoidance.initiative_id.in_(ids)).scalar() or 0
            return float(_savings), float(_rebate), float(_avoidance)

    savings_sum,   rebate_sum,   avoidance_sum   = _calc_stats(matching_ids)
    savings_appv,  rebate_appv,  avoidance_appv  = _calc_stats(approved_ids)
    savings_pend,  rebate_pend,  avoidance_pend  = _calc_stats(pending_ids)

    # Total count
    if stats_year:
        year_start = date(stats_year, 1, 1)
        year_end   = date(stats_year, 12, 31)
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
        total = len(matching_ids)

    return jsonify({
        'total':              total,
        'savings':            savings_sum,
        'savings_approved':   savings_appv,
        'savings_pending':    savings_pend,
        'rebate':             rebate_sum,
        'rebate_approved':    rebate_appv,
        'rebate_pending':     rebate_pend,
        'avoidance':          avoidance_sum,
        'avoidance_approved': avoidance_appv,
        'avoidance_pending':  avoidance_pend,
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
