// Cost Avoidance Form JavaScript

let editInitiativeId = null;
let existingFileCount = 0;
let stagedNewFiles = [];
const ALLOWED_UPLOAD_EXTENSIONS = new Set(['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'png', 'jpg', 'jpeg', 'gif', 'zip']);
const ACCEPTED_UPLOAD_FORMATS = 'Accepted formats: PDF, Word, Excel, PowerPoint, Images, ZIP (Max 500MB total).';

document.addEventListener('DOMContentLoaded', async function() {
    await loadContractCategorySelect('contractCategory');
    await initializePrimeContractLookup({
        contractInputId: 'contractId',
        vendorInputId: 'vendorName',
        contractListId: 'contractIdOptions',
        vendorListId: 'vendorNameOptions',
    });
    initializeForm();
    setupEventListeners();
    checkEditMode();
});

function initializeForm() {
    // Calculate avoidance amount when original or new quote changes
    const originalQuote = document.getElementById('originalQuote');
    const newQuote = document.getElementById('newQuote');
    const avoidanceAmount = document.getElementById('avoidanceAmount');
    
    function calculateAvoidance() {
        const original = numVal(originalQuote.value);
        const newQ = numVal(newQuote.value);
        const avoidance = original - newQ;
        avoidanceAmount.value = fmtNum(avoidance);
        avoidanceAmount.dispatchEvent(new Event('input'));
    }
    
    originalQuote.addEventListener('input', calculateAvoidance);
    newQuote.addEventListener('input', calculateAvoidance);
    
    setupFileUpload();
    setupFacilityAllocation();
}

function setupEventListeners() {
    const form = document.getElementById('costAvoidanceForm');
    form.addEventListener('submit', handleSubmit);
    installInvalidHighlightClearers(form);
}

function installInvalidHighlightClearers(form) {
    const fields = form.querySelectorAll('input, select, textarea');
    fields.forEach(field => {
        const eventName = field.type === 'radio' || field.type === 'checkbox' || field.tagName === 'SELECT'
            ? 'change'
            : 'input';
        field.addEventListener(eventName, () => {
            if (field.type === 'radio' || field.type === 'checkbox') {
                const groupElem = field.closest('.mb-3') || field.closest('.col-md-6') || field.closest('.form-section');
                if (groupElem) {
                    groupElem.classList.remove('invalid-field-group');
                }
            } else {
                field.classList.remove('is-invalid');
            }
        });
    });
}

function setupFileUpload() {
    const fileInput = document.getElementById('fileUpload');
    const fileList = document.getElementById('fileList');
    
    fileInput.addEventListener('change', function(e) {
        const newFiles = Array.from(e.target.files);
        const invalidFiles = [];
        newFiles.forEach(f => {
            if (!isAllowedUploadFile(f.name)) {
                invalidFiles.push(f.name);
                return;
            }
            if (!stagedNewFiles.some(s => s.name === f.name && s.size === f.size)) {
                stagedNewFiles.push(f);
            }
        });
        // Clear input so the same file can be re-selected after removal
        fileInput.value = '';
        if (invalidFiles.length) {
            showAlert(`File type not allowed: ${formatUploadFileList(invalidFiles)}. ${ACCEPTED_UPLOAD_FORMATS}`, 'warning');
        }
        displayFileList(stagedNewFiles, fileList);
        if (stagedNewFiles.length > 0) fileInput.classList.remove('is-invalid');
    });
}

function isAllowedUploadFile(name) {
    const parts = String(name || '').split('.');
    if (parts.length < 2) return false;
    return ALLOWED_UPLOAD_EXTENSIONS.has(parts.pop().toLowerCase());
}

function formatUploadFileList(names) {
    return names.map(name => String(name || '').replace(/[&<>"']/g, ch => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    }[ch]))).join(', ');
}

function displayFileList(files, container) {
    // Only remove staged (non-existing) file items so that existing file rows
    // (which have id="existing-file-*") are preserved when new files are staged.
    container.querySelectorAll('.file-item:not([id^="existing-file-"])').forEach(el => el.remove());

    files.forEach((file, index) => {
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        fileItem.innerHTML = `
            <span class="file-item-name"><i class="fas fa-file"></i> ${file.name}</span>
            <span class="file-item-size">${formatFileSize(file.size)}</span>
            <span class="file-item-remove" onclick="removeFile(${index})">
                <i class="fas fa-times-circle"></i>
            </span>
        `;
        container.appendChild(fileItem);
    });
}

function displayExistingFiles(files) {
    const fileList = document.getElementById('fileList');
    if (!files || files.length === 0) return;
    const header = document.createElement('div');
    header.className = 'text-muted small mb-1';
    header.innerHTML = '<i class="fas fa-paperclip"></i> Already attached:';
    fileList.appendChild(header);
    files.forEach(file => {
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        fileItem.id = `existing-file-${file.id}`;
        const sizeText = file.file_size ? formatFileSize(file.file_size) : '';
        fileItem.innerHTML = `
            <span class="file-item-name"><i class="fas fa-file"></i> ${file.file_name}</span>
            <span class="file-item-size">${sizeText}</span>
            <span class="file-item-remove" onclick="deleteExistingFile(${file.id}, this.closest('.file-item'))" title="Delete file">
                <i class="fas fa-times-circle"></i>
            </span>
        `;
        fileList.appendChild(fileItem);
    });
}

function deleteExistingFile(fileId, rowEl) {
    if (!editInitiativeId) return;
    // Use stagedNewFiles.length — fileInput is always cleared after staging so .files.length is always 0
    const pendingUploads = stagedNewFiles.length;
    if (existingFileCount <= 1 && pendingUploads === 0) {
        showAlert('At least one file attachment is required. Upload another attachment before deleting this one.', 'warning');
        return;
    }
    if (!confirm('Delete this attachment? This cannot be undone.')) return;
    fetch(`/api/initiatives/${editInitiativeId}/files/${fileId}`, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.error) { showAlert(data.error, 'danger'); return; }
            existingFileCount = Math.max(0, existingFileCount - 1);
            if (rowEl) rowEl.remove();
        })
        .catch(() => showAlert('Error deleting file', 'danger'));
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

function removeFile(index) {
    stagedNewFiles.splice(index, 1);
    displayFileList(stagedNewFiles, document.getElementById('fileList'));
}

function setupFacilityAllocation() {
    const allocationInputs = document.querySelectorAll('.facility-allocation');
    const totalSpan = document.getElementById('totalAllocation');
    const allocationTypePercent = document.getElementById('allocationTypePercent');
    const allocationTypeAmount = document.getElementById('allocationTypeAmount');
    const allocationInstruction = document.getElementById('allocationInstruction');
    const totalAllocationLabel = document.getElementById('totalAllocationLabel');
    const avoidanceAmountInput = document.getElementById('avoidanceAmount');
    
    // Current allocation type (locked to dollar amount)
    let currentAllocationType = 'amount';
    
    function updateAllocationMethod() {
        currentAllocationType = document.querySelector('input[name="allocationType"]:checked').value;
        const isPercentage = currentAllocationType === 'percentage';
        
        // Update UI based on allocation type
        if (isPercentage) {
            // Percentage mode
            allocationInstruction.textContent = 'Allocate cost avoidance percentage across facilities';
            totalAllocationLabel.innerHTML = 'Total Allocation: <span id="totalAllocation">0</span>%';
            
            // Update labels and inputs
            document.querySelectorAll('.allocation-symbol').forEach(span => {
                span.textContent = '%';
            });
            
            allocationInputs.forEach(input => {
                input.max = '100';
                input.value = '0';
            });
            
            // Hide calculation displays
            document.querySelectorAll('.allocation-calc').forEach(el => {
                el.classList.add('d-none');
            });
        } else {
            // Amount mode
            allocationInstruction.textContent = 'Allocate dollar amounts across facilities';
            totalAllocationLabel.innerHTML = 'Total Allocation: $<span id="totalAllocation">0.00</span>';
            
            // Get total from avoidance amount
            const totalAmount = numVal(avoidanceAmountInput.value);
            
            // Update labels and inputs
            document.querySelectorAll('.allocation-symbol').forEach(span => {
                span.textContent = '$';
            });
            
            allocationInputs.forEach(input => {
                input.max = totalAmount;
                input.value = '0';
            });
            
            // Show calculation displays
            document.querySelectorAll('.allocation-calc').forEach(el => {
                el.classList.remove('d-none');
            });
        }
        
        updateTotal();
    }
    
    function updateTotal() {
        let total = 0;
        const isPercentage = currentAllocationType === 'percentage';
        const totalAmount = numVal(avoidanceAmountInput.value);
        
        allocationInputs.forEach(input => {
            const value = numVal(input.value);
            total += value;
            
            // Update calculation display for amount mode
            if (!isPercentage) {
                const facilityCode = input.dataset.facility;
                const calcElement = input.parentElement.querySelector('.allocation-calc');
                if (calcElement && totalAmount > 0) {
                    const percentage = (value / totalAmount * 100).toFixed(2);
                    calcElement.textContent = `${percentage}% of total`;
                }
            }
        });
        
        total = Math.round(total * 100) / 100;
        
        // Update total span with proper formatting
        const totalSpanNew = document.getElementById('totalAllocation');
        if (isPercentage) {
            totalSpanNew.textContent = total;
        } else {
            totalSpanNew.textContent = total.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        }
        
        // Validation
        const expectedTotal = isPercentage ? 100 : totalAmount;
        const tolerance = 0.01; // Allow for rounding differences
        
        // Update remaining allocation display
        const remainingLabel = document.getElementById('remainingAllocationLabel');
        if (remainingLabel && !isPercentage) {
            const remaining = Math.round((totalAmount - total) * 100) / 100;
            const absRemaining = Math.abs(remaining).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
            if (Math.abs(remaining) <= tolerance) {
                remainingLabel.className = 'ms-3 fw-semibold text-success';
                remainingLabel.innerHTML = '<i class="fas fa-check-circle"></i> Fully Allocated';
            } else if (remaining > tolerance) {
                remainingLabel.className = 'ms-3 fw-semibold text-warning-dark';
                remainingLabel.innerHTML = `<i class="fas fa-minus-circle"></i> Remaining: $${absRemaining}`;
            } else {
                remainingLabel.className = 'ms-3 fw-semibold text-danger';
                remainingLabel.innerHTML = `<i class="fas fa-exclamation-circle"></i> Over by: $${absRemaining}`;
            }
        }
        
        return total;
    }
    
    // Event listeners
    allocationInputs.forEach(input => {
        input.addEventListener('input', updateTotal);
    });
    
    // Update total amount when avoidance amount changes
    if (avoidanceAmountInput) {
        avoidanceAmountInput.addEventListener('input', function() {
            if (currentAllocationType === 'amount') {
                const totalAmount = numVal(this.value);
                
                // Update max values for all inputs
                allocationInputs.forEach(input => {
                    input.max = totalAmount;
                });
                
                updateTotal();
            }
        });
    }
    
    // Initialize
    updateAllocationMethod();
}

function validateForm() {
    const form = document.getElementById('costAvoidanceForm');
    let isValid = true;
    
    // Check required fields
    const requiredFields = form.querySelectorAll('[required]');
    const missingFields = [];
    const seenGroups = new Set();
    let firstInvalidField = null;

    requiredFields.forEach(field => {
        if ((field.type === 'radio' || field.type === 'checkbox') && seenGroups.has(field.name)) {
            return;
        }

        const isEmpty = field.type === 'radio' || field.type === 'checkbox'
            ? !form.querySelector(`[name="${field.name}"]:checked`)
            : !field.value.trim();

        if (!isEmpty) {
            if (field.type === 'radio' || field.type === 'checkbox') {
                const groupElem = field.closest('.mb-3') || field.closest('.col-md-6') || field.closest('.form-section');
                if (groupElem) {
                    groupElem.classList.remove('invalid-field-group');
                }
            } else {
                field.classList.remove('is-invalid');
            }
            return;
        }

        if (field.type === 'radio' || field.type === 'checkbox') {
            seenGroups.add(field.name);
            const groupElem = field.closest('.mb-3') || field.closest('.col-md-6') || field.closest('.form-section');
            if (groupElem) {
                groupElem.classList.add('invalid-field-group');
            }
        } else {
            field.classList.add('is-invalid');
        }

        if (!firstInvalidField) {
            firstInvalidField = field;
        }

        const labelText = (() => {
            if (field.id) {
                const label = form.querySelector(`label[for="${field.id}"]`);
                if (label) return label.textContent.trim();
            }
            const group = field.closest('.mb-3, .col-md-6, .col-md-4, .row, .form-section');
            if (group) {
                const label = group.querySelector('label.form-label');
                if (label) return label.textContent.trim();
            }
            if (field.name) {
                return field.name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            }
            return 'Required field';
        })();

        missingFields.push(labelText.replace(/\s*\*+$/, '').trim());
    });

    if (missingFields.length > 0) {
        showAlert(`Please complete the required fields before submitting: ${missingFields.join(', ')}.`, 'warning');
        if (firstInvalidField) {
            firstInvalidField.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        isValid = false;
    }
    
    const avoidanceAmountVal = numVal(document.getElementById('avoidanceAmount')?.value || '0');
    if (avoidanceAmountVal <= 0) {
        showAlert('Cost Avoidance Amount must be greater than 0 before submitting.', 'warning');
        isValid = false;
    }

    // Validate facility allocation is fully allocated (submit only, not draft)
    const allocType = document.querySelector('input[name="allocationType"]:checked')?.value || 'amount';
    let allocTotal = 0;
    document.querySelectorAll('.facility-allocation').forEach(inp => { allocTotal += numVal(inp.value); });
    allocTotal = Math.round(allocTotal * 100) / 100;
    const allocTolerance = 0.01;
    if (allocType === 'percentage') {
        if (Math.abs(allocTotal - 100) > allocTolerance) {
            showAlert('Facility allocations must total 100% before submitting.', 'warning');
            isValid = false;
        }
    } else {
        const mainAmt = numVal(document.getElementById('avoidanceAmount')?.value || '0');
        if (mainAmt > 0 && Math.abs(mainAmt - allocTotal) > allocTolerance) {
            showAlert('Facility allocation must equal the Avoidance Amount before submitting. Please fully allocate the remaining amount.', 'warning');
            isValid = false;
        }
    }

    // Require at least one file attachment (new upload or existing)
    const fileInput = document.getElementById('fileUpload');
    const existingRows = document.querySelectorAll('#fileList [id^="existing-file-"]').length;
    const newFileCount = stagedNewFiles.length;
    if (existingRows + newFileCount === 0) {
        showAlert('At least one supporting document must be attached before submitting.', 'warning');
        if (fileInput) {
            fileInput.classList.add('is-invalid');
            fileInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        isValid = false;
    }

    return isValid;
}

function handleSubmit(e) {
    e.preventDefault();
    
    if (!validateForm()) {
        return;
    }
    
    const formData = new FormData(e.target);
    
    // Add facility allocations with type
    const allocationType = document.querySelector('input[name="allocationType"]:checked').value;
    const facilities = [];
    document.querySelectorAll('.facility-allocation').forEach(input => {
        const value = numVal(input.value);
        if (value > 0) {
            const allocation = {
                facility_code: input.dataset.facility
            };
            
            if (allocationType === 'percentage') {
                allocation.percentage = value;
            } else {
                allocation.amount = value;
            }
            
            facilities.push(allocation);
        }
    });
    
    const jsonData = {
        initiative_type: 'Cost Avoidance',
        wave_id: formData.get('wave_id'),
        contract_category: formData.get('contract_category'),
        contract_number: formData.get('contract_id'),
        contract_source: formData.get('contract_source'),
        strata_project_id: formData.get('strata_project_id'),
        vendor_name: formData.get('vendor_name'),
        description: formData.get('description'),
        avoidance_type: formData.get('avoidance_type'),
        po_number: formData.get('po_number'),
        po_date: formData.get('po_date'),
        avoidance_date: formData.get('avoidance_date'),
        original_quote: numVal(formData.get('original_quote')),
        new_quote: numVal(formData.get('new_quote')),
        avoidance_amount: numVal(formData.get('avoidance_amount')),
        facility_allocations: facilities,
        status: 'Submitted'
    };
    
    showLoading();
    
    fetch(editInitiativeId ? `/api/cost-avoidance/${editInitiativeId}` : '/api/cost-avoidance', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(jsonData)
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.initiative) {
            // Handle file uploads if any
            if (stagedNewFiles.length > 0) {
                uploadFiles(data.initiative.id, stagedNewFiles);
            } else {
                showAlert('Cost Avoidance initiative created successfully!', 'success');
                setTimeout(() => {
                    window.location.href = '/dashboard';
                }, 2000);
            }
        } else {
            showAlert(data.error || 'Error creating initiative', 'danger');
        }
    })
    .catch(error => {
        hideLoading();
        console.error('Error:', error);
        showAlert('Error submitting form', 'danger');
    });
}

function saveDraft() {
    const form = document.getElementById('costAvoidanceForm');
    const formData = new FormData(form);
    
    const facilities = [];
    document.querySelectorAll('.facility-allocation').forEach(input => {
        const percentage = numVal(input.value);
        if (percentage > 0) {
            facilities.push({
                facility_code: input.dataset.facility,
                percentage: percentage
            });
        }
    });
    
    const jsonData = {
        initiative_type: 'Cost Avoidance',
        wave_id: formData.get('wave_id'),
        contract_category: formData.get('contract_category'),
        contract_number: formData.get('contract_id'),
        contract_source: formData.get('contract_source'),
        strata_project_id: formData.get('strata_project_id'),
        vendor_name: formData.get('vendor_name'),
        description: formData.get('description'),
        avoidance_type: formData.get('avoidance_type'),
        po_number: formData.get('po_number'),
        po_date: formData.get('po_date'),
        avoidance_date: formData.get('avoidance_date'),
        original_quote: numVal(formData.get('original_quote')),
        new_quote: numVal(formData.get('new_quote')),
        avoidance_amount: numVal(formData.get('avoidance_amount')),
        facility_allocations: facilities,
        status: 'Draft'
    };

    // Check allocation before uploading
    const draftAllocType = document.querySelector('input[name="allocationType"]:checked')?.value || 'amount';
    let draftAllocTotal = 0;
    document.querySelectorAll('.facility-allocation').forEach(inp => { draftAllocTotal += numVal(inp.value); });
    draftAllocTotal = Math.round(draftAllocTotal * 100) / 100;
    if (draftAllocType === 'percentage') {
        if (draftAllocTotal > 0 && Math.abs(draftAllocTotal - 100) > 0.01) {
            showAlert('Facility allocations must total 100% before saving.', 'warning');
            return;
        }
    } else {
        const mainAmt = numVal(document.getElementById('avoidanceAmount')?.value || '0');
        if (mainAmt > 0 && draftAllocTotal > 0 && Math.abs(mainAmt - draftAllocTotal) > 0.01) {
            showAlert('Facility allocation must equal the Avoidance Amount before saving. Please fully allocate the remaining amount.', 'warning');
            return;
        }
    }

    showLoading();
    
    fetch(editInitiativeId ? `/api/cost-avoidance/${editInitiativeId}` : '/api/cost-avoidance', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(jsonData)
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.initiative) {
            showAlert('Draft saved successfully!', 'success');
            setTimeout(() => {
                window.location.href = '/dashboard';
            }, 2000);
        } else {
            showAlert(data.error || 'Error saving draft', 'danger');
        }
    })
    .catch(error => {
        hideLoading();
        console.error('Error:', error);
        showAlert('Error saving draft', 'danger');
    });
}

function uploadFiles(initiativeId, files) {
    const formData = new FormData();
    Array.from(files).forEach(file => {
        formData.append('files', file);
    });
    
    fetch(`/api/initiatives/${initiativeId}/files`, {
        method: 'POST',
        body: formData
    })
    .then(response => response.json().then(data => ({ ok: response.ok, data })))
    .then(({ ok, data }) => {
        if (!ok || data.error) {
            throw new Error(data.error || 'File upload failed');
        }
        return data;
    })
    .then(data => {
        showAlert('Initiative and files uploaded successfully!', 'success');
        setTimeout(() => {
            window.location.href = '/dashboard';
        }, 2000);
    })
    .catch(error => {
        console.error('Error uploading files:', error);
        showAlert(`Initiative saved, but file upload failed: ${error.message}`, 'warning');
        setTimeout(() => {
            window.location.href = '/dashboard';
        }, 2000);
    });
}

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

function showAlert(message, type) {
    if (window.showGlobalPopup) {
        window.showGlobalPopup(message, type, { autoDismissMs: 5000 });
        return;
    }

    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const container = document.querySelector('.container');
    container.insertBefore(alertDiv, container.firstChild);
    
    setTimeout(() => {
        alertDiv.remove();
    }, 5000);
}

// --- Edit Mode ---

function checkEditMode() {
    const urlParams = new URLSearchParams(window.location.search);
    const id = urlParams.get('id');
    if (id) {
        editInitiativeId = parseInt(id);
        loadInitiativeData(editInitiativeId);
    }
}

async function loadInitiativeData(id) {
    try {
        const response = await fetch(`/api/initiatives/${id}`);
        const data = await response.json();
        const ca = data.cost_avoidance || {};
        setField('waveId', data.wave_id);
        setField('description', data.description);
        setRadio('avoidance_type', ca.avoidance_type);
        setField('strataProjectId', ca.strata_project_id);
        setSelect('contractCategory', ca.contract_category);
        setField('contractId', ca.contract_number);
        await loadPrimeVendorOptions(ca.contract_number, 'vendorNameOptions');
        setRadio('contract_source', ca.contract_source);
        setField('vendorName', ca.vendor_name);
        setField('poNumber', ca.po_number);
        setField('poDate', ca.po_date);
        setField('avoidanceDate', ca.avoidance_date);
        setField('originalQuote', ca.original_quote);
        setField('newQuote', ca.new_quote);
        setField('avoidanceAmount', ca.avoidance_amount);
        (data.facility_allocations || []).forEach(alloc => {
            if (alloc.facility) {
                const input = document.getElementById(alloc.facility.code.toLowerCase());
                if (input) {
                    input.value = alloc.allocation_amount !== null && alloc.allocation_amount !== undefined
                        ? alloc.allocation_amount : (alloc.allocation_percentage || 0);
                    input.dispatchEvent(new Event('input'));
                }
            }
        });
        document.getElementById('originalQuote').dispatchEvent(new Event('input'));
        existingFileCount = (data.files || []).length;
        displayExistingFiles(data.files || []);
    } catch (err) {
        console.error('Error loading initiative:', err);
    }
}

function setField(id, value) {
    const el = document.getElementById(id);
    if (el && value !== null && value !== undefined) el.value = value;
}

function setRadio(name, value) {
    if (!value) return;
    const radio = document.querySelector(`input[name="${name}"][value="${value}"]`);
    if (radio) { radio.checked = true; radio.dispatchEvent(new Event('change')); }
}

function setSelect(id, value) {
    const el = document.getElementById(id);
    if (!el || !value) return;
    const exists = Array.from(el.options || []).some(option => option.value === value);
    if (!exists) {
        const dynamic = document.createElement('option');
        dynamic.value = value;
        dynamic.text = value;
        dynamic.dataset.dynamic = 'true';
        el.appendChild(dynamic);
    }
    el.value = value;
}
