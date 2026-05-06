// Rebate Form JavaScript

let editInitiativeId = null;
let existingFileCount = 0;
let stagedNewFiles = [];

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
    setupFileUpload();
    setupFacilityAllocation();
}

function setupEventListeners() {
    const form = document.getElementById('rebateForm');
    form.addEventListener('submit', handleSubmit);
}

function setupFileUpload() {
    const fileInput = document.getElementById('fileUpload');
    const fileList = document.getElementById('fileList');
    
    fileInput.addEventListener('change', function(e) {
        const newFiles = Array.from(e.target.files);
        newFiles.forEach(f => {
            if (!stagedNewFiles.some(s => s.name === f.name && s.size === f.size)) {
                stagedNewFiles.push(f);
            }
        });
        // Clear input so the same file can be re-selected after removal
        fileInput.value = '';
        displayFileList(stagedNewFiles, fileList);
        if (stagedNewFiles.length > 0) fileInput.classList.remove('is-invalid');
    });
}

function displayFileList(files, container) {
    container.innerHTML = '';
    
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
    const fileInput = document.getElementById('fileUpload');
    const pendingUploads = fileInput ? fileInput.files.length : 0;
    if (existingFileCount <= 1 && pendingUploads === 0) {
        showAlert('At least one file attachment is required. Upload a replacement before deleting this one.', 'warning');
        return;
    }
    if (!confirm('Delete this attachment? This cannot be undone.')) return;
    fetch(`/api/initiatives/${editInitiativeId}/files/${fileId}`, { method: 'DELETE' })
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
    const rebateAmountInput = document.getElementById('rebateAmount');
    
    // Current allocation type (locked to dollar amount)
    let currentAllocationType = 'amount';
    
    function updateAllocationMethod() {
        currentAllocationType = document.querySelector('input[name="allocationType"]:checked').value;
        const isPercentage = currentAllocationType === 'percentage';
        
        // Update UI based on allocation type
        if (isPercentage) {
            // Percentage mode
            allocationInstruction.textContent = 'Allocate rebate percentage across facilities';
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
            
            // Get total from rebate amount
            const totalAmount = numVal(rebateAmountInput.value);
            
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
        const totalAmount = numVal(rebateAmountInput.value);
        
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
    
    // Update total amount when rebate amount changes
    if (rebateAmountInput) {
        rebateAmountInput.addEventListener('input', function() {
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
    const form = document.getElementById('rebateForm');
    let isValid = true;
    
    // Check required fields
    const requiredFields = form.querySelectorAll('[required]');
    requiredFields.forEach(field => {
        if (!field.value.trim()) {
            field.classList.add('is-invalid');
            isValid = false;
        } else {
            field.classList.remove('is-invalid');
        }
    });

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
        const mainAmt = numVal(document.getElementById('rebateAmount')?.value || '0');
        if (mainAmt > 0 && Math.abs(mainAmt - allocTotal) > allocTolerance) {
            showAlert('Facility allocation must equal the Rebate Amount before submitting. Please fully allocate the remaining amount.', 'warning');
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
    
    // Add facility allocations — always send all 8 facilities
    const facilities = [];
    document.querySelectorAll('.facility-allocation').forEach(input => {
        facilities.push({
            facility_code:     input.dataset.facility,
            allocation_amount: numVal(input.value) || 0
        });
    });

    const jsonData = {
        initiative_type: 'Rebate',
        contract_category: formData.get('contract_category'),
        contract_number: formData.get('contract_id'),
        contract_source: formData.get('contract_source'),
        vendor_name: formData.get('vendor_name'),
        wave_initiative_id: formData.get('wave_initiative_id'),
        description: formData.get('description'),
        rebate_type: formData.get('rebate_type'),
        transaction_number: formData.get('transaction_number'),
        transaction_date: formData.get('transaction_date'),
        transaction_type: formData.get('transaction_type'),
        rebate_amount: numVal(formData.get('rebate_amount')),
        facility_allocations: facilities,
        status: 'Submitted'
    };
    
    showLoading();
    
    fetch(editInitiativeId ? `/api/rebates/${editInitiativeId}` : '/api/rebates', {
        method: editInitiativeId ? 'PUT' : 'POST',
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
                showAlert('Rebate initiative created successfully!', 'success');
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
    const form = document.getElementById('rebateForm');
    const formData = new FormData(form);
    
    const facilities = [];
    document.querySelectorAll('.facility-allocation').forEach(input => {
        facilities.push({
            facility_code:     input.dataset.facility,
            allocation_amount: numVal(input.value) || 0
        });
    });

    const jsonData = {
        initiative_type: 'Rebate',
        contract_category: formData.get('contract_category'),
        contract_number: formData.get('contract_id'),
        contract_source: formData.get('contract_source'),
        vendor_name: formData.get('vendor_name'),
        wave_initiative_id: formData.get('wave_initiative_id'),
        description: formData.get('description'),
        rebate_type: formData.get('rebate_type'),
        transaction_number: formData.get('transaction_number'),
        transaction_date: formData.get('transaction_date'),
        transaction_type: formData.get('transaction_type'),
        rebate_amount: numVal(formData.get('rebate_amount')),
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
        const mainAmt = numVal(document.getElementById('rebateAmount')?.value || '0');
        if (mainAmt > 0 && draftAllocTotal > 0 && Math.abs(mainAmt - draftAllocTotal) > 0.01) {
            showAlert('Facility allocation must equal the Rebate Amount before saving. Please fully allocate the remaining amount.', 'warning');
            return;
        }
    }

    showLoading();

    fetch(editInitiativeId ? `/api/rebates/${editInitiativeId}` : '/api/rebates', {
        method: editInitiativeId ? 'PUT' : 'POST',
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
    .then(response => response.json())
    .then(data => {
        showAlert('Initiative and files uploaded successfully!', 'success');
        setTimeout(() => {
            window.location.href = '/dashboard';
        }, 2000);
    })
    .catch(error => {
        console.error('Error uploading files:', error);
        showAlert('Initiative created but file upload failed', 'warning');
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
    if (window.showGlobalPopup && (type === 'danger' || type === 'error')) {
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
        const rb = data.rebate || {};
        setField('description', data.description);
        setSelect('rebateType', rb.rebate_type);
        setField('waveInitiativeId', rb.wave_initiative_id);
        setSelect('contractCategory', rb.contract_category);
        setField('contractId', rb.contract_number);
        await loadPrimeVendorOptions(rb.contract_number, 'vendorNameOptions');
        setRadio('contract_source', rb.contract_source);
        setField('vendorName', rb.vendor_name);
        setField('transactionDate', rb.transaction_date);
        setRadio('transaction_type', rb.transaction_type);
        setField('transactionNumber', rb.transaction_number);
        setField('rebateAmount', rb.rebate_amount);
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
