// Dashboard functionality

let currentInitiativeId = null;
window._showDeleted = false;

// ── Sorting & pagination state ────────────────────────
let _sortColumn  = 'initiative_date';   // default: newest initiative year first
let _sortDir     = 'desc';
let _currentPage = 1;
const _pageSize  = 20;

// ── Stats year follows the bottom Initiative Year filter ────────────────
let _statsYear = null;

function syncStatsYearFromFilter() {
    const selectedYear = document.getElementById('filterYear')?.value || '';
    _statsYear = selectedYear ? parseInt(selectedYear, 10) : null;

    const summaryLabel = document.getElementById('summaryYearLabel');
    if (summaryLabel) {
        summaryLabel.textContent = selectedYear ? `Initiative Year: ${selectedYear}` : 'Initiative Year: All Years';
    }

    const badge = document.getElementById('statsYearBadge');
    if (badge) {
        badge.textContent = selectedYear || 'All Years';
        badge.style.display = '';
    }
}

/**
 * Toggle sort on a column. Cycles: none → asc → desc → none.
 * Resets to page 1 and re-fetches from server.
 */
function toggleSort(column) {
    if (_sortColumn === column) {
        if (_sortDir === 'asc')  { _sortDir = 'desc'; }
        else                     { _sortColumn = null; _sortDir = 'asc'; }
    } else {
        _sortColumn = column;
        _sortDir    = 'asc';
    }
    _currentPage = 1;
    updateSortIcons();
    loadInitiatives();
}

/** Navigate to a page — fetches that page from server. */
function goToPage(page) {
    _currentPage = page;
    loadInitiatives();
    document.getElementById('initiativesTable')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

/** Build the pagination bar using values returned by the server. */
function renderPagination(totalRows, currentPage, totalPages) {
    const container = document.getElementById('paginationContainer');
    if (!container) return;

    const start = totalRows ? Math.min((currentPage - 1) * _pageSize + 1, totalRows) : 0;
    const end   = Math.min(currentPage * _pageSize, totalRows);

    if (totalPages <= 1) {
        container.innerHTML = totalRows
            ? `<div class="px-3 py-2"><small class="text-muted">Showing all ${totalRows} initiative${totalRows !== 1 ? 's' : ''}</small></div>`
            : '';
        return;
    }

    const pageBtns = [];
    const mkBtn = (label, pg, active = false, disabled = false) => {
        const cls   = active ? 'page-item active' : disabled ? 'page-item disabled' : 'page-item';
        const click = (!active && !disabled) ? `goToPage(${pg})` : 'return false';
        return `<li class="${cls}"><a class="page-link" href="#" onclick="event.preventDefault();${click}">${label}</a></li>`;
    };

    pageBtns.push(mkBtn('&laquo;', currentPage - 1, false, currentPage === 1));

    let pages = [];
    if (totalPages <= 7) {
        for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else {
        pages = [1];
        if (currentPage > 4)              pages.push('...');
        for (let i = Math.max(2, currentPage - 2); i <= Math.min(totalPages - 1, currentPage + 2); i++) pages.push(i);
        if (currentPage < totalPages - 3) pages.push('...');
        pages.push(totalPages);
    }

    pages.forEach(p => {
        if (p === '...') pageBtns.push('<li class="page-item disabled"><a class="page-link" href="#">…</a></li>');
        else             pageBtns.push(mkBtn(p, p, p === currentPage));
    });

    pageBtns.push(mkBtn('&raquo;', currentPage + 1, false, currentPage === totalPages));

    container.innerHTML = `
        <div class="d-flex justify-content-between align-items-center px-3 py-2">
            <small class="text-muted">Showing ${start}–${end} of ${totalRows} initiatives</small>
            <nav><ul class="pagination pagination-sm mb-0">${pageBtns.join('')}</ul></nav>
        </div>`;
}

/** Refresh the sort-indicator icons in all sortable column headers. */
function updateSortIcons() {
    const cols = { id: 'sort-icon-id', updated_at: 'sort-icon-updated', amount: 'sort-icon-amount', initiative_date: 'sort-icon-initdate' };
    Object.entries(cols).forEach(([col, iconId]) => {
        const el = document.getElementById(iconId);
        if (!el) return;
        if (_sortColumn !== col) {
            el.className = 'fas fa-sort ms-1 text-muted sort-icon-inactive';
        } else if (_sortDir === 'asc') {
            el.className = 'fas fa-sort-up ms-1 text-primary';
        } else {
            el.className = 'fas fa-sort-down ms-1 text-primary';
        }
    });
}
// ───────────────────────────────────────────────────────

// Render initiatives as plain HTML table rows
function renderTableRows(rows) {
    const tbody = document.getElementById('initiativesTableBody');
    if (!tbody) return;

    if (!rows || rows.length === 0) {
        tbody.innerHTML = '<tr><td colspan="11" class="text-center text-muted py-4">No initiatives found.</td></tr>';
        return;
    }

    const typeIcons = {
        'Cost Savings':  '<i class="fas fa-piggy-bank text-success me-1"></i>',
        'Rebate':        '<i class="fas fa-receipt text-info me-1"></i>',
        'Cost Avoidance':'<i class="fas fa-shield-alt text-warning me-1"></i>'
    };
    const statusClass = {
        'Draft':          'status-draft',
        'Submitted':      'status-submitted',
        'Pending Review': 'status-pending',
        'Approved':       'status-approved',
        'Rejected':       'status-rejected'
    };

    tbody.innerHTML = rows.map(r => {
        const icon        = typeIcons[r.initiative_type]  || '';
        const sCls        = statusClass[r.status] || '';
        const amount      = parseFloat(r.amount) || 0;
        const fmtAmt      = '$' + Math.round(amount).toLocaleString('en-US');
        const initDateRaw = r.initiative_date;
        const initDateFmt = initDateRaw ? new Date(initDateRaw + 'T00:00:00').getFullYear() : '';
        const updatedDate = r.updated_at ? new Date(r.updated_at).toLocaleString('en-US', {timeZone: 'America/New_York', month: '2-digit', day: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'}) : '';
        const cu          = window._currentUser || {};

        let actionBtns = '';
        if (r.is_deleted) {
            // Deleted row — admin can restore
            if (cu.can_delete_all) {
                actionBtns = `<button class="btn btn-sm btn-outline-warning" onclick="restoreInitiative(${r.id})" title="Restore"><i class="fas fa-trash-restore"></i></button>`;
            }
        } else {
            // Normal row — view, edit, optional delete
            const canDel = cu.can_delete_all || (cu.can_delete_own && r.created_by_id === cu.id);
            // Approved initiatives are read-only — only view is allowed
            const editBtn = r.status !== 'Approved'
                ? `<button class="btn btn-sm btn-outline-info"    onclick="editInitiative(${r.id})" title="Edit"><i class="fas fa-edit"></i></button>`
                : `<button class="btn btn-sm btn-outline-secondary" onclick="viewInitiative(${r.id})" title="Approved — view only" disabled><i class="fas fa-lock"></i></button>`;
            actionBtns = `
                <button class="btn btn-sm btn-outline-primary" onclick="viewInitiative(${r.id})" title="View"><i class="fas fa-eye"></i></button>
                ${editBtn}
                ${canDel ? `<button class="btn btn-sm btn-outline-danger" onclick="deleteInitiative(${r.id})" title="Delete"><i class="fas fa-trash"></i></button>` : ''}
            `;
        }

        const rowClass = r.is_deleted ? ' class="deleted-row"' : '';
        const statusCell = r.is_deleted
            ? `<span class="status-badge" style="background:#dc3545;color:white">Deleted</span>`
            : `<span class="status-badge ${sCls}">${r.status || ''}</span>`;

        return `<tr${rowClass}>
            <td>${r.id || ''}</td>
            <td>${r.owner_name || ''}</td>
            <td>${icon}${r.initiative_type || ''}</td>
            <td>${r.contract_id || 'N/A'}</td>
            <td>${r.contract_category || ''}</td>
            <td>${r.vendor_name || ''}</td>
            <td class="text-end">${fmtAmt}</td>
            <td>${initDateFmt}</td>
            <td>${updatedDate}</td>
            <td>${statusCell}</td>
            <td>
                <div class="btn-group btn-group-sm" role="group">
                    ${actionBtns}
                </div>
            </td>
        </tr>`;
    }).join('');
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Load current user permissions
    fetch('/api/auth/current-user')
        .then(r => r.json())
        .then(u => {
            window._currentUser = u;
            // Show the "Show Deleted" toggle only for admins
            if (u.can_delete_all) {
                const btn = document.getElementById('toggleDeletedBtn');
                if (btn) btn.classList.remove('d-none');
            }
        })
        .catch(() => { window._currentUser = {}; });

    syncStatsYearFromFilter();
    updateSortIcons();
    loadInitiatives();

    // Setup filter event listeners
    setupFilters();

    // Reset confirm view whenever action modal closes so it shows the form next time
    const actionModalEl = document.getElementById('actionModal');
    if (actionModalEl) {
        actionModalEl.addEventListener('hidden.bs.modal', function() {
            document.getElementById('mf_confirmView')?.classList.add('d-none');
            document.getElementById('modalForm')?.classList.remove('d-none');
            document.getElementById('mf_goBackBtn')?.classList.add('d-none');
            document.getElementById('mf_confirmSaveBtn')?.classList.add('d-none');
            window._pendingPayload  = null;
            window._pendingEndpoint = null;
        });
    }
});

// Load a single page of initiatives from the server
function loadInitiatives() {
    showLoading();

    const status = document.getElementById('filterStatus').value;
    const search = document.getElementById('searchBox').value;
    const filterYear = document.getElementById('filterYear')?.value || '';

    // Map client sort-column names → API sort_by values
    const sortByMap = { id: 'id', updated_at: 'updated_at', amount: 'amount', initiative_date: 'initiative_date' };
    const sort_by    = _sortColumn ? (sortByMap[_sortColumn] || 'created_at') : 'created_at';
    const sort_order = _sortColumn ? _sortDir : 'desc';

    const params = new URLSearchParams({
        page:       _currentPage,
        per_page:   _pageSize,
        sort_by,
        sort_order,
    });
    if (status)              params.set('status', status);
    if (search)              params.set('search', search);
    if (filterYear)          params.set('initiative_year', filterYear);
    if (window._showDeleted) params.set('include_deleted', 'true');

    fetch(`/api/initiatives?${params}`)
        .then(r => r.json())
        .then(data => {
            if (data.initiatives) {
                const rows = data.initiatives.map(flattenInitiative);
                renderTableRows(rows);
                renderPagination(data.total || 0, data.current_page || 1, data.pages || 1);
            } else {
                console.error('No initiatives data in response');
                renderTableRows([]);
                renderPagination(0, 1, 1);
            }
            hideLoading();
        })
        .catch(error => {
            console.error('Error loading initiatives:', error);
            showAlert('Error loading initiatives', 'danger');
            hideLoading();
        });

    loadStats();
}

// Load only the aggregate stats (called on year-tab switch too)
function loadStats() {
    const status = document.getElementById('filterStatus').value;
    const search = document.getElementById('searchBox').value;
    const filterYear = document.getElementById('filterYear')?.value || '';

    syncStatsYearFromFilter();

    const statsParams = new URLSearchParams();
    if (status)              statsParams.set('status', status);
    if (search)              statsParams.set('search', search);
    if (filterYear)          statsParams.set('initiative_year', filterYear);
    if (window._showDeleted) statsParams.set('include_deleted', 'true');
    if (_statsYear)          statsParams.set('stats_year', _statsYear);

    fetch(`/api/initiatives/dashboard-stats?${statsParams}`)
        .then(r => r.json())
        .then(stats => { if (stats) updateStatisticsFromServer(stats); })
        .catch(() => {});
}

// Flatten nested initiative API response into grid-friendly row
function flattenInitiative(init) {
    const detail = init.cost_savings || init.rebate || init.cost_avoidance || {};
    const amount = init.cost_savings    ? (init.cost_savings.total_savings_amount || 0)
                 : init.rebate          ? (init.rebate.rebate_amount || 0)
                 : init.cost_avoidance  ? (init.cost_avoidance.avoidance_amount || 0)
                 : 0;
    const initiative_date =
          init.cost_savings   ? (init.cost_savings.start_date   || null)
        : init.rebate         ? (init.rebate.transaction_date   || null)
        : init.cost_avoidance ? (init.cost_avoidance.avoidance_date || null)
        : null;
    return {
        ...init,
        owner_name:        init.owner ? (init.owner.full_name || init.owner.username || '') : '',
        created_by:        init.created_by ? (init.created_by.full_name || init.created_by.username) : '',
        created_by_id:     init.created_by ? init.created_by.id : null,
        contract_category: detail.contract_category || '',
        vendor_name:       detail.vendor_name || '',
        contract_id:       detail.contract_number || '',
        amount:            parseFloat(amount) || 0,
        initiative_date,
        is_deleted:        init.is_deleted || false
    };
}

// Update statistics cards from server aggregate response
function updateStatisticsFromServer(stats) {
    const abbrev = n => {
        const v = +n || 0;
        if (Math.abs(v) >= 1_000_000) return '$' + (v / 1_000_000).toFixed(2) + 'M';
        if (Math.abs(v) >= 1_000)     return '$' + (v / 1_000).toFixed(2) + 'K';
        return '$' + Math.round(v).toLocaleString('en-US');
    };
    document.getElementById('totalCount').textContent      = stats.total || 0;
    document.getElementById('savingsAmount').textContent   = abbrev(stats.savings);
    document.getElementById('rebateAmount').textContent    = abbrev(stats.rebate);
    document.getElementById('avoidanceAmount').textContent = abbrev(stats.avoidance);
}

// Setup filter event listeners
function setupFilters() {
    document.getElementById('filterStatus').addEventListener('change', applyFilters);
    document.getElementById('filterYear').addEventListener('change', applyFilters);
    document.getElementById('searchBox').addEventListener('keyup', debounce(applyFilters, 500));
}

// Apply filters — always restart from page 1
function applyFilters() {
    _currentPage = 1;
    loadInitiatives();
}

// View initiative details (read-only modal)
function viewInitiative(id) {
    showInitiativeModal(id, false);
}

// Edit initiative (editable modal)
function editInitiative(id) {
    showInitiativeModal(id, true);
}

// Open the initiative modal (view or edit mode)
function showInitiativeModal(id, editMode) {
    Promise.all([
        fetch(`/api/initiatives/${id}`).then(response => response.json()),
        loadContractCategorySelect('mf_contract_category'),
        initializePrimeContractLookup({
            contractInputId: 'mf_contract_number',
            vendorInputId: 'mf_vendor_name',
            contractListId: 'mf_contract_number_options',
            vendorListId: 'mf_vendor_name_options',
        }),
    ])
        .then(([data]) => {
            populateInitiativeModal(data, editMode);
            const modal = new bootstrap.Modal(document.getElementById('actionModal'));
            modal.show();
        })
        .catch(error => {
            console.error('Error loading initiative:', error);
            showAlert('Error loading initiative details', 'danger');
        });
}

// Populate the modal form with initiative data
function populateInitiativeModal(data, editMode) {
    // Clear any previous alerts
    const mac = document.getElementById('modalAlertContainer');
    if (mac) mac.innerHTML = '';

    const flat = flattenInitiative(data);
    const raw  = data.cost_savings || data.rebate || data.cost_avoidance || {};
    const type = data.initiative_type;

    // Store context for save
    window._modalInitiativeId     = data.id;
    window._modalInitiativeType   = type;
    window._modalInitiativeStatus = data.status;

    // Helpers
    const setVal = (elId, val) => {
        const el = document.getElementById(elId);
        if (el) el.value = (val !== null && val !== undefined) ? val : '';
    };
    // Like setVal but formats numbers with thousand separators
    const setNumVal = (elId, val) => {
        const el = document.getElementById(elId);
        if (!el) return;
        const n = parseFloat(String(val ?? '').replace(/,/g, ''));
        el.value = isNaN(n) ? '' : fmtNum(n);
    };
    const setRadio = (name, val) => {
        document.querySelectorAll(`input[name="${name}"]`).forEach(r => {
            r.checked = (r.value === val);
        });
    };
    const setSelectNormalized = (elId, val) => {
        const el = document.getElementById(elId);
        if (!el) return;

        const raw = (val ?? '').toString().trim();
        if (!raw) {
            el.value = '';
            return;
        }

        const norm = s => s.toString().trim().toLowerCase().replace(/\s+/g, ' ');
        const target = norm(raw);
        const options = Array.from(el.options || []);
        const match = options.find(o => norm(o.value || o.text || '') === target);

        if (match) {
            el.value = match.value;
            return;
        }

        // Preserve legacy/custom values so view mode still shows accurate data.
        const dynamic = document.createElement('option');
        dynamic.value = raw;
        dynamic.text = raw;
        dynamic.dataset.dynamic = 'true';
        el.appendChild(dynamic);
        el.value = raw;
    };

    // Common fields
    setVal('mf_initiative_type', type);
    setVal('mf_status',          data.status);
    setVal('mf_created_by',      flat.created_by);
    setVal('mf_description',     data.description);

    // Contract fields
    const cc = document.getElementById('mf_contract_category');
    if (cc) {
        Array.from(cc.options || []).forEach(o => {
            if (o.dataset && o.dataset.dynamic === 'true') o.remove();
        });
    }
    setSelectNormalized('mf_contract_category', raw.contract_category);
    setVal('mf_contract_number',     raw.contract_number);
    loadPrimeVendorOptions(raw.contract_number, 'mf_vendor_name_options');
    setRadio('mf_contract_source_r', raw.contract_source);
    setVal('mf_vendor_name',         raw.vendor_name);
    setVal('mf_wave_initiative_id',  raw.wave_initiative_id);

    // Always hide text fallback for contract_source, show radios
    document.getElementById('mf_contract_source').style.display = 'none';

    // Hide all type sections
    ['mf_section_savings', 'mf_section_avoidance', 'mf_section_rebate'].forEach(sid => {
        document.getElementById(sid).classList.add('d-none');
    });

    // Type-specific
    if (type === 'Cost Savings') {
        document.getElementById('mf_section_savings').classList.remove('d-none');
        const cs = data.cost_savings || {};
        setRadio('mf_savings_type',    cs.savings_type);
        setVal('mf_gpo_tier_cs',       cs.gpo_tier);
        setVal('mf_start_date',        cs.start_date  ? cs.start_date.slice(0,10)  : '');
        setVal('mf_end_date',          cs.end_date    ? cs.end_date.slice(0,10)    : '');
        setNumVal('mf_baseline_spend',    cs.baseline_spend);
        setNumVal('mf_expected_spend',    cs.expected_spend);
        setNumVal('mf_annual_savings',    cs.annual_savings_amount);
        setNumVal('mf_total_savings',     cs.total_savings_amount);

    } else if (type === 'Cost Avoidance') {
        document.getElementById('mf_section_avoidance').classList.remove('d-none');
        const ca = data.cost_avoidance || {};
        setRadio('mf_avoidance_type',  ca.avoidance_type);
        setVal('mf_strata_project_id', ca.strata_project_id);
        setVal('mf_po_number',         ca.po_number);
        setVal('mf_po_date',           ca.po_date         ? ca.po_date.slice(0,10)         : '');
        setVal('mf_avoidance_date',    ca.avoidance_date  ? ca.avoidance_date.slice(0,10)  : '');
        setNumVal('mf_original_quote',    ca.original_quote);
        setNumVal('mf_new_quote',         ca.new_quote);
        setNumVal('mf_avoidance_amount',  ca.avoidance_amount);

    } else if (type === 'Rebate') {
        document.getElementById('mf_section_rebate').classList.remove('d-none');
        const rb = data.rebate || {};
        document.getElementById('mf_rebate_type').value = rb.rebate_type || '';
        setVal('mf_gpo_tier_rb',       rb.gpo_tier);
        setNumVal('mf_rebate_amount',  rb.rebate_amount);
        setVal('mf_transaction_date',  rb.transaction_date  ? rb.transaction_date.slice(0,10)  : '');
        setRadio('mf_transaction_type', rb.transaction_type);
        setVal('mf_transaction_number', rb.transaction_number);
    }

    // Facility allocations
    const facilityMap = {};
    (data.facility_allocations || []).forEach(a => {
        const code = a.facility ? a.facility.code.toUpperCase() : '';
        if (code) {
            facilityMap[code] = (a.allocation_amount !== null && a.allocation_amount !== undefined)
                ? a.allocation_amount
                : (a.allocation_percentage || '');
        }
    });
    document.querySelectorAll('.modal-alloc').forEach(inp => {
        const v = facilityMap[inp.dataset.facility];
        const fv = parseFloat(String(v ?? 0).replace(/,/g, ''));
        inp.value = isNaN(fv) ? '0.00' : fmtNum(fv);
    });

    // Review info
    const reviewSection = document.getElementById('mf_review_section');
    if (data.review_comments || data.reviewed_by) {
        reviewSection.classList.remove('d-none');
        setVal('mf_reviewed_by',      data.reviewed_by  || '');
        setVal('mf_review_date',      data.review_date  ? new Date(data.review_date).toLocaleDateString() : '');
        setVal('mf_review_comments',  data.review_comments || '');
    } else {
        reviewSection.classList.add('d-none');
    }

    // Approve / Reject buttons — visible only for Pending Review + reviewer/approver
    const canActOnReview = window._currentUser && (window._currentUser.can_approve || window._currentUser.can_review);
    const isPendingReview = data.status === 'Pending Review';
    const isRejected      = data.status === 'Rejected';
    const approveBtn = document.getElementById('modalApproveBtn');
    const rejectBtn  = document.getElementById('modalRejectBtn');
    const revertBtn  = document.getElementById('modalRevertBtn');
    if (approveBtn) approveBtn.classList.toggle('d-none', !(canActOnReview && isPendingReview && !editMode));
    if (rejectBtn)  rejectBtn.classList.toggle('d-none',  !(canActOnReview && isPendingReview && !editMode));
    if (revertBtn)  revertBtn.classList.toggle('d-none',  !(canActOnReview && isRejected && !editMode));

    // Files / Attachments — clear staged state and render
    window._stagedFiles        = [];
    window._stagedDeletes      = new Set();
    window._stagedReplacements = new Set();   // names of staged files replacing an existing one
    populateModalFiles(data.files || [], editMode);

    // Wire file input to stage on change (edit mode)
    const fileInput = document.getElementById('mf_file_input');
    if (fileInput) {
        fileInput.onchange = null;
        if (editMode) {
            fileInput.onchange = function() {
                const newFiles = Array.from(this.files);
                const warnings = [];
                newFiles.forEach(f => {
                    // Check for a name collision with an existing (non-pending-delete) server file
                    const dup = window._serverFiles.find(
                        sf => sf.file_name.toLowerCase() === f.name.toLowerCase()
                              && !window._stagedDeletes.has(sf.id)
                    );
                    if (dup) {
                        window._stagedDeletes.add(dup.id);
                        window._stagedReplacements.add(f.name);
                        warnings.push(f.name);
                    }
                    window._stagedFiles.push(f);
                });
                this.value = '';
                if (warnings.length) {
                    showModalAlert(
                        `<strong>Note:</strong> The following file(s) will <strong>replace</strong> the existing version when you click Save Changes: <em>${warnings.join(', ')}</em>`,
                        'warning'
                    );
                }
                renderModalFiles(window._serverFiles, window._editMode);
            };
        }
    }

    // Enable / disable all editable modal fields
    document.querySelectorAll('.modal-field').forEach(el => {
        el.disabled = !editMode;
    });
    // Always lock metadata
    ['mf_initiative_type', 'mf_status', 'mf_created_by'].forEach(elId => {
        const el = document.getElementById(elId);
        if (el) el.disabled = true;
    });

    // Status-specific notices in edit mode
    const _mac = document.getElementById('modalAlertContainer');
    if (_mac && editMode) {
        if (data.status === 'Rejected') {
            _mac.innerHTML = `<div class="alert alert-warning py-2 mb-2 small">
                <i class="fas fa-exclamation-triangle me-1"></i>
                <strong>Rejected initiative:</strong> Saving changes will resubmit this initiative for <strong>Pending Review</strong>.
            </div>`;
        } else {
            _mac.innerHTML = '';
        }
    }

    // Title & Save button
    document.getElementById('modalTitle').textContent = editMode ? 'Edit Initiative' : 'View Initiative';
    document.getElementById('modalSaveBtn').classList.toggle('d-none', !editMode);

    // Wire up live calculations and trigger initial display
    setupModalCalculations(type);

    // In edit mode, snapshot field values AFTER calculations have settled
    if (editMode) {
        setTimeout(() => captureModalSnapshot(type), 50);
    }
}

// Set up auto-calculations inside the view/edit modal
function setupModalCalculations(type) {
    const fmt2 = n => n.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});

    // ── Cost Savings ──────────────────────────────────────────────────
    if (type === 'Cost Savings') {
        const baseline    = document.getElementById('mf_baseline_spend');
        const expected    = document.getElementById('mf_expected_spend');
        const annual      = document.getElementById('mf_annual_savings');
        const total       = document.getElementById('mf_total_savings');
        const hint        = document.getElementById('mf_total_savings_hint');
        const startDate   = document.getElementById('mf_start_date');
        const endDate     = document.getElementById('mf_end_date');

        function getDurationYears() {
            if (!startDate.value || !endDate.value) return null;
            const s = new Date(startDate.value), e = new Date(endDate.value);
            if (e <= s) return null;
            return (e - s) / (365.25 * 24 * 60 * 60 * 1000);
        }

        function calcSavings() {
            const b = numVal(baseline.value);
            const n = numVal(expected.value);
            const savings = b - n;
            annual.value = savings !== 0 ? fmtNum(Math.round(savings)) : '';
            calcTotal();
        }

        function calcTotal() {
            const ann = numVal(annual.value);
            const dur = getDurationYears();
            if (dur !== null && ann !== 0) {
                const t = Math.round(ann * dur);
                total.value = fmtNum(t);
                if (hint) hint.textContent = `Calculated: $${Math.round(ann).toLocaleString('en-US')} × ${dur.toFixed(2)} yrs = $${t.toLocaleString('en-US')}`;
            } else {
                total.value = '';
                if (hint) hint.textContent = 'Calculated: Annual Expected Savings × Duration (years)';
            }
            updateAllocTotal();
        }

        baseline.addEventListener('input',  calcSavings);
        expected.addEventListener('input',  calcSavings);
        annual.addEventListener('input',    calcTotal);
        startDate.addEventListener('change', calcTotal);
        endDate.addEventListener('change',   calcTotal);
        total.addEventListener('input', updateAllocTotal);

        // Trigger on open
        calcTotal();
    }

    // ── Cost Avoidance ────────────────────────────────────────────────
    if (type === 'Cost Avoidance') {
        const original  = document.getElementById('mf_original_quote');
        const newQ      = document.getElementById('mf_new_quote');
        const avoidance = document.getElementById('mf_avoidance_amount');

        function calcAvoidance() {
            const o = numVal(original.value);
            const n = numVal(newQ.value);
            const a = o - n;
            avoidance.value = a !== 0 ? fmtNum(a) : '';
            updateAllocTotal();
        }

        original.addEventListener('input',  calcAvoidance);
        newQ.addEventListener('input',      calcAvoidance);
        avoidance.addEventListener('input', updateAllocTotal);

        // Trigger on open
        calcAvoidance();
    }

    // ── Rebate ────────────────────────────────────────────────────────
    if (type === 'Rebate') {
        const rebateAmt = document.getElementById('mf_rebate_amount');
        if (rebateAmt) rebateAmt.addEventListener('input', updateAllocTotal);
    }

    // ── Facility allocation total + remaining ─────────────────────────
    function getMainAmount() {
        if (type === 'Cost Savings')   return numVal(document.getElementById('mf_total_savings').value);
        if (type === 'Cost Avoidance') return numVal(document.getElementById('mf_avoidance_amount').value);
        if (type === 'Rebate')         return numVal(document.getElementById('mf_rebate_amount').value);
        return 0;
    }

    function updateAllocTotal() {
        let total = 0;
        document.querySelectorAll('.modal-alloc').forEach(inp => { total += numVal(inp.value); });
        total = Math.round(total * 100) / 100;

        const totalSpan     = document.getElementById('mf_alloc_total');
        const remainingSpan = document.getElementById('mf_alloc_remaining');
        if (totalSpan) totalSpan.textContent = fmt2(total);

        if (remainingSpan) {
            const mainAmt   = getMainAmount();
            const remaining = Math.round((mainAmt - total) * 100) / 100;
            const absRem    = Math.abs(remaining);
            const tolerance = 0.01;
            if (mainAmt <= 0) {
                remainingSpan.className = '';
                remainingSpan.innerHTML = '';
            } else if (absRem <= tolerance) {
                remainingSpan.className = 'fw-semibold text-success';
                remainingSpan.innerHTML = '<i class="fas fa-check-circle"></i> Fully Allocated';
            } else if (remaining > tolerance) {
                remainingSpan.className = 'fw-semibold text-warning';
                remainingSpan.innerHTML = `<i class="fas fa-minus-circle"></i> Remaining: $${fmt2(absRem)}`;
            } else {
                remainingSpan.className = 'fw-semibold text-danger';
                remainingSpan.innerHTML = `<i class="fas fa-exclamation-circle"></i> Over by: $${fmt2(absRem)}`;
            }
        }
    }

    // Wire alloc inputs and run immediately
    document.querySelectorAll('.modal-alloc').forEach(inp => inp.addEventListener('input', updateAllocTotal));
    updateAllocTotal();
}

// Validate edit modal required fields — mirrors each form's required set
function captureModalSnapshot(type) {
    const getVal   = id => { const el = document.getElementById(id); return el ? el.value : ''; };
    const getRadio = n  => { const el = document.querySelector(`input[name="${n}"]:checked`); return el ? el.value : ''; };

    const snap = {
        description:        getVal('mf_description'),
        contract_category:  getVal('mf_contract_category'),
        contract_number:    getVal('mf_contract_number'),
        contract_source:    getRadio('mf_contract_source_r'),
        vendor_name:        getVal('mf_vendor_name'),
        wave_initiative_id: getVal('mf_wave_initiative_id'),
    };
    if (type === 'Cost Savings') {
        Object.assign(snap, {
            savings_type:          getRadio('mf_savings_type'),
            gpo_tier:              getVal('mf_gpo_tier_cs'),
            start_date:            getVal('mf_start_date'),
            end_date:              getVal('mf_end_date'),
            baseline_spend:        numVal(getVal('mf_baseline_spend')),
            expected_spend:        numVal(getVal('mf_expected_spend')),
            annual_savings_amount: numVal(getVal('mf_annual_savings')),
            total_savings_amount:  numVal(getVal('mf_total_savings')),
        });
    } else if (type === 'Cost Avoidance') {
        Object.assign(snap, {
            avoidance_type:    getRadio('mf_avoidance_type'),
            strata_project_id: getVal('mf_strata_project_id'),
            po_number:         getVal('mf_po_number'),
            po_date:           getVal('mf_po_date'),
            avoidance_date:    getVal('mf_avoidance_date'),
            original_quote:    numVal(getVal('mf_original_quote')),
            new_quote:         numVal(getVal('mf_new_quote')),
            avoidance_amount:  numVal(getVal('mf_avoidance_amount')),
        });
    } else if (type === 'Rebate') {
        Object.assign(snap, {
            rebate_type:         getVal('mf_rebate_type'),
            gpo_tier:            getVal('mf_gpo_tier_rb'),
            rebate_amount:       numVal(getVal('mf_rebate_amount')),
            transaction_date:    getVal('mf_transaction_date'),
            transaction_type:    getRadio('mf_transaction_type'),
            transaction_number:  getVal('mf_transaction_number'),
        });
    }
    const allocs = {};
    document.querySelectorAll('.modal-alloc').forEach(inp => { allocs[inp.dataset.facility] = numVal(inp.value); });
    snap._allocations = allocs;

    window._originalModalSnapshot = snap;
}

const _FIELD_LABELS = {
    description:           { label: 'Description' },
    contract_category:     { label: 'Contract Category' },
    contract_number:       { label: 'Contract ID' },
    contract_source:       { label: 'Contract Source' },
    vendor_name:           { label: 'Vendor Name' },
    wave_initiative_id:    { label: 'Wave Initiative ID' },
    savings_type:          { label: 'Savings Type' },
    gpo_tier:              { label: 'GPO Tier' },
    start_date:            { label: 'Start Date' },
    end_date:              { label: 'End Date' },
    baseline_spend:        { label: 'Baseline Spend',        currency: true },
    expected_spend:        { label: 'Expected Spend',        currency: true },
    annual_savings_amount: { label: 'Annual Savings',        currency: true },
    total_savings_amount:  { label: 'Total Savings',         currency: true },
    avoidance_type:        { label: 'Avoidance Type' },
    strata_project_id:     { label: 'Strata Project ID' },
    po_number:             { label: 'PO Number' },
    po_date:               { label: 'PO Date' },
    avoidance_date:        { label: 'Avoidance Date' },
    original_quote:        { label: 'Original Quote',        currency: true },
    new_quote:             { label: 'New Quote',             currency: true },
    avoidance_amount:      { label: 'Avoidance Amount',      currency: true },
    rebate_type:           { label: 'Rebate Type' },
    rebate_amount:         { label: 'Rebate Amount',         currency: true },
    transaction_date:      { label: 'Transaction Date' },
    transaction_type:      { label: 'Transaction Type' },
    transaction_number:    { label: 'Transaction Number' },
};

function _fmtSummaryVal(key, val) {
    if (val === '' || val === null || val === undefined) return '<em class="text-muted">—</em>';
    const meta = _FIELD_LABELS[key];
    if (meta && meta.currency) {
        // Use numVal so formatted strings like "1,234.00" are parsed correctly
        const n = numVal(val);
        return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    return String(val).replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function buildChangeSummary(payload, type) {
    const snap = window._originalModalSnapshot || {};
    const fieldRows = [];

    // Field-by-field diff (skip _allocations / facility_allocations — handled separately)
    Object.entries(payload).forEach(([key, newVal]) => {
        if (key === 'facility_allocations') return;
        const oldVal = snap[key] !== undefined ? snap[key] : '';
        const oldStr = String(oldVal ?? '').trim();
        const newStr = String(newVal ?? '').trim();
        if (oldStr !== newStr) {
            const meta  = _FIELD_LABELS[key];
            const label = meta ? meta.label : key;
            fieldRows.push(`
                <tr>
                    <td class="fw-semibold text-nowrap">${label}</td>
                    <td class="text-danger text-break">${_fmtSummaryVal(key, oldStr)}</td>
                    <td class="text-success text-break">${_fmtSummaryVal(key, newStr)}</td>
                </tr>`);
        }
    });

    // Facility allocation diffs
    const oldAllocs = snap._allocations || {};
    (payload.facility_allocations || []).forEach(({ facility_code, allocation_amount }) => {
        const oldRaw = oldAllocs[facility_code] ?? 0;   // already a raw number from snapshot
        const newRaw = allocation_amount ?? 0;           // raw number from payload
        if (Math.abs(numVal(oldRaw) - numVal(newRaw)) > 0.005) {
            fieldRows.push(`
                <tr>
                    <td class="fw-semibold text-nowrap">Allocation – ${facility_code}</td>
                    <td class="text-danger">${_fmtSummaryVal('baseline_spend', oldRaw || '0')}</td>
                    <td class="text-success">${_fmtSummaryVal('baseline_spend', newRaw || '0')}</td>
                </tr>`);
        }
    });

    // Staged file changes
    const fileLines = [];
    window._stagedFiles.forEach(f => {
        const isRepl = window._stagedReplacements && window._stagedReplacements.has(f.name);
        fileLines.push(
            isRepl
                ? `<li><span class="badge bg-warning text-dark">Replace</span> ${f.name}</li>`
                : `<li><span class="badge bg-success">Add</span> ${f.name}</li>`
        );
    });
    // Pure deletes (not part of a replacement)
    window._stagedDeletes.forEach(id => {
        const srv = (window._serverFiles || []).find(sf => sf.id === id);
        const nm  = srv ? srv.file_name : `File #${id}`;
        const isRepl = window._stagedReplacements && window._stagedReplacements.has(nm);
        if (!isRepl) {
            fileLines.push(`<li><span class="badge bg-danger">Delete</span> ${nm}</li>`);
        }
    });

    const hasFieldChanges = fieldRows.length > 0;
    const hasFileChanges  = fileLines.length  > 0;

    if (!hasFieldChanges && !hasFileChanges) {
        return '<div class="alert alert-info"><i class="fas fa-info-circle me-1"></i>No changes detected.</div>';
    }

    let html = '';
    if (hasFieldChanges) {
        html += `
            <h6 class="fw-bold text-primary mb-2"><i class="fas fa-edit me-1"></i>Field Changes</h6>
            <div class="table-responsive mb-3">
                <table class="table table-sm table-bordered align-middle">
                    <thead class="table-light">
                        <tr>
                            <th style="width:28%">Field</th>
                            <th style="width:36%">Old Value</th>
                            <th style="width:36%">New Value</th>
                        </tr>
                    </thead>
                    <tbody>${fieldRows.join('')}</tbody>
                </table>
            </div>`;
    }
    if (hasFileChanges) {
        html += `
            <h6 class="fw-bold text-primary mb-2"><i class="fas fa-paperclip me-1"></i>File Changes</h6>
            <ul class="list-unstyled ps-1">${fileLines.join('')}</ul>`;
    }
    return html;
}

// Validate edit modal required fields — mirrors each form's required set
function validateModalForm(type) {
    // Clear previous invalid states
    document.querySelectorAll('#modalForm .is-invalid').forEach(el => el.classList.remove('is-invalid'));
    document.querySelectorAll('#modalForm .modal-radio-invalid').forEach(el => el.classList.remove('modal-radio-invalid', 'border', 'border-danger', 'rounded', 'p-1'));

    const errors = [];

    const req = (elId, label) => {
        const el = document.getElementById(elId);
        if (!el) return;
        if (!el.value.trim()) {
            el.classList.add('is-invalid');
            errors.push(label);
        }
    };
    const reqRadio = (name, label, containerId) => {
        const checked = document.querySelector(`input[name="${name}"]:checked`);
        if (!checked) {
            const cid = containerId || `${name}_radios`;
            const group = document.getElementById(cid);
            if (group) {
                group.classList.add('modal-radio-invalid', 'border', 'border-danger', 'rounded', 'p-1');
            }
            errors.push(label);
        }
    };
    const reqNum = (elId, label) => {
        const el = document.getElementById(elId);
        if (!el) return;
        const val = numVal(el.value);
        if (isNaN(val) || el.value.trim() === '') {
            el.classList.add('is-invalid');
            errors.push(label);
        }
    };

    // Common — all types
    req('mf_description',     'Description');
    req('mf_contract_category', 'Contract Category');
    req('mf_contract_number', 'Contract ID');
    req('mf_vendor_name',     'Vendor Name');
    reqRadio('mf_contract_source_r', 'Contract Source', 'mf_contract_source_radios');

    if (type === 'Cost Savings') {
        reqRadio('mf_savings_type',  'Savings Type');
        req('mf_start_date',         'Start Date');
        req('mf_end_date',           'End Date');
        reqNum('mf_baseline_spend',  'Baseline Spend');
        reqNum('mf_expected_spend',  'Expected Spend');
        reqNum('mf_annual_savings',  'Annual Savings');
        reqNum('mf_total_savings',   'Total Savings');
    } else if (type === 'Cost Avoidance') {
        reqRadio('mf_avoidance_type', 'Avoidance Type');
        req('mf_po_number',           'PO Number');
        req('mf_po_date',             'PO Date');
        req('mf_avoidance_date',      'Avoidance Date');
        reqNum('mf_original_quote',   'Original Quote');
        reqNum('mf_new_quote',        'New Quote');
        reqNum('mf_avoidance_amount', 'Avoidance Amount');
    } else if (type === 'Rebate') {
        req('mf_rebate_type',            'Rebate Type');
        reqNum('mf_rebate_amount',       'Rebate Amount');
        req('mf_transaction_date',       'Transaction Date');
        reqRadio('mf_transaction_type',  'Transaction Type');
        req('mf_transaction_number',     'Transaction Number');
    }

    // Validate facility allocation is fully allocated (amount mode only in modal)
    {
        let allocTotal = 0;
        document.querySelectorAll('.modal-alloc').forEach(inp => { allocTotal += numVal(inp.value); });
        allocTotal = Math.round(allocTotal * 100) / 100;
        const allocTolerance = 0.01;
        const mainAmtId = type === 'Cost Savings'   ? 'mf_total_savings'
                        : type === 'Cost Avoidance' ? 'mf_avoidance_amount'
                        : type === 'Rebate'         ? 'mf_rebate_amount'
                        : null;
        if (mainAmtId) {
            const mainAmt = numVal(document.getElementById(mainAmtId)?.value || '0');
            if (mainAmt > 0 && Math.abs(mainAmt - allocTotal) > allocTolerance) {
                errors.push('Facility Allocation (must be fully allocated)');
                document.getElementById('mf_alloc_remaining')?.scrollIntoView({behavior: 'smooth', block: 'center'});
            }
        }
    }

    if (errors.length > 0) {
        showModalAlert(`Please fill in required fields: ${errors.join(', ')}`, 'warning');
        return false;
    }
    return true;
}

// Save changes from the edit modal — show confirm summary first, then confirmAndSave() does the actual fetch
function saveModalChanges() {
    const id   = window._modalInitiativeId;
    const type = window._modalInitiativeType;
    if (!id || !type) return;

    if (!validateModalForm(type)) return;

    const getVal = elId => { const el = document.getElementById(elId); return el ? el.value : ''; };
    const getRadio = name => { const el = document.querySelector(`input[name="${name}"]:checked`); return el ? el.value : ''; };

    // Common editable field
    const payload = {
        description:       getVal('mf_description'),
        contract_category: getVal('mf_contract_category'),
        contract_number:   getVal('mf_contract_number'),
        contract_source:   getRadio('mf_contract_source_r'),
        vendor_name:       getVal('mf_vendor_name'),
        wave_initiative_id: getVal('mf_wave_initiative_id')
    };

    // Rejected initiatives resubmit for Pending Review on save
    if (window._modalInitiativeStatus === 'Rejected') {
        payload.status = 'Pending Review';
    }

    // Type-specific fields
    if (type === 'Cost Savings') {
        Object.assign(payload, {
            savings_type:          getRadio('mf_savings_type'),
            gpo_tier:              getVal('mf_gpo_tier_cs'),
            start_date:            getVal('mf_start_date'),
            end_date:              getVal('mf_end_date'),
            baseline_spend:        numVal(getVal('mf_baseline_spend')),
            expected_spend:        numVal(getVal('mf_expected_spend')),
            annual_savings_amount: numVal(getVal('mf_annual_savings')),
            total_savings_amount:  numVal(getVal('mf_total_savings'))
        });
    } else if (type === 'Cost Avoidance') {
        Object.assign(payload, {
            avoidance_type:   getRadio('mf_avoidance_type'),
            strata_project_id: getVal('mf_strata_project_id'),
            po_number:        getVal('mf_po_number'),
            po_date:          getVal('mf_po_date'),
            avoidance_date:   getVal('mf_avoidance_date'),
            original_quote:   numVal(getVal('mf_original_quote')),
            new_quote:        numVal(getVal('mf_new_quote')),
            avoidance_amount: numVal(getVal('mf_avoidance_amount'))
        });
    } else if (type === 'Rebate') {
        Object.assign(payload, {
            rebate_type:        getVal('mf_rebate_type'),
            gpo_tier:           getVal('mf_gpo_tier_rb'),
            rebate_amount:      numVal(getVal('mf_rebate_amount')),
            transaction_date:   getVal('mf_transaction_date'),
            transaction_type:   getRadio('mf_transaction_type'),
            transaction_number: getVal('mf_transaction_number')
        });
    }

    // Facility allocations — send all 8 as array, default 0 when blank
    const facilityAllocations = [];
    document.querySelectorAll('.modal-alloc').forEach(inp => {
        facilityAllocations.push({
            facility_code:     inp.dataset.facility,
            allocation_amount: numVal(inp.value)
        });
    });
    payload.facility_allocations = facilityAllocations;

    const endpointMap = {
        'Cost Savings':    'cost-savings',
        'Cost Avoidance':  'cost-avoidance',
        'Rebate':          'rebates'
    };
    const endpoint = endpointMap[type];
    if (!endpoint) return;

    // Build and show the change summary confirmation view
    const summaryHtml = buildChangeSummary(payload, type);
    document.getElementById('confirmChangesBody').innerHTML = summaryHtml;
    document.getElementById('modalForm').classList.add('d-none');
    document.getElementById('mf_confirmView').classList.remove('d-none');
    document.getElementById('modalSaveBtn').classList.add('d-none');
    document.getElementById('mf_goBackBtn').classList.remove('d-none');
    document.getElementById('mf_confirmSaveBtn').classList.remove('d-none');

    // Store pending work for confirmAndSave()
    window._pendingPayload  = payload;
    window._pendingEndpoint = endpoint;
}

function goBackToForm() {
    document.getElementById('mf_confirmView').classList.add('d-none');
    document.getElementById('modalForm').classList.remove('d-none');
    document.getElementById('mf_goBackBtn').classList.add('d-none');
    document.getElementById('mf_confirmSaveBtn').classList.add('d-none');
    document.getElementById('modalSaveBtn').classList.remove('d-none');
}

function confirmAndSave() {
    const id       = window._modalInitiativeId;
    const payload  = window._pendingPayload;
    const endpoint = window._pendingEndpoint;
    if (!id || !payload || !endpoint) return;

    const confirmBtn = document.getElementById('mf_confirmSaveBtn');
    const goBackBtn  = document.getElementById('mf_goBackBtn');
    confirmBtn.disabled = true;
    goBackBtn.disabled  = true;
    confirmBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Saving…';

    fetch(`/api/${endpoint}/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(r => r.json())
    .then(resp => {
        if (resp.error) {
            // Go back to form view and show error
            goBackToForm();
            showModalAlert(resp.error, 'danger');
        } else {
            // Flush staged file changes before closing
            flushStagedFileChanges(id).then(fileErrors => {
                if (fileErrors.length) {
                    goBackToForm();
                    showModalAlert('Initiative saved, but file errors: ' + fileErrors.join('; '), 'warning');
                } else {
                    bootstrap.Modal.getInstance(document.getElementById('actionModal')).hide();
                    showAlert('Initiative updated successfully', 'success');
                }
                loadInitiatives();
            });
        }
    })
    .catch(err => {
        console.error('Error saving:', err);
        goBackToForm();
        showModalAlert('Error saving changes', 'danger');
    })
    .finally(() => {
        confirmBtn.disabled = false;
        goBackBtn.disabled  = false;
        confirmBtn.innerHTML = '<i class="fas fa-check-circle"></i> Confirm &amp; Save';
    });
}

// Revert rejected initiative from modal footer
function revertInitiativeFromModal() {
    const id = window._modalInitiativeId;
    if (!id) return;
    if (confirm('Revert this initiative to Pending Review? The rejection comment will be cleared.')) {
        fetch(`/api/initiatives/${id}/revert`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
        .then(r => r.json())
        .then(data => {
            if (data.message) {
                bootstrap.Modal.getInstance(document.getElementById('actionModal'))?.hide();
                showAlert('Initiative reverted to Pending Review', 'success');
                loadInitiatives();
            } else {
                showModalAlert(data.error || 'Error reverting initiative', 'danger');
            }
        })
        .catch(() => showModalAlert('Error reverting initiative', 'danger'));
    }
}

// Approve initiative from modal footer
function approveInitiativeFromModal() {
    const id = window._modalInitiativeId;
    if (!id) return;
    if (confirm('Are you sure you want to approve this initiative?')) {
        fetch(`/api/initiatives/${id}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
        .then(r => r.json())
        .then(data => {
            if (data.message) {
                bootstrap.Modal.getInstance(document.getElementById('actionModal'))?.hide();
                showAlert('Initiative approved successfully', 'success');
                loadInitiatives();
            } else {
                showModalAlert(data.error || 'Error approving initiative', 'danger');
            }
        })
        .catch(() => showModalAlert('Error approving initiative', 'danger'));
    }
}

// Approve initiative
function approveInitiative(id) {
    if (confirm('Are you sure you want to approve this initiative?')) {
        fetch(`/api/initiatives/${id}/approve`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.message) {
                showAlert('Initiative approved successfully', 'success');
                loadInitiatives();
            } else {
                showAlert(data.error || 'Error approving initiative', 'danger');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showAlert('Error approving initiative', 'danger');
        });
    }
}

// Reject initiative
function rejectInitiative(id) {
    currentInitiativeId = id;
    // close action modal if open so reject modal can show cleanly
    const actionModalInst = bootstrap.Modal.getInstance(document.getElementById('actionModal'));
    if (actionModalInst) {
        actionModalInst.hide();
        document.getElementById('actionModal').addEventListener('hidden.bs.modal', function openReject() {
            this.removeEventListener('hidden.bs.modal', openReject);
            new bootstrap.Modal(document.getElementById('rejectModal')).show();
        });
    } else {
        new bootstrap.Modal(document.getElementById('rejectModal')).show();
    }
}

// Submit rejection
function submitRejection() {
    const comment = document.getElementById('rejectComment').value.trim();
    
    if (!comment) {
        showAlert('Please enter a rejection reason', 'warning');
        return;
    }
    
    fetch(`/api/initiatives/${currentInitiativeId}/reject`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ comments: comment })
    })
    .then(response => response.json())
    .then(data => {
        if (data.message) {
            showAlert('Initiative rejected', 'success');
            bootstrap.Modal.getInstance(document.getElementById('rejectModal')).hide();
            document.getElementById('rejectComment').value = '';
            loadInitiatives();
        } else {
            showAlert(data.error || 'Error rejecting initiative', 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showAlert('Error rejecting initiative', 'danger');
    });
}

// Toggle show-deleted view (admin only)
function toggleShowDeleted() {
    window._showDeleted = !window._showDeleted;
    const btn = document.getElementById('toggleDeletedBtn');
    if (btn) {
        if (window._showDeleted) {
            btn.innerHTML = '<i class="fas fa-eye-slash"></i> Hide Deleted';
            btn.classList.replace('btn-outline-danger', 'btn-danger');
        } else {
            btn.innerHTML = '<i class="fas fa-trash-alt"></i> Show Deleted';
            btn.classList.replace('btn-danger', 'btn-outline-danger');
        }
    }
    loadInitiatives();
}

// Delete (soft-delete) an initiative
function deleteInitiative(id) {
    if (!confirm('Delete this initiative? Admins can restore it later.')) return;
    fetch(`/api/initiatives/${id}`, { method: 'DELETE' })
        .then(r => r.json())
        .then(data => {
            if (data.message) {
                showAlert('Initiative deleted', 'success');
                loadInitiatives();
            } else {
                showAlert(data.error || 'Error deleting initiative', 'danger');
            }
        })
        .catch(() => showAlert('Error deleting initiative', 'danger'));
}

// Restore a soft-deleted initiative (admin only)
function restoreInitiative(id) {
    if (!confirm('Restore this initiative?')) return;
    fetch(`/api/initiatives/${id}/restore`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
        .then(r => r.json())
        .then(data => {
            if (data.message) {
                showAlert('Initiative restored', 'success');
                loadInitiatives();
            } else {
                showAlert(data.error || 'Error restoring initiative', 'danger');
            }
        })
        .catch(() => showAlert('Error restoring initiative', 'danger'));
}

// Utility functions
function showLoading() {
    const overlay = document.createElement('div');
    overlay.className = 'loading-overlay';
    overlay.id = 'loadingOverlay';
    overlay.innerHTML = '<div class="loading-spinner"></div>';
    document.body.appendChild(overlay);
}

function hideLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.remove();
    }
}

// ── File Attachments ─────────────────────────────────────────────────────────
function fmtFileSize(bytes) {
    if (!bytes) return '0 B';
    const k = 1024, sizes = ['B','KB','MB','GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return (bytes / Math.pow(k, i)).toFixed(1) + ' ' + sizes[i];
}

function fileTypeIcon(ext) {
    const e = (ext || '').toLowerCase();
    if (['pdf'].includes(e))                              return 'fas fa-file-pdf text-danger';
    if (['xls','xlsx'].includes(e))                       return 'fas fa-file-excel text-success';
    if (['doc','docx'].includes(e))                       return 'fas fa-file-word text-primary';
    if (['ppt','pptx'].includes(e))                       return 'fas fa-file-powerpoint text-warning';
    if (['png','jpg','jpeg','gif'].includes(e))           return 'fas fa-file-image text-info';
    if (['zip','rar','7z'].includes(e))                   return 'fas fa-file-archive text-secondary';
    return 'fas fa-file text-secondary';
}

// Store the server file list so renderModalFiles can always access it
window._serverFiles        = [];
window._stagedFiles        = [];
window._stagedDeletes      = new Set();
window._stagedReplacements = new Set();

function populateModalFiles(files, editMode) {
    window._serverFiles = files;
    window._editMode    = editMode;
    const uploadArea = document.getElementById('mf_file_upload_area');
    if (editMode) {
        uploadArea && uploadArea.classList.remove('d-none');
    } else {
        uploadArea && uploadArea.classList.add('d-none');
    }
    renderModalFiles(files, editMode);
}

function renderModalFiles(serverFiles, editMode) {
    if (editMode === undefined) editMode = window._editMode || false;
    const container = document.getElementById('mf_file_list');
    if (!container) return;
    container.innerHTML = '';

    const allEmpty = !serverFiles.length && !window._stagedFiles.length;
    if (allEmpty) {
        container.innerHTML = '<span class="text-muted small">No attachments.</span>';
        return;
    }

    // Existing server files
    serverFiles.forEach(f => {
        const pendingDelete = window._stagedDeletes.has(f.id);
        const row = document.createElement('div');
        row.className = 'd-flex align-items-center gap-2 py-1 border-bottom' + (pendingDelete ? ' opacity-50' : '');
        const icon = fileTypeIcon(f.file_type);
        const size = fmtFileSize(f.file_size);
        const uploader = f.uploaded_by ? f.uploaded_by.full_name : '';
        row.innerHTML = `
            <i class="${icon}"></i>
            ${ pendingDelete
                ? `<span class="text-truncate small flex-grow-1 text-decoration-line-through text-danger" title="${f.file_name}">${f.file_name}</span>`
                : `<a href="/api/initiatives/${f.initiative_id}/files/${f.id}/download"
                      class="text-truncate small flex-grow-1" title="${f.file_name}">${f.file_name}</a>` }
            <span class="text-muted small text-nowrap">${size}</span>
            ${uploader ? `<span class="text-muted small text-nowrap d-none d-md-inline">${uploader}</span>` : ''}
            ${ editMode ? (pendingDelete
                ? `<button type="button" class="btn btn-sm btn-outline-secondary py-0 px-1" onclick="unstageDelete(${f.id})" title="Undo remove"><i class="fas fa-undo"></i></button>`
                : `<button type="button" class="btn btn-sm btn-outline-danger py-0 px-1" onclick="stageDeleteFile(${f.id})" title="Remove file"><i class="fas fa-trash-alt"></i></button>`
            ) : '' }
        `;
        container.appendChild(row);
    });

    // Staged new files (not yet uploaded)
    window._stagedFiles.forEach((f, idx) => {
        const ext = f.name.split('.').pop().toLowerCase();
        const isReplacement = window._stagedReplacements && window._stagedReplacements.has(f.name);
        const row = document.createElement('div');
        row.className = 'd-flex align-items-center gap-2 py-1 border-bottom';
        row.innerHTML = `
            <i class="${fileTypeIcon(ext)}"></i>
            <span class="text-truncate small flex-grow-1" title="${f.name}">${f.name}</span>
            ${ isReplacement
                ? `<span class="badge bg-warning text-dark small" title="Will overwrite the existing file with this name">Replaces existing</span>`
                : `<span class="badge bg-info text-dark small">Pending</span>` }
            <span class="text-muted small text-nowrap">${fmtFileSize(f.size)}</span>
            <button type="button" class="btn btn-sm btn-outline-danger py-0 px-1" onclick="removeStagedFile(${idx})" title="Cancel"><i class="fas fa-times"></i></button>
        `;
        container.appendChild(row);
    });
}

function stageDeleteFile(fileId) {
    window._stagedDeletes.add(fileId);
    renderModalFiles(window._serverFiles, window._editMode);
}

function unstageDelete(fileId) {
    window._stagedDeletes.delete(fileId);
    renderModalFiles(window._serverFiles, window._editMode);
}

function removeStagedFile(idx) {
    const f = window._stagedFiles[idx];
    // If this was a replacement, undo the auto-staged delete for the existing file
    if (f && window._stagedReplacements && window._stagedReplacements.has(f.name)) {
        const dup = window._serverFiles.find(
            sf => sf.file_name.toLowerCase() === f.name.toLowerCase()
        );
        if (dup) window._stagedDeletes.delete(dup.id);
        window._stagedReplacements.delete(f.name);
    }
    window._stagedFiles.splice(idx, 1);
    renderModalFiles(window._serverFiles, window._editMode);
}

async function flushStagedFileChanges(initiativeId) {
    const errors = [];

    // Delete staged files FIRST — important for replacements: the old physical
    // file must be removed before the new upload writes to the same path.
    for (const fileId of window._stagedDeletes) {
        try {
            const r = await fetch(`/api/initiatives/${initiativeId}/files/${fileId}`, { method: 'DELETE' });
            const d = await r.json();
            if (d.error) errors.push(d.error);
            else window._serverFiles = d.files || [];
        } catch (e) { errors.push(`Delete file ${fileId} failed`); }
    }
    window._stagedDeletes.clear();

    // Upload new files after deletions so replacements are saved cleanly
    if (window._stagedFiles.length) {
        const formData = new FormData();
        window._stagedFiles.forEach(f => formData.append('files', f));
        try {
            const r = await fetch(`/api/initiatives/${initiativeId}/files`, { method: 'POST', body: formData });
            const d = await r.json();
            if (d.error) errors.push(d.error);
            else window._serverFiles = d.files || [];
        } catch (e) { errors.push('File upload failed'); }
        window._stagedFiles = [];
    }

    return errors;
}

function showModalAlert(message, type) {
    const container = document.getElementById('modalAlertContainer');
    if (!container) { showAlert(message, type); return; }
    container.innerHTML = `
        <div class="alert alert-${type} alert-dismissible fade show mb-3" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>`;
    // Auto-dismiss after 8 seconds
    setTimeout(() => { container.innerHTML = ''; }, 8000);
}

function showAlert(message, type) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const container = document.querySelector('.container-fluid');
    container.insertBefore(alertDiv, container.firstChild);
    
    setTimeout(() => {
        alertDiv.remove();
    }, 5000);
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}
