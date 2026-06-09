"""
Cost Avoidance API endpoints.
"""
from flask import jsonify, request, g
from datetime import datetime
from app.utils.timezone import now_eastern
from app import db
from app.api import cost_avoidance_bp
from app.models import Initiative, CostAvoidance, FacilityAllocation, Facility, AuditLog, User, UserRole
from app.utils.decorators import login_required, permission_required
from app.utils.validators import validate_facility_allocations, validate_cost_avoidance_duplicate, validate_positive_amount
from app.utils.email import send_initiative_created_notification
from app.utils.sp_helpers import run_distribution_procedure


def _normalize_wave_id(value):
    """Normalize wave_id so empty values persist as N/A."""
    if value is None:
        return 'N/A'
    text = str(value).strip()
    return text or 'N/A'


@cost_avoidance_bp.route('', methods=['POST'])
@permission_required('create')
def create_cost_avoidance():
    """Create a new Cost Avoidance initiative."""
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
    required_fields = ['avoidance_type', 'contract_number', 'vendor_name', 'po_number', 'avoidance_amount']
    for field in required_fields:
        if not has_required_value(field):
            return jsonify({'error': f'Missing required field: {field}'}), 400

    # Validate amount values
    is_valid, error = validate_positive_amount(data.get('avoidance_amount'), 'avoidance_amount')
    if not is_valid:
        return jsonify({'error': error}), 400

    # Validate facility allocations
    allocations = data.get('facility_allocations', [])
    is_valid, error = validate_facility_allocations(allocations)
    if not is_valid:
        return jsonify({'error': error}), 400
    
    # Check for duplicates
    is_valid, error = validate_cost_avoidance_duplicate(
        data['avoidance_type'],
        data['vendor_name'],
        data['po_number']
    )
    if not is_valid:
        return jsonify({'error': error}), 400
    
    try:
        # Create initiative
        initiative = Initiative(
            initiative_type='Cost Avoidance',
            description=data.get('description', ''),
            wave_id=_normalize_wave_id(data.get('wave_id')),
            status='Pending Review',
            owner_id=data.get('owner_id', user.id),
            created_by_id=user.id
        )
        db.session.add(initiative)
        db.session.flush()
        
        # Create cost avoidance details
        cost_avoidance = CostAvoidance(
            initiative_id=initiative.id,
            avoidance_type=data.get('avoidance_type') or '',
            strata_project_id=data.get('strata_project_id') or '',
            contract_category=data.get('contract_category') or '',
            contract_number=data.get('contract_number') or '',
            contract_source=data.get('contract_source') or '',
            vendor_name=data.get('vendor_name') or '',
            po_number=data.get('po_number') or '',
            po_date=datetime.fromisoformat(data['po_date']).date() if 'po_date' in data else None,
            avoidance_date=datetime.fromisoformat(data['avoidance_date']).date() if 'avoidance_date' in data else None,
            original_quote=data.get('original_quote'),
            new_quote=data.get('new_quote'),
            avoidance_amount=data.get('avoidance_amount')
        )
        db.session.add(cost_avoidance)
        
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
            table_name='cost_avoidance',
            record_id=cost_avoidance.id,
            user_id=user.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        audit.set_new_values(cost_avoidance.to_dict())
        db.session.add(audit)
        
        db.session.commit()

        run_distribution_procedure()
        
        # Send email notifications
        reviewers = User.query.join(UserRole).filter(
            UserRole.can_review == True,
            User.is_active == True
        ).all()
        send_initiative_created_notification(initiative, user, reviewers)
        
        return jsonify({
            'message': 'Cost Avoidance initiative created successfully',
            'initiative': initiative.to_dict(include_details=True)
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@cost_avoidance_bp.route('/<int:initiative_id>', methods=['POST'])
@login_required
def update_cost_avoidance(initiative_id):
    """Update a Cost Avoidance initiative."""
    user = g.current_user
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    initiative = Initiative.query.filter_by(
        id=initiative_id,
        initiative_type='Cost Avoidance',
        is_deleted=False
    ).first()
    
    if not initiative:
        return jsonify({'error': 'Cost Avoidance initiative not found'}), 404
    
    # Only admins or the initiative owner can edit.
    role_name = (getattr(getattr(user, 'role', None), 'name', '') or '').strip().lower()
    is_admin = role_name == 'admin'
    is_owner = initiative.owner_id == user.id
    can_edit = is_admin or is_owner
    
    if not can_edit:
        return jsonify({'error': 'Insufficient permissions to edit this initiative'}), 403

    # Approved initiatives are locked — no edits allowed
    if initiative.status == 'Approved':
        return jsonify({'error': 'Approved initiatives cannot be modified.'}), 403

    cost_avoidance = initiative.cost_avoidance
    if not cost_avoidance:
        return jsonify({'error': 'Cost Avoidance details not found'}), 404
    
    # Store old values for audit
    old_values = cost_avoidance.to_dict()
    
    try:
        if 'contract_number' in data and not str(data['contract_number']).strip():
            return jsonify({'error': 'Missing required field: contract_number'}), 400

        # Validate if avoidance type/vendor/PO are being changed
        if 'avoidance_amount' in data:
            is_valid, error = validate_positive_amount(data['avoidance_amount'], 'avoidance_amount')
            if not is_valid:
                return jsonify({'error': error}), 400

        if ('avoidance_type' in data or 'vendor_name' in data or 'po_number' in data):
            avoidance_type = data.get('avoidance_type', cost_avoidance.avoidance_type)
            vendor_name = data.get('vendor_name', cost_avoidance.vendor_name)
            po_number = data.get('po_number', cost_avoidance.po_number)
            
            is_valid, error = validate_cost_avoidance_duplicate(
                avoidance_type,
                vendor_name,
                po_number,
                initiative_id
            )
            if not is_valid:
                return jsonify({'error': error}), 400
        
        # Update cost avoidance fields
        updateable_fields = [
            'avoidance_type', 'strata_project_id', 'contract_category',
            'contract_number', 'contract_source', 'vendor_name', 'po_number', 'original_quote',
            'new_quote', 'avoidance_amount'
        ]
        
        for field in updateable_fields:
            if field in data:
                setattr(cost_avoidance, field, data[field])
        
        if data.get('po_date'):
            cost_avoidance.po_date = datetime.fromisoformat(data['po_date']).date()
        elif 'po_date' in data:
            cost_avoidance.po_date = None
        if data.get('avoidance_date'):
            cost_avoidance.avoidance_date = datetime.fromisoformat(data['avoidance_date']).date()
        elif 'avoidance_date' in data:
            cost_avoidance.avoidance_date = None
        
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
            table_name='cost_avoidance',
            record_id=cost_avoidance.id,
            user_id=user.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        audit.set_old_values(old_values)
        audit.set_new_values(cost_avoidance.to_dict())
        db.session.add(audit)
        
        db.session.commit()

        run_distribution_procedure()
        
        return jsonify({
            'message': 'Cost Avoidance initiative updated successfully',
            'initiative': initiative.to_dict(include_details=True)
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
