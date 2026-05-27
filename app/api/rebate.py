"""
Rebate API endpoints.
"""
from flask import jsonify, request, g
from datetime import datetime
from app.utils.timezone import now_eastern
from app import db
from app.api import rebate_bp
from app.models import Initiative, Rebate, FacilityAllocation, Facility, AuditLog, User, UserRole
from app.utils.decorators import login_required, permission_required
from app.utils.validators import validate_facility_allocations, validate_rebate_duplicate, validate_positive_amount
from app.utils.email import send_initiative_created_notification


def _normalize_wave_id(value):
    """Normalize wave_id so empty values persist as N/A."""
    if value is None:
        return 'N/A'
    text = str(value).strip()
    return text or 'N/A'


def _normalize_rebate_categories(contract_category, wave_category):
    """Keep wave-prefixed values in wave_category and out of contract_category."""
    normalized_contract = (contract_category or '').strip()
    normalized_wave = (wave_category or '').strip()

    if normalized_contract.lower().startswith('wave -'):
        if not normalized_wave:
            normalized_wave = normalized_contract
        normalized_contract = ''

    return normalized_contract, normalized_wave


@rebate_bp.route('', methods=['POST'])
@permission_required('create')
def create_rebate():
    """Create a new Rebate initiative."""
    user = g.current_user
    data = request.get_json()

    def has_required_value(field_name):
        value = data.get(field_name)
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        return True
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Validate required fields
    required_fields = ['rebate_type', 'contract_number', 'vendor_name', 'transaction_number', 'rebate_amount']
    for field in required_fields:
        if not has_required_value(field):
            return jsonify({'error': f'Missing required field: {field}'}), 400

    # Validate amount values
    is_valid, error = validate_positive_amount(data.get('rebate_amount'), 'rebate_amount')
    if not is_valid:
        return jsonify({'error': error}), 400

    # Validate facility allocations
    allocations = data.get('facility_allocations', [])
    is_valid, error = validate_facility_allocations(allocations)
    if not is_valid:
        return jsonify({'error': error}), 400
    
    # Check for duplicates
    is_valid, error = validate_rebate_duplicate(
        data['rebate_type'],
        data['vendor_name'],
        data['transaction_number']
    )
    if not is_valid:
        return jsonify({'error': error}), 400
    
    try:
        contract_category, wave_category = _normalize_rebate_categories(
            data.get('contract_category'),
            data.get('wave_category')
        )

        # Create initiative
        initiative = Initiative(
            initiative_type='Rebate',
            description=data.get('description', ''),
            wave_id=_normalize_wave_id(data.get('wave_id')),
            status='Pending Review',
            owner_id=data.get('owner_id', user.id),
            created_by_id=user.id
        )
        db.session.add(initiative)
        db.session.flush()
        
        # Create rebate details
        rebate = Rebate(
            initiative_id=initiative.id,
            rebate_type=data.get('rebate_type') or '',
            contract_category=contract_category,
            wave_category=wave_category,
            contract_source=data.get('contract_source') or '',
            contract_number=data.get('contract_number') or '',
            vendor_name=data.get('vendor_name') or '',
            gpo_tier=data.get('gpo_tier') or '',
            rebate_check_date=datetime.fromisoformat(data['transaction_date']).date() if data.get('transaction_date') else None,
            rebate_payment_type=data.get('transaction_type') or '',
            check_number=data.get('transaction_number') or '',
            rebate_amount=data.get('rebate_amount')
        )
        db.session.add(rebate)
        
        # Create facility allocations
        facility_lookup = {f.code: f.id for f in Facility.query.filter_by(is_active=True).all()}
        for alloc_data in allocations:
            facility_code = alloc_data.get('facility_code')
            facility_id = facility_lookup.get(facility_code) if facility_code else alloc_data.get('facility_id')
            if not facility_id:
                continue
            allocation = FacilityAllocation(
                initiative_id=initiative.id,
                facility_id=facility_id,
                allocation_percentage=alloc_data['allocation_percentage'] if 'allocation_percentage' in alloc_data else alloc_data.get('percentage'),
                allocation_amount=alloc_data['allocation_amount'] if 'allocation_amount' in alloc_data else alloc_data.get('amount')
            )
            db.session.add(allocation)
        
        # Create audit log
        audit = AuditLog(
            initiative_id=initiative.id,
            action='CREATE',
            table_name='rebates',
            record_id=rebate.id,
            user_id=user.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        audit.set_new_values(rebate.to_dict())
        db.session.add(audit)
        
        db.session.commit()
        
        # Send email notifications
        reviewers = User.query.join(UserRole).filter(
            UserRole.can_review == True,
            User.is_active == True
        ).all()
        send_initiative_created_notification(initiative, user, reviewers)
        
        return jsonify({
            'message': 'Rebate initiative created successfully',
            'initiative': initiative.to_dict(include_details=True)
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@rebate_bp.route('/<int:initiative_id>', methods=['POST'])
@login_required
def update_rebate(initiative_id):
    """Update a Rebate initiative."""
    user = g.current_user
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    initiative = Initiative.query.filter_by(
        id=initiative_id,
        initiative_type='Rebate',
        is_deleted=False
    ).first()
    
    if not initiative:
        return jsonify({'error': 'Rebate initiative not found'}), 404
    
    # Only creator, reviewer, or admin can edit existing initiatives.
    role_name = (getattr(getattr(user, 'role', None), 'name', '') or '').strip().lower()
    is_admin = role_name == 'admin'
    is_reviewer = role_name == 'reviewer' or user.has_permission('review') or user.has_permission('approve')
    is_creator = initiative.created_by_id == user.id
    can_edit = is_creator or is_reviewer or is_admin
    
    if not can_edit:
        return jsonify({'error': 'Insufficient permissions to edit this initiative'}), 403

    # Approved initiatives are locked — no edits allowed
    if initiative.status == 'Approved':
        return jsonify({'error': 'Approved initiatives cannot be modified.'}), 403

    rebate = initiative.rebate
    if not rebate:
        return jsonify({'error': 'Rebate details not found'}), 404
    
    # Store old values for audit
    old_values = rebate.to_dict()
    
    try:
        if 'contract_number' in data and not str(data['contract_number']).strip():
            return jsonify({'error': 'Missing required field: contract_number'}), 400

        # Validate if rebate type/vendor/transaction number are being changed
        if 'rebate_amount' in data:
            is_valid, error = validate_positive_amount(data['rebate_amount'], 'rebate_amount')
            if not is_valid:
                return jsonify({'error': error}), 400

        if ('rebate_type' in data or 'vendor_name' in data or 'transaction_number' in data):
            rebate_type = data.get('rebate_type', rebate.rebate_type)
            vendor_name = data.get('vendor_name', rebate.vendor_name)
            transaction_number = data.get('transaction_number', rebate.check_number)
            
            is_valid, error = validate_rebate_duplicate(
                rebate_type,
                vendor_name,
                transaction_number,
                initiative_id
            )
            if not is_valid:
                return jsonify({'error': error}), 400
        
        # Update rebate fields
        updateable_fields = [
            'rebate_type', 'contract_source', 'contract_number',
            'vendor_name', 'gpo_tier', 'rebate_amount'
        ]
        
        for field in updateable_fields:
            if field in data:
                setattr(rebate, field, data[field])

        if 'contract_category' in data or 'wave_category' in data:
            contract_category, wave_category = _normalize_rebate_categories(
                data.get('contract_category', rebate.contract_category),
                data.get('wave_category', rebate.wave_category),
            )
            rebate.contract_category = contract_category
            rebate.wave_category = wave_category
        
        if data.get('transaction_date'):
            rebate.rebate_check_date = datetime.fromisoformat(data['transaction_date']).date()
        elif 'transaction_date' in data:
            rebate.rebate_check_date = None
        if 'transaction_type' in data:
            rebate.rebate_payment_type = data['transaction_type']
        if 'transaction_number' in data:
            rebate.check_number = data['transaction_number']
        
        # Update initiative fields
        if 'description' in data:
            initiative.description = data['description']
        if 'wave_id' in data:
            initiative.wave_id = _normalize_wave_id(data['wave_id'])
        
        # If previously Rejected, resubmit for Pending Review
        if initiative.status == 'Rejected':
            initiative.status = 'Pending Review'
            initiative.review_comments = ''
            initiative.reviewed_by_id = None
            initiative.review_date = None

        initiative.updated_at = now_eastern()
        
        # Update facility allocations if provided
        if 'facility_allocations' in data:
            allocations = data['facility_allocations']
            is_valid, error = validate_facility_allocations(allocations)
            if not is_valid:
                return jsonify({'error': error}), 400
            
            FacilityAllocation.query.filter_by(initiative_id=initiative.id).delete()
            
            facility_lookup = {f.code: f.id for f in Facility.query.filter_by(is_active=True).all()}
            for alloc_data in allocations:
                facility_code = alloc_data.get('facility_code')
                facility_id = facility_lookup.get(facility_code) if facility_code else alloc_data.get('facility_id')
                if not facility_id:
                    continue
                allocation = FacilityAllocation(
                    initiative_id=initiative.id,
                    facility_id=facility_id,
                    allocation_percentage=alloc_data['allocation_percentage'] if 'allocation_percentage' in alloc_data else alloc_data.get('percentage'),
                    allocation_amount=alloc_data['allocation_amount'] if 'allocation_amount' in alloc_data else alloc_data.get('amount')
                )
                db.session.add(allocation)
        
        # Create audit log
        audit = AuditLog(
            initiative_id=initiative.id,
            action='UPDATE',
            table_name='rebates',
            record_id=rebate.id,
            user_id=user.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        audit.set_old_values(old_values)
        audit.set_new_values(rebate.to_dict())
        db.session.add(audit)
        
        db.session.commit()
        
        return jsonify({
            'message': 'Rebate initiative updated successfully',
            'initiative': initiative.to_dict(include_details=True)
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
