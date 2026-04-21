let contractCategoryRequest = null;
let primeContractLookupRequest = null;

function getContractCategoryEndpoint() {
    return '/api/initiatives/contract-categories';
}

function getPrimeContractLookupEndpoint(contractNumber = '') {
    const url = new URL('/api/initiatives/prime-contract-lookup', window.location.origin);
    if (contractNumber && contractNumber.trim()) {
        url.searchParams.set('contract_number', contractNumber.trim());
    }
    return url.toString();
}

function setContractCategoryLoadingState(select, message) {
    if (!select) return;
    select.innerHTML = '';
    const option = document.createElement('option');
    option.value = '';
    option.text = message;
    select.appendChild(option);
    select.value = '';
    select.disabled = true;
}

async function fetchContractCategories(forceRefresh = false) {
    if (!forceRefresh && contractCategoryRequest) {
        return contractCategoryRequest;
    }

    contractCategoryRequest = fetch(getContractCategoryEndpoint(), {
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' },
    })
        .then(async response => {
            if (!response.ok) {
                throw new Error(`Failed to load contract categories (${response.status})`);
            }
            const payload = await response.json();
            return Array.isArray(payload.contract_categories) ? payload.contract_categories : [];
        })
        .catch(error => {
            contractCategoryRequest = null;
            throw error;
        });

    return contractCategoryRequest;
}

async function loadContractCategorySelect(selectOrId, options = {}) {
    const select = typeof selectOrId === 'string'
        ? document.getElementById(selectOrId)
        : selectOrId;

    if (!select) return [];

    const {
        placeholder = 'Please Select',
        loadingText = 'Loading contract categories...',
        errorText = 'Unable to load contract categories',
        includePlaceholder = true,
    } = options;

    setContractCategoryLoadingState(select, loadingText);

    try {
        const categories = await fetchContractCategories(options.forceRefresh === true);
        const previousValue = select.dataset.pendingValue || select.value || '';

        select.innerHTML = '';
        if (includePlaceholder) {
            const placeholderOption = document.createElement('option');
            placeholderOption.value = '';
            placeholderOption.text = placeholder;
            select.appendChild(placeholderOption);
        }

        categories.forEach(category => {
            const option = document.createElement('option');
            option.value = category;
            option.text = category;
            select.appendChild(option);
        });

        select.disabled = false;
        if (previousValue) {
            const match = Array.from(select.options || []).find(option => option.value === previousValue);
            if (match) {
                select.value = previousValue;
            }
        }
        return categories;
    } catch (error) {
        console.error('Error loading contract categories:', error);
        setContractCategoryLoadingState(select, errorText);
        return [];
    }
}

async function fetchPrimeContractLookup(contractNumber = '', forceRefresh = false) {
    const normalizedContractNumber = (contractNumber || '').trim();
    if (!normalizedContractNumber && !forceRefresh && primeContractLookupRequest) {
        return primeContractLookupRequest;
    }

    const requestPromise = fetch(getPrimeContractLookupEndpoint(normalizedContractNumber), {
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' },
    })
        .then(async response => {
            if (!response.ok) {
                throw new Error(`Failed to load PRIME contract lookup (${response.status})`);
            }
            const payload = await response.json();
            return {
                contractNumbers: Array.isArray(payload.contract_numbers) ? payload.contract_numbers : [],
                vendors: Array.isArray(payload.vendors) ? payload.vendors : [],
            };
        });

    if (!normalizedContractNumber) {
        primeContractLookupRequest = requestPromise.catch(error => {
            primeContractLookupRequest = null;
            throw error;
        });
        return primeContractLookupRequest;
    }

    return requestPromise;
}

function populateDataList(datalistOrId, values) {
    const datalist = typeof datalistOrId === 'string'
        ? document.getElementById(datalistOrId)
        : datalistOrId;

    if (!datalist) return;

    datalist.innerHTML = '';
    (values || []).forEach(value => {
        const option = document.createElement('option');
        option.value = value;
        datalist.appendChild(option);
    });
}

async function loadPrimeContractIdOptions(datalistOrId, options = {}) {
    try {
        const payload = await fetchPrimeContractLookup('', options.forceRefresh === true);
        populateDataList(datalistOrId, payload.contractNumbers || []);
        return payload.contractNumbers || [];
    } catch (error) {
        console.error('Error loading PRIME contract IDs:', error);
        populateDataList(datalistOrId, []);
        return [];
    }
}

async function loadPrimeVendorOptions(contractNumber, datalistOrId) {
    const normalizedContractNumber = (contractNumber || '').trim();
    if (!normalizedContractNumber) {
        populateDataList(datalistOrId, []);
        return [];
    }

    try {
        const payload = await fetchPrimeContractLookup(normalizedContractNumber);
        populateDataList(datalistOrId, payload.vendors || []);
        return payload.vendors || [];
    } catch (error) {
        console.error('Error loading PRIME vendors:', error);
        populateDataList(datalistOrId, []);
        return [];
    }
}

function debounceAsync(callback, waitMs) {
    let timeoutId = null;
    return (...args) => {
        if (timeoutId) {
            clearTimeout(timeoutId);
        }
        timeoutId = setTimeout(() => callback(...args), waitMs);
    };
}

async function initializePrimeContractLookup(options) {
    const contractInput = typeof options.contractInputId === 'string'
        ? document.getElementById(options.contractInputId)
        : options.contractInputId;
    const vendorInput = typeof options.vendorInputId === 'string'
        ? document.getElementById(options.vendorInputId)
        : options.vendorInputId;

    if (!contractInput || !vendorInput) return;

    if (options.contractListId) {
        contractInput.setAttribute('list', options.contractListId);
    }
    if (options.vendorListId) {
        vendorInput.setAttribute('list', options.vendorListId);
    }

    await loadPrimeContractIdOptions(options.contractListId);

    contractInput.dataset.lastPrimeContractValue = (contractInput.value || '').trim();

    const refreshVendors = async ({ clearVendorOnChange = false } = {}) => {
        const currentContractNumber = contractInput.value || contractInput.dataset.pendingValue || '';
        const normalizedCurrentContractNumber = currentContractNumber.trim();
        const lastContractNumber = (contractInput.dataset.lastPrimeContractValue || '').trim();

        if (clearVendorOnChange && normalizedCurrentContractNumber !== lastContractNumber) {
            vendorInput.value = '';
        }

        contractInput.dataset.lastPrimeContractValue = normalizedCurrentContractNumber;
        return loadPrimeVendorOptions(currentContractNumber, options.vendorListId);
    };

    if (!contractInput.dataset.primeLookupBound) {
        const debouncedRefresh = debounceAsync(
            () => refreshVendors({ clearVendorOnChange: true }),
            250
        );
        contractInput.addEventListener('input', debouncedRefresh);
        contractInput.addEventListener('change', () => refreshVendors({ clearVendorOnChange: true }));
        contractInput.addEventListener('blur', () => refreshVendors({ clearVendorOnChange: true }));
        contractInput.dataset.primeLookupBound = 'true';
    }

    await refreshVendors();
}