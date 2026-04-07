"""
Main routes for serving HTML pages.
"""
import io
import os
import zipfile
from datetime import datetime

from flask import Blueprint, send_file, send_from_directory, render_template, redirect, request, url_for
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename

from app.models import Initiative, FacilityAllocation, Rebate

main_bp = Blueprint('main', __name__)

_REBATE_ALLOC_COLUMNS = [
    ('MMC', 'MMC_ALLOC'),
    ('BURKE', 'BURKE_ALLOC'),
    ('AECOM', 'AECOM_ALLOC'),
    ('MMVO', 'MOUNT_VERNON_ALLOC'),
    ('MSSO', 'NEW_ROCHELLE_ALLOC'),
    ('NYACK', 'NYACK_ALLOC'),
    ('SLCH', 'SLCH_ALLOC'),
    ('WPH', 'WPH_ALLOC'),
]

_REBATE_ALLOC_CODE_MAP = {
    'MMC': 'MMC_ALLOC',
    'BURKE': 'BURKE_ALLOC',
    'AECOM': 'AECOM_ALLOC',
    'MMVO': 'MOUNT_VERNON_ALLOC',
    'MOUNT_VERNON': 'MOUNT_VERNON_ALLOC',
    'MOUNT VERNON': 'MOUNT_VERNON_ALLOC',
    'MSSO': 'NEW_ROCHELLE_ALLOC',
    'NEW_ROCHELLE': 'NEW_ROCHELLE_ALLOC',
    'NEW ROCHELLE': 'NEW_ROCHELLE_ALLOC',
    'NYACK': 'NYACK_ALLOC',
    'SLCH': 'SLCH_ALLOC',
    'WPH': 'WPH_ALLOC',
}

_REBATE_FILE_PATH_HEADERS = [f'FILE_PATH_{index}' for index in range(1, 11)]


def _parse_filter_date(value):
    """Parse a YYYY-MM-DD date filter value."""
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def _format_allocation_value(allocation):
    """Format an allocation amount or percent for display/export."""
    if allocation.allocation_amount is not None:
        return f"${float(allocation.allocation_amount):,.2f}"
    if allocation.allocation_percentage is not None:
        return f"{float(allocation.allocation_percentage):,.2f}%"
    return '—'


def _get_rebate_extraction_data(start_date=None, end_date=None, search_term=''):
    """Build rebate extraction rows, optionally filtered by check date and search text."""
    query = (
        Initiative.query.join(Initiative.rebate)
        .options(
            joinedload(Initiative.rebate),
            joinedload(Initiative.facility_allocations).joinedload(FacilityAllocation.facility),
            joinedload(Initiative.files)
        )
        .filter(
            Initiative.initiative_type == 'Rebate',
            Initiative.is_deleted == False
        )
    )

    if start_date:
        query = query.filter(Rebate.rebate_check_date >= start_date)
    if end_date:
        query = query.filter(Rebate.rebate_check_date <= end_date)

    initiatives = query.order_by(Initiative.id.desc()).all()

    rebate_rows = []
    total_rebate_amount = 0.0
    normalized_search = (search_term or '').strip().lower()

    for initiative in initiatives:
        rebate = initiative.rebate
        if rebate is None:
            continue

        allocation_map = {column_name: '—' for _, column_name in _REBATE_ALLOC_COLUMNS}
        for allocation in sorted(
            initiative.facility_allocations,
            key=lambda item: ((item.facility.code if item.facility else 'ZZZ'), item.id)
        ):
            facility_code = allocation.facility.code if allocation.facility else 'Unknown'
            column_name = _REBATE_ALLOC_CODE_MAP.get(str(facility_code).upper())
            if not column_name:
                continue
            allocation_map[column_name] = _format_allocation_value(allocation)

        attachments = []
        for file_record in initiative.files:
            if getattr(file_record, 'is_deleted', False):
                continue
            attachments.append({
                'id': file_record.id,
                'file_name': file_record.file_name or os.path.basename(file_record.file_path or ''),
                'file_path': file_record.file_path,
            })

        rebate_amount = float(rebate.rebate_amount or 0)
        row = {
            'initiative_id': initiative.id,
            'description': initiative.description or '—',
            'rebate_type': rebate.rebate_type or '—',
            'contract_number': rebate.contract_number or '—',
            'contract_category': rebate.contract_category or '—',
            'contract_source': rebate.contract_source or '—',
            'vendor_name': rebate.vendor_name or '—',
            'rebate_check_date': rebate.rebate_check_date.strftime('%Y-%m-%d') if rebate.rebate_check_date else '—',
            'rebate_payment_type': rebate.rebate_payment_type or '—',
            'check_number': rebate.check_number or '—',
            'rebate_amount': rebate_amount,
            'allocation_map': allocation_map,
            'attachments': attachments,
        }

        if normalized_search:
            searchable_text = ' '.join([
                str(row['initiative_id']),
                row['description'],
                row['rebate_type'],
                row['contract_number'],
                row['contract_category'],
                row['contract_source'],
                row['vendor_name'],
                row['rebate_check_date'],
                row['rebate_payment_type'],
                row['check_number'],
                *allocation_map.values(),
            ]).lower()
            if normalized_search not in searchable_text:
                continue

        total_rebate_amount += rebate_amount
        rebate_rows.append(row)

    return rebate_rows, total_rebate_amount


def _build_rebate_excel_workbook(rebate_rows, allocation_headers):
    """Create the rebate extraction Excel workbook with attachment hyperlink placeholders."""
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = 'Rebate Initiatives'

    headers = [
        'INITIATIVE_ID',
        'INIT_DESC',
        'REBATE_TYPE',
        'CONTRACT_NUM',
        'CONTRACT_CATEGORY',
        'CONTRACT_SOURCE',
        'VENDOR_NAME',
        'REBATE_CHECK_DATE',
        'REBATE_PAYMENT_TYPE',
        'CHECK_NUMBER',
        'REBATE_AMOUNT',
        *allocation_headers,
        *_REBATE_FILE_PATH_HEADERS,
    ]
    worksheet.append(headers)

    header_fill = PatternFill(fill_type='solid', fgColor='112B46')
    header_font = Font(color='FFFFFF', bold=True)
    hyperlink_start_col = len(headers) - len(_REBATE_FILE_PATH_HEADERS) + 1

    for col_idx, header in enumerate(headers, start=1):
        cell = worksheet.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        worksheet.column_dimensions[get_column_letter(col_idx)].width = min(max(len(header) + 2, 14), 28)

    for row_idx, row in enumerate(rebate_rows, start=2):
        file_paths = list(row.get('excel_file_paths', []))[:len(_REBATE_FILE_PATH_HEADERS)]
        file_paths += [''] * (len(_REBATE_FILE_PATH_HEADERS) - len(file_paths))

        worksheet.append([
            row['initiative_id'],
            row['description'],
            row['rebate_type'],
            row['contract_number'],
            row['contract_category'],
            row['contract_source'],
            row['vendor_name'],
            row['rebate_check_date'],
            row['rebate_payment_type'],
            row['check_number'],
            row['rebate_amount'],
            *[row['allocation_map'][column_name] for column_name in allocation_headers],
            *file_paths,
        ])

        worksheet.cell(row=row_idx, column=11).number_format = '$#,##0.00'

        for offset, relative_path in enumerate(file_paths):
            if not relative_path:
                continue
            cell = worksheet.cell(row=row_idx, column=hyperlink_start_col + offset)
            cell.hyperlink = relative_path
            cell.style = 'Hyperlink'

    worksheet.freeze_panes = 'A2'
    worksheet.auto_filter.ref = worksheet.dimensions

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


@main_bp.route('/')
def index():
    """Redirect to dashboard."""
    return redirect(url_for('main.dashboard'))


@main_bp.route('/dashboard')
def dashboard():
    """Serve the dashboard page."""
    # TEMPORARY: Use test user for local development
    return render_template('dashboard.html', current_user='Andrew Tong')


@main_bp.route('/savings-dashboard')
def savings_dashboard():
    """Serve the savings analytics dashboard (reviewer / admin)."""
    return render_template('savings_dashboard.html', current_user='Andrew Tong')


@main_bp.route('/cost-savings/form')
def cost_savings_form():
    """Serve the cost savings form page."""
    # TEMPORARY: Use test user for local development
    return render_template('cost_savings_form.html', current_user='Andrew Tong')


@main_bp.route('/rebate/form')
def rebate_form():
    """Serve the rebate form page."""
    # TEMPORARY: Use test user for local development
    return render_template('rebate_form.html', current_user='Andrew Tong')


@main_bp.route('/rebate/extraction')
def rebate_extraction():
    """Display all rebate initiatives with their detailed facility allocations."""
    start_date_raw = (request.args.get('start_date') or '').strip()
    end_date_raw = (request.args.get('end_date') or '').strip()
    search_term = (request.args.get('search') or '').strip()

    start_date = _parse_filter_date(start_date_raw)
    end_date = _parse_filter_date(end_date_raw)
    rebate_rows, total_rebate_amount = _get_rebate_extraction_data(start_date, end_date, search_term)

    return render_template(
        'rebate_extraction.html',
        current_user='Andrew Tong',
        rebate_rows=rebate_rows,
        rebate_count=len(rebate_rows),
        total_rebate_amount=total_rebate_amount,
        allocation_columns=[column_name for _, column_name in _REBATE_ALLOC_COLUMNS],
        filter_start_date=start_date_raw if start_date else '',
        filter_end_date=end_date_raw if end_date else '',
        search_term=search_term,
    )


@main_bp.route('/rebate/extraction/export')
def rebate_extraction_export():
    """Export rebate extraction results as a ZIP containing an Excel workbook and attachments."""
    start_date = _parse_filter_date((request.args.get('start_date') or '').strip())
    end_date = _parse_filter_date((request.args.get('end_date') or '').strip())
    search_term = (request.args.get('search') or '').strip()

    rebate_rows, _ = _get_rebate_extraction_data(start_date, end_date, search_term)
    allocation_headers = [column_name for _, column_name in _REBATE_ALLOC_COLUMNS]
    export_date = datetime.now().strftime('%m.%d.%Y')
    workbook_name = f'Rebate Initiatives-Savings Tracker - {export_date}.xlsx'
    zip_name = f'Rebate Initiatives-Savings Tracker - {export_date}.zip'

    zip_buffer = io.BytesIO()
    missing_files = []

    with zipfile.ZipFile(zip_buffer, 'w', compression=zipfile.ZIP_DEFLATED) as zip_file:
        attachment_count = 0
        for row in rebate_rows:
            excel_file_paths = []
            for attachment in row['attachments']:
                file_path = attachment.get('file_path')
                safe_name = secure_filename(attachment.get('file_name') or '') or f"file_{attachment.get('id', 'unknown')}"

                if file_path and os.path.isfile(file_path):
                    attachment_count += 1
                    arcname = (
                        f"Rebate_Attachments/initiative_{row['initiative_id']}/"
                        f"{attachment.get('id', 'file')}_{safe_name}"
                    )
                    zip_file.write(file_path, arcname=arcname)
                    if len(excel_file_paths) < len(_REBATE_FILE_PATH_HEADERS):
                        excel_file_paths.append(arcname)
                else:
                    missing_files.append(
                        f"Initiative {row['initiative_id']}: {attachment.get('file_name', 'Unknown file')}"
                    )

            row['excel_file_paths'] = excel_file_paths

        workbook_buffer = _build_rebate_excel_workbook(rebate_rows, allocation_headers)
        zip_file.writestr(workbook_name, workbook_buffer.getvalue())

        if attachment_count == 0:
            zip_file.writestr(
                'Rebate_Attachments/README.txt',
                'No attachment files were found for the selected rebate initiatives.\n'
            )

        if missing_files:
            zip_file.writestr('Rebate_Attachments/MISSING_FILES.txt', '\n'.join(missing_files))

    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name=zip_name
    )


@main_bp.route('/cost-avoidance/form')
def cost_avoidance_form():
    """Serve the cost avoidance form page."""
    # TEMPORARY: Use test user for local development
    return render_template('cost_avoidance_form.html', current_user='Andrew Tong')


@main_bp.route('/logout')
def logout():
    """Handle logout."""
    # For IIS Windows Authentication, we can't really logout
    # Just redirect to a goodbye page or back to index
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Logged Out - Savings Tracker</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="bg-light">
        <div class="container mt-5">
            <div class="row justify-content-center">
                <div class="col-md-6 text-center">
                    <h1>Logged Out</h1>
                    <p class="lead">You have been logged out. Close your browser to complete the logout process.</p>
                    <a href="/" class="btn btn-primary">Return to Login</a>
                </div>
            </div>
        </div>
    </body>
    </html>
    '''


@main_bp.route('/static/<path:path>')
def send_static(path):
    """Serve static files."""
    return send_from_directory('static', path)
