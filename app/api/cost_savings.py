"""
Cost Savings API endpoints.
"""
from flask import jsonify, request, g
from datetime import datetime
from app.utils.timezone import now_eastern
from app import db
from app.api import cost_savings_bp
from app.models import Initiative, CostSavings, FacilityAllocation, Facility, AuditLog, User, UserRole
from app.utils.decorators import login_required, permission_required
from app.utils.validators import (
    validate_facility_allocations,
    validate_cost_savings_duplicate,
    validate_positive_amount
)
from app.utils.email import send_initiative_created_notification


@cost_savings_bp.route('', methods=['POST'])
@permission_required('create')
def create_cost_savings():
    """Create a new Cost Savings initiative."""
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
    required_fields = ['contract_number', 'vendor_name', 'start_date', 'end_date', 'total_savings_amount']
    for field in required_fields:
        if not has_required_value(field):
            return jsonify({'error': f'Missing required field: {field}'}), 400

    # Validate amount values
    is_valid, error = validate_positive_amount(data.get('total_savings_amount'), 'total_savings_amount')
    if not is_valid:
        return jsonify({'error': error}), 400

    # Validate facility allocations
    allocations = data.get('facility_allocations', [])
    is_valid, error = validate_facility_allocations(allocations)
    if not is_valid:
        return jsonify({'error': error}), 400
    
    # Check for duplicates
    is_valid, error = validate_cost_savings_duplicate(
        data['contract_number'],
        data['vendor_name'],
        datetime.fromisoformat(data['start_date']).date(),
        datetime.fromisoformat(data['end_date']).date()
    )
    if not is_valid:
        return jsonify({'error': error}), 400
    
    try:
        # Create initiative
        initiative = Initiative(
            initiative_type='Cost Savings',
            description=data.get('description', ''),
            wave_id=data.get('wave_id', ''),
            status='Pending Review',
            owner_id=data.get('owner_id', user.id),
            created_by_id=user.id
        )
        db.session.add(initiative)
        db.session.flush()  # Get initiative ID
        
        # Create cost savings details
        cost_savings = CostSavings(
            initiative_id=initiative.id,
            savings_type=data.get('savings_type') or '',
            wave_initiative_id=data.get('wave_initiative_id') or '',
            contract_number=data.get('contract_number') or '',
            contract_category=data.get('contract_category') or '',
            contract_source=data.get('contract_source') or '',
            gpo_tier=data.get('gpo_tier') or '',
            start_date=datetime.fromisoformat(data['start_date']).date() if data.get('start_date') else None,
            end_date=datetime.fromisoformat(data['end_date']).date() if data.get('end_date') else None,
            vendor_name=data.get('vendor_name') or '',
            baseline_spend=data.get('baseline_spend'),
            expected_spend=data.get('expected_spend'),
            annual_savings_amount=data.get('annual_savings_amount'),
            total_savings_amount=data.get('total_savings_amount'),
            is_fixed_cost=data.get('is_fixed_cost', False)
        )
        db.session.add(cost_savings)
        
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
            table_name='cost_savings',
            record_id=cost_savings.id,
            user_id=user.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        audit.set_new_values(cost_savings.to_dict())
        db.session.add(audit)
        
        db.session.commit()
        
        # Send email notifications
        reviewers = User.query.join(UserRole).filter(
            UserRole.can_review == True,
            User.is_active == True
        ).all()
        send_initiative_created_notification(initiative, user, reviewers)
        
        return jsonify({
            'message': 'Cost Savings initiative created successfully',
            'initiative': initiative.to_dict(include_details=True)
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@cost_savings_bp.route('/<int:initiative_id>', methods=['POST'])
@login_required
def update_cost_savings(initiative_id):
    """Update a Cost Savings initiative."""
    user = g.current_user
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    initiative = Initiative.query.filter_by(
        id=initiative_id,
        initiative_type='Cost Savings',
        is_deleted=False
    ).first()
    
    if not initiative:
        return jsonify({'error': 'Cost Savings initiative not found'}), 404
    
    # Check permissions
    can_edit = False
    if user.has_permission('edit_all'):
        can_edit = True
    elif user.has_permission('edit_own') and initiative.created_by_id == user.id:
        can_edit = True
    
    if not can_edit:
        return jsonify({'error': 'Insufficient permissions to edit this initiative'}), 403

    # Approved initiatives are locked — no edits allowed
    if initiative.status == 'Approved':
        return jsonify({'error': 'Approved initiatives cannot be modified.'}), 403

    cost_savings = initiative.cost_savings
    if not cost_savings:
        return jsonify({'error': 'Cost Savings details not found'}), 404
    
    # Store old values for audit
    old_values = cost_savings.to_dict()
    
    try:
        if 'contract_number' in data and not str(data['contract_number']).strip():
            return jsonify({'error': 'Missing required field: contract_number'}), 400

        if 'total_savings_amount' in data:
            is_valid, error = validate_positive_amount(data['total_savings_amount'], 'total_savings_amount')
            if not is_valid:
                return jsonify({'error': error}), 400

        # Validate if contract/vendor/dates are being changed
        if ('contract_number' in data or 'vendor_name' in data or 
            'start_date' in data or 'end_date' in data):
            
            contract_number = data.get('contract_number', cost_savings.contract_number)
            vendor_name = data.get('vendor_name', cost_savings.vendor_name)
            start_date = datetime.fromisoformat(data['start_date']).date() if data.get('start_date') else cost_savings.start_date
            end_date = datetime.fromisoformat(data['end_date']).date() if data.get('end_date') else cost_savings.end_date
            
            is_valid, error = validate_cost_savings_duplicate(
                contract_number,
                vendor_name,
                start_date,
                end_date,
                initiative_id
            )
            if not is_valid:
                return jsonify({'error': error}), 400
            
            # Save the parsed dates back to the model
            if data.get('start_date'):
                cost_savings.start_date = start_date
            elif 'start_date' in data:
                cost_savings.start_date = None
            if data.get('end_date'):
                cost_savings.end_date = end_date
            elif 'end_date' in data:
                cost_savings.end_date = None
        
        # Update cost savings fields
        updateable_fields = [
            'savings_type', 'wave_initiative_id', 'contract_number', 'contract_category', 'contract_source',
            'gpo_tier', 'vendor_name', 'baseline_spend', 'expected_spend',
            'annual_savings_amount', 'total_savings_amount', 'is_fixed_cost'
        ]
        
        for field in updateable_fields:
            if field in data:
                setattr(cost_savings, field, data[field])
        
        # Update initiative fields
        if 'description' in data:
            initiative.description = data['description']
        if 'wave_id' in data:
            initiative.wave_id = data['wave_id']
        
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
            
            # Delete old allocations
            FacilityAllocation.query.filter_by(initiative_id=initiative.id).delete()
            
            # Create new allocations
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
            table_name='cost_savings',
            record_id=cost_savings.id,
            user_id=user.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        audit.set_old_values(old_values)
        audit.set_new_values(cost_savings.to_dict())
        db.session.add(audit)
        
        db.session.commit()
        
        return jsonify({
            'message': 'Cost Savings initiative updated successfully',
            'initiative': initiative.to_dict(include_details=True)
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
