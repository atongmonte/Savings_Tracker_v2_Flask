// Cost Savings Form JavaScript

let editInitiativeId = null;
let existingFileCount = 0;
let stagedNewFiles = [];

function shiftIsoDate(isoDate, days) {
    if (!isoDate) return '';
    const parts = isoDate.split('-').map(Number);
    if (parts.length !== 3 || parts.some(Number.isNaN)) return '';
    const shifted = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2] + days));
    const y = shifted.getUTCFullYear();
    const m = String(shifted.getUTCMonth() + 1).padStart(2, '0');
    const d = String(shifted.getUTCDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

function applyCostSavingsDateBounds(changedFieldId = null) {
    const startDateInput = document.getElementById('startDate');
    const endDateInput = document.getElementById('endDate');
    if (!startDateInput || !endDateInput) return;

    const startValue = startDateInput.value;
    const endValue = endDateInput.value;

    startDateInput.removeAttribute('max');
    endDateInput.removeAttribute('min');

    if (endValue) {
        startDateInput.max = shiftIsoDate(endValue, -1);
    }
    if (startValue) {
        endDateInput.min = shiftIsoDate(startValue, 1);
    }

    if (startValue && endValue && startValue >= endValue) {
        if (changedFieldId === 'startDate') {
            endDateInput.value = '';
        } else {
            startDateInput.value = '';
        }

        const nextStart = startDateInput.value;
        const nextEnd = endDateInput.value;
        startDateInput.removeAttribute('max');
        endDateInput.removeAttribute('min');
        if (nextEnd) startDateInput.max = shiftIsoDate(nextEnd, -1);
        if (nextStart) endDateInput.min = shiftIsoDate(nextStart, 1);
    }
}

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
    setupTemplateSection();
    checkEditMode();
});

function initializeForm() {
    // Calculate savings amount when baseline or new contract spend changes
    const baselineSpend = document.getElementById('baselineSpend');
    const newContractSpend = document.getElementById('newContractSpend');
    const savingsAmount = document.getElementById('savingsAmount');
    const totalSavingsAmount = document.getElementById('totalSavingsAmount');
    const startDateInput = document.getElementById('startDate');
    const endDateInput = document.getElementById('endDate');
    const totalSavingsHint = document.getElementById('totalSavingsHint');
    
    function getDurationYears() {
        if (!startDateInput.value || !endDateInput.value) return null;
        const start = new Date(startDateInput.value);
        const end = new Date(endDateInput.value);
        if (end <= start) return null;
        return (end - start) / (365.25 * 24 * 60 * 60 * 1000);
    }
    
    function calculateSavings() {
        const baseline = numVal(baselineSpend.value);
        const newSpend = numVal(newContractSpend.value);
        const savings = baseline - newSpend;
        savingsAmount.value = fmtNum(savings);
        calculateTotal();
    }
    
    function calculateTotal() {
        const annualSavings = numVal(savingsAmount.value);
        const durationYears = getDurationYears();
        if (durationYears !== null && annualSavings !== 0) {
            const total = Math.round(annualSavings * durationYears);
            totalSavingsAmount.value = fmtNum(total);
            totalSavingsAmount.dispatchEvent(new Event('input'));
            if (totalSavingsHint) {
                totalSavingsHint.textContent = `Calculated: $${annualSavings.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})} × ${durationYears.toFixed(2)} yrs = $${total.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
            }
        } else {
            totalSavingsAmount.value = '';
            totalSavingsAmount.dispatchEvent(new Event('input'));
            if (totalSavingsHint) {
                totalSavingsHint.textContent = 'Calculated: Annual Expected Savings × Duration (years)';
            }
        }
    }
    
    baselineSpend.addEventListener('input', calculateSavings);
    newContractSpend.addEventListener('input', calculateSavings);
    if (startDateInput) {
        startDateInput.addEventListener('change', function() {
            applyCostSavingsDateBounds('startDate');
            calculateTotal();
        });
    }
    if (endDateInput) {
        endDateInput.addEventListener('change', function() {
            applyCostSavingsDateBounds('endDate');
            calculateTotal();
        });
    }
    applyCostSavingsDateBounds();
    
    // File upload handling
    setupFileUpload();
    
    // Facility allocation
    setupFacilityAllocation();
}

function setupEventListeners() {
    const form = document.getElementById('costSavingsForm');
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

function setupTemplateSection() {
    const templateMappings = {
        'Standardization/Conversion': {
            title: 'Standardization/Conversion Template',
            filename: 'standardization_conversion_template.xlsx',
            url: '/static/templates/standardization_conversion_template.xlsx'
        },
        'Negotiated Price Reduction': {
            title: 'Negotiated Price Reduction Template',
            filename: 'negotiated_price_reduction_template.xlsx',
            url: '/static/templates/negotiated_price_reduction_template.xlsx'
        },
        'Demand/Utilization Reduction': {
            title: 'Demand/Utilization Reduction Template',
            filename: 'demand_utilization_reduction_template.xlsx',
            url: '/static/templates/demand_utilization_reduction_template.xlsx'
        },
        'One-time Saving (non-rebate)': {
            title: 'One-time Saving Template',
            filename: 'one_time_saving_template.xlsx',
            url: '/static/templates/one_time_saving_template.xlsx'
        }
    };

    const radios = document.querySelectorAll('.cost-savings-type-radio');
    const templateSection = document.getElementById('templateSection');
    const templateTitle = document.getElementById('templateTitle');
    const templateName = document.getElementById('templateName');
    const templateDownloadLink = document.getElementById('templateDownloadLink');
    const initiativeDetails = document.getElementById('initiativeDetailsSection');
    
    radios.forEach(radio => {
        radio.addEventListener('change', function() {
            if (this.checked) {
                const type = this.value;
                const template = templateMappings[type];
                
                if (template) {
                    templateTitle.textContent = template.title;
                    templateName.textContent = type;
                    templateDownloadLink.href = template.url;
                    templateDownloadLink.download = template.filename;
                    templateSection.classList.remove('d-none');
                } else {
                    templateSection.classList.add('d-none');
                }
                
                // Hide Initiative Details section for Demand/Utilization Reduction
                if (type === 'Demand/Utilization Reduction') {
                    initiativeDetails.classList.add('d-none');
                    // Make fields optional
                    toggleInitiativeDetailsRequired(false);
                } else {
                    initiativeDetails.classList.remove('d-none');
                    // Make fields required
                    toggleInitiativeDetailsRequired(true);
                }

                // Hide Facility Allocation section for Demand/Utilization Reduction
                const facilityAllocSection = document.getElementById('facilityAllocationSection');
                if (facilityAllocSection) {
                    if (type === 'Demand/Utilization Reduction') {
                        facilityAllocSection.classList.add('d-none');
                    } else {
                        facilityAllocSection.classList.remove('d-none');
                    }
                }
            }
        });
    });
}

function toggleInitiativeDetailsRequired(isRequired) {
    const fields = [
        'baselineSpend',
        'newContractSpend',
        'savingsAmount',
        'totalSavingsAmount'
    ];
    
    fields.forEach(fieldId => {
        const field = document.getElementById(fieldId);
        if (field) {
            if (isRequired) {
                field.setAttribute('required', 'required');
            } else {
                field.removeAttribute('required');
            }
        }
    });
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
    const totalSavingsInput = document.getElementById('totalSavingsAmount');
    
    // Debug: Check if elements exist
    console.log('Allocation symbols found:', document.querySelectorAll('.allocation-symbol').length);
    
    // Current allocation type (locked to dollar amount)
    let currentAllocationType = 'amount';
    
    function updateAllocationMethod() {
        currentAllocationType = document.querySelector('input[name="allocationType"]:checked').value;
        const isPercentage = currentAllocationType === 'percentage';
        
        console.log('Switching to:', currentAllocationType);
        
        // Update UI based on allocation type
        if (isPercentage) {
            // Percentage mode
            allocationInstruction.textContent = 'Allocate savings percentage across facilities (must total 100%)';
            totalAllocationLabel.innerHTML = 'Total Allocation: <span id="totalAllocation">0</span>%';
            
            // Update input group symbols to %
            document.querySelectorAll('.allocation-symbol').forEach((span, index) => {
                span.textContent = '%';
                console.log(`Symbol ${index} set to %`);
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
            
            // Get total from total expected savings
            const totalAmount = numVal(totalSavingsInput.value);
            
            // Update input group symbols to $
            document.querySelectorAll('.allocation-symbol').forEach((span, index) => {
                span.textContent = '$';
                console.log(`Symbol ${index} set to $`);
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
        const totalAmount = numVal(totalSavingsInput.value);
        
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
    
    // Re-run allocation validation when total expected savings changes
    if (totalSavingsInput) {
        totalSavingsInput.addEventListener('input', function() {
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
    const form = document.getElementById('costSavingsForm');
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
    
    // Validate dates
    const startDateEl = document.getElementById('startDate');
    const endDateEl = document.getElementById('endDate');
    if (startDateEl && endDateEl && startDateEl.value && endDateEl.value) {
        const startDate = new Date(startDateEl.value);
        const endDate = new Date(endDateEl.value);
        if (endDate <= startDate) {
            showAlert('Cost savings end date must be after start date', 'warning');
            isValid = false;
        }
    }

    const totalSavingsVal = numVal(document.getElementById('totalSavingsAmount')?.value || '0');
    if (totalSavingsVal <= 0) {
        showAlert('Total Expected Savings must be greater than 0 before submitting.', 'warning');
        isValid = false;
    }

    // Validate facility allocation is fully allocated (submit only, not draft)
    // Skip for Demand/Utilization Reduction — no allocation required for that type
    const selectedSavingsType = document.querySelector('input[name="cost_savings_type"]:checked')?.value || '';
    if (selectedSavingsType !== 'Demand/Utilization Reduction') {
        const allocationType = document.querySelector('input[name="allocationType"]:checked')?.value || 'amount';
        let allocTotal = 0;
        document.querySelectorAll('.facility-allocation').forEach(inp => { allocTotal += numVal(inp.value); });
        allocTotal = Math.round(allocTotal * 100) / 100;
        const allocTolerance = 0.01;
        if (allocationType === 'percentage') {
            if (Math.abs(allocTotal - 100) > allocTolerance) {
                showAlert('Facility allocations must total 100% before submitting.', 'warning');
                isValid = false;
            }
        } else {
            const mainAmt = numVal(document.getElementById('totalSavingsAmount')?.value || '0');
            if (mainAmt > 0 && Math.abs(mainAmt - allocTotal) > allocTolerance) {
                showAlert('Facility allocation must equal the Total Savings amount before submitting. Please fully allocate the remaining amount.', 'warning');
                isValid = false;
            }
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
        initiative_type: 'Cost Savings',
        wave_id: formData.get('wave_id'),
        contract_category: formData.get('contract_category'),
        contract_number: formData.get('contract_id'),
        contract_source: formData.get('contract_source'),
        vendor_name: formData.get('vendor_name'),
        description: formData.get('description'),
        savings_type: formData.get('cost_savings_type'),
        gpo_tier: formData.get('gpo_tier'),
        start_date: formData.get('start_date'),
        end_date: formData.get('end_date'),
        baseline_spend: numVal(formData.get('baseline_spend')),
        expected_spend: numVal(formData.get('expected_spend')),
        annual_savings_amount: numVal(formData.get('annual_savings_amount')),
        total_savings_amount: numVal(formData.get('total_savings_amount')),
        facility_allocations: facilities,
        status: 'Submitted'
    };
    
    showLoading();
    
    fetch(editInitiativeId ? `/api/cost-savings/${editInitiativeId}` : '/api/cost-savings', {
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
                showAlert('Cost Savings initiative created successfully!', 'success');
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
    const form = document.getElementById('costSavingsForm');
    const formData = new FormData(form);
    
    // Similar to handleSubmit but with status = 'Draft'
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
        initiative_type: 'Cost Savings',
        wave_id: formData.get('wave_id'),
        contract_category: formData.get('contract_category'),
        contract_number: formData.get('contract_id'),
        contract_source: formData.get('contract_source'),
        vendor_name: formData.get('vendor_name'),
        description: formData.get('description'),
        savings_type: formData.get('cost_savings_type'),
        gpo_tier: formData.get('gpo_tier'),
        start_date: formData.get('start_date'),
        end_date: formData.get('end_date'),
        baseline_spend: numVal(formData.get('baseline_spend')),
        expected_spend: numVal(formData.get('expected_spend')),
        annual_savings_amount: numVal(formData.get('annual_savings_amount')),
        total_savings_amount: numVal(formData.get('total_savings_amount')),
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
        const mainAmt = numVal(document.getElementById('totalSavingsAmount')?.value || '0');
        if (mainAmt > 0 && draftAllocTotal > 0 && Math.abs(mainAmt - draftAllocTotal) > 0.01) {
            showAlert('Facility allocation must equal the Total Savings amount before saving. Please fully allocate the remaining amount.', 'warning');
            return;
        }
    }

    showLoading();
    
    fetch(editInitiativeId ? `/api/cost-savings/${editInitiativeId}` : '/api/cost-savings', {
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
        const cs = data.cost_savings || {};
        setField('waveId', data.wave_id);
        setField('description', data.description);
        setRadio('cost_savings_type', cs.savings_type);
        setSelect('contractCategory', cs.contract_category);
        setField('contractId', cs.contract_number);
        await loadPrimeVendorOptions(cs.contract_number, 'vendorNameOptions');
        setRadio('contract_source', cs.contract_source);
        setField('gpoTier', cs.gpo_tier);
        setField('vendorName', cs.vendor_name);
        setField('startDate', cs.start_date);
        setField('endDate', cs.end_date);
        applyCostSavingsDateBounds();
        setField('baselineSpend', cs.baseline_spend);
        setField('newContractSpend', cs.expected_spend);
        setField('savingsAmount', cs.annual_savings_amount);
        setField('totalSavingsAmount', cs.total_savings_amount);
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
        document.getElementById('baselineSpend').dispatchEvent(new Event('input'));
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
