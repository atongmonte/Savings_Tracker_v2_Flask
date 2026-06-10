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

const AUTOCOMPLETE_MAX_ITEMS = 8;

function createCustomAutocomplete(input) {
    input.removeAttribute('list');
    input.setAttribute('autocomplete', 'off');

    let allOptions = [];
    let activeIndex = -1;

    const dropdown = document.createElement('ul');
    dropdown.className = 'prime-autocomplete-dropdown';
    Object.assign(dropdown.style, {
        position: 'fixed',
        background: '#fff',
        border: '1px solid #ced4da',
        borderTop: 'none',
        borderRadius: '0 0 4px 4px',
        zIndex: '9999',
        margin: '0',
        padding: '0',
        listStyle: 'none',
        display: 'none',
        boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
        overflowY: 'auto',
    });
    document.body.appendChild(dropdown);

    function positionDropdown() {
        const rect = input.getBoundingClientRect();
        dropdown.style.top = rect.bottom + 'px';
        dropdown.style.left = rect.left + 'px';
        dropdown.style.width = rect.width + 'px';
    }

    function setActive(index) {
        const items = dropdown.querySelectorAll('li');
        items.forEach(li => {
            li.style.background = '';
            li.style.color = '';
        });
        activeIndex = index;
        if (index >= 0 && index < items.length) {
            items[index].style.background = '#0072BC';
            items[index].style.color = '#fff';
            items[index].scrollIntoView({ block: 'nearest' });
        }
    }

    function hideDropdown() {
        dropdown.style.display = 'none';
        activeIndex = -1;
    }

    function showDropdown(items) {
        if (!items.length) {
            hideDropdown();
            return;
        }
        dropdown.innerHTML = '';
        activeIndex = -1;
        const limited = items.slice(0, AUTOCOMPLETE_MAX_ITEMS);
        limited.forEach((value, i) => {
            const li = document.createElement('li');
            li.textContent = value;
            Object.assign(li.style, {
                padding: '0.45rem 0.75rem',
                cursor: 'pointer',
                fontSize: '0.875rem',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                borderBottom: i < limited.length - 1 ? '1px solid #f0f0f0' : 'none',
            });
            li.addEventListener('mousedown', e => {
                e.preventDefault();
                input.value = value;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                hideDropdown();
            });
            li.addEventListener('mouseenter', () => setActive(i));
            li.addEventListener('mouseleave', () => {
                li.style.background = '';
                li.style.color = '';
            });
            dropdown.appendChild(li);
        });
        positionDropdown();
        dropdown.style.display = 'block';
    }

    function filterAndShow() {
        const query = (input.value || '').trim().toLowerCase();
        const filtered = query
            ? allOptions.filter(v => v.toLowerCase().includes(query))
            : allOptions;
        showDropdown(filtered);
    }

    input.addEventListener('input', filterAndShow);
    input.addEventListener('focus', filterAndShow);
    input.addEventListener('blur', () => setTimeout(hideDropdown, 150));
    input.addEventListener('keydown', e => {
        if (dropdown.style.display === 'none') return;
        const items = dropdown.querySelectorAll('li');
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            setActive(Math.min(activeIndex + 1, items.length - 1));
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setActive(Math.max(activeIndex - 1, 0));
        } else if (e.key === 'Enter' && activeIndex >= 0) {
            e.preventDefault();
            items[activeIndex].dispatchEvent(new MouseEvent('mousedown'));
        } else if (e.key === 'Escape') {
            hideDropdown();
        }
    });

    const onScrollOrResize = () => {
        if (dropdown.style.display !== 'none') positionDropdown();
    };
    window.addEventListener('scroll', onScrollOrResize, true);
    window.addEventListener('resize', onScrollOrResize);

    return {
        setOptions(options) {
            allOptions = options || [];
            if (document.activeElement === input) filterAndShow();
        },
        destroy() {
            dropdown.remove();
            window.removeEventListener('scroll', onScrollOrResize, true);
            window.removeEventListener('resize', onScrollOrResize);
        },
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

    // Use custom autocomplete dropdowns instead of native datalist
    const contractAC = createCustomAutocomplete(contractInput);
    const vendorAC = createCustomAutocomplete(vendorInput);

    // Load all contract IDs and seed the contract autocomplete
    let allContractNumbers = [];
    try {
        const payload = await fetchPrimeContractLookup('', options.forceRefresh === true);
        allContractNumbers = payload.contractNumbers || [];
    } catch (e) {
        console.error('Error loading PRIME contract IDs:', e);
    }
    contractAC.setOptions(allContractNumbers);

    contractInput.dataset.lastPrimeContractValue = (contractInput.value || '').trim();

    const refreshVendors = async ({ clearVendorOnChange = false } = {}) => {
        const currentContractNumber = contractInput.value || contractInput.dataset.pendingValue || '';
        const normalizedCurrentContractNumber = currentContractNumber.trim();
        const lastContractNumber = (contractInput.dataset.lastPrimeContractValue || '').trim();

        if (clearVendorOnChange && normalizedCurrentContractNumber !== lastContractNumber) {
            vendorInput.value = '';
            vendorAC.setOptions([]);
        }

        contractInput.dataset.lastPrimeContractValue = normalizedCurrentContractNumber;

        if (!normalizedCurrentContractNumber) {
            vendorAC.setOptions([]);
            return;
        }
        try {
            const payload = await fetchPrimeContractLookup(normalizedCurrentContractNumber);
            vendorAC.setOptions(payload.vendors || []);
        } catch (e) {
            console.error('Error loading PRIME vendors:', e);
            vendorAC.setOptions([]);
        }
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