"""
Validation utilities.
"""
from datetime import datetime
from app import db
from app.models import CostSavings, Rebate, CostAvoidance


def validate_facility_allocations(allocations):
    """
    Validate facility allocations.
    Accepts a list of dicts with 'facility_code' and 'allocation_amount' (or legacy 'allocation_percentage'/'percentage'/'amount').
    An empty list or all-zero amounts is allowed (user may not have allocated yet).
    """
    if not allocations:
        return True, None   # empty is permitted — treat as unallocated

    has_percentage = any('allocation_percentage' in alloc or 'percentage' in alloc for alloc in allocations)
    has_amount     = any('allocation_amount' in alloc or 'amount' in alloc for alloc in allocations)

    if has_percentage and has_amount:
        return False, "Cannot mix percentage and amount allocations"

    if has_percentage:
        # Validate percentage allocations
        total = 0
        for alloc in allocations:
            percentage = float(alloc.get('allocation_percentage') or alloc.get('percentage', 0))
            if percentage < 0 or percentage > 100:
                return False, f"Invalid allocation percentage: {percentage}%. Must be between 0 and 100."
            total += percentage

        if abs(total - 100.0) > 0.01:  # Allow small floating point differences
            return False, f"Facility allocations must sum to 100%. Current total: {total}%"

    elif has_amount:
        for alloc in allocations:
            amount = float(alloc.get('allocation_amount') or alloc.get('amount', 0))
            if amount < 0:
                return False, f"Invalid allocation amount: ${amount}. Must be >= 0."

    return True, None


def validate_positive_amount(value, field_name):
    """
    Validate a submitted amount is a positive number.
    """
    if value is None:
        return False, f"Missing required field: {field_name}"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return False, f"{field_name.replace('_', ' ').title()} must be a valid number."
    if amount <= 0:
        return False, f"{field_name.replace('_', ' ').title()} must be greater than 0."
    return True, None


def validate_cost_savings_duplicate(contract_number, vendor_name, start_date, end_date, initiative_id=None):
    """
    Check for duplicate/overlapping Cost Savings initiatives.
    
    Args:
        contract_number: Contract number
        vendor_name: Vendor name
        start_date: Start date
        end_date: End date
        initiative_id: Current initiative ID (to exclude when updating)
        
    Returns:
        Tuple (is_valid, error_message)
    """
    query = db.session.query(CostSavings).join(CostSavings.initiative).filter(
        CostSavings.contract_number == contract_number,
        CostSavings.vendor_name == vendor_name,
        db.or_(
            # Check for overlapping date ranges
            db.and_(
                CostSavings.start_date <= start_date,
                CostSavings.end_date >= start_date
            ),
            db.and_(
                CostSavings.start_date <= end_date,
                CostSavings.end_date >= end_date
            ),
            db.and_(
                CostSavings.start_date >= start_date,
                CostSavings.end_date <= end_date
            )
        )
    )
    
    # Exclude current initiative if updating
    if initiative_id:
        query = query.filter(CostSavings.initiative_id != initiative_id)
    
    # Exclude deleted initiatives
    from app.models import Initiative
    query = query.filter(Initiative.is_deleted == False)
    
    existing = query.first()
    
    if existing:
        return False, "A Cost Savings initiative with the same contract and overlapping date range already exists"
    
    return True, None


def validate_rebate_duplicate(rebate_type, vendor_name, transaction_number, initiative_id=None):
    """
    Check for duplicate Rebate initiatives.
    
    Args:
        rebate_type: Type of rebate
        vendor_name: Vendor name
        transaction_number: Transaction/check number
        initiative_id: Current initiative ID (to exclude when updating)
        
    Returns:
        Tuple (is_valid, error_message)
    """
    query = db.session.query(Rebate).join(Rebate.initiative).filter(
        Rebate.rebate_type == rebate_type,
        Rebate.vendor_name == vendor_name,
        Rebate.check_number == transaction_number
    )
    
    # Exclude current initiative if updating
    if initiative_id:
        query = query.filter(Rebate.initiative_id != initiative_id)
    
    # Exclude deleted initiatives
    from app.models import Initiative
    query = query.filter(Initiative.is_deleted == False)
    
    existing = query.first()
    
    if existing:
        return False, "A Rebate initiative with the same type, vendor name, and check number already exists"
    
    return True, None


def validate_cost_avoidance_duplicate(avoidance_type, vendor_name, po_number, initiative_id=None):
    """
    Check for duplicate Cost Avoidance initiatives.
    
    Args:
        avoidance_type: Type of cost avoidance
        vendor_name: Vendor name
        po_number: PO number
        initiative_id: Current initiative ID (to exclude when updating)
        
    Returns:
        Tuple (is_valid, error_message)
    """
    query = db.session.query(CostAvoidance).join(CostAvoidance.initiative).filter(
        CostAvoidance.avoidance_type == avoidance_type,
        CostAvoidance.vendor_name == vendor_name,
        CostAvoidance.po_number == po_number
    )
    
    # Exclude current initiative if updating
    if initiative_id:
        query = query.filter(CostAvoidance.initiative_id != initiative_id)
    
    # Exclude deleted initiatives
    from app.models import Initiative
    query = query.filter(Initiative.is_deleted == False)
    
    existing = query.first()
    
    if existing:
        return False, "A Cost Avoidance initiative with the same type, vendor name, and PO number already exists"
    
    return True, None


def allowed_file(filename, allowed_extensions=None):
    """
    Check if file extension is allowed.
    
    Args:
        filename: Name of the file
        allowed_extensions: Set of allowed extensions (optional)
        
    Returns:
        Boolean
    """
    if allowed_extensions is None:
        from flask import current_app
        allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', set())
    
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions
