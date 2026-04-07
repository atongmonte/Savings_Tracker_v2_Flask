// Shared number formatting utility for all initiative forms

// Strip commas and return float; safe to call on any value
window.numVal = function(v) {
    return parseFloat(String(v || '').replace(/,/g, '')) || 0;
};

// Format a number with thousand separators (no trailing zeros removed)
window.fmtNum = function(n) {
    if (n === null || n === undefined || n === '' || isNaN(n)) return '';
    const parts = Number(n).toFixed(2).split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return parts.join('.');
};

(function () {
    function applyFormatter(input) {
        const isReadonly = input.hasAttribute('readonly');
        // Switch from number to text so we can show formatted value
        input.setAttribute('inputmode', 'decimal');
        input.type = 'text';

        function format(val) {
            // Strip anything that's not a digit, minus sign, or decimal
            let raw = String(val).replace(/[^0-9.\-]/g, '');
            const isNeg = raw.startsWith('-');
            raw = raw.replace(/-/g, '');
            // Only allow one decimal point
            const parts = raw.split('.');
            let integer = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
            let result = parts.length > 1 ? integer + '.' + parts[1] : integer;
            return isNeg && result ? '-' + result : result;
        }

        // Format initial value if any
        if (input.value !== '' && input.value !== '0') {
            const num = parseFloat(input.value);
            if (!isNaN(num)) input.value = fmtNum(num);
        }

        if (!isReadonly) {
            input.addEventListener('input', function () {
                const start = this.selectionStart;
                const prevLen = this.value.length;
                const formatted = format(this.value);
                this.value = formatted;
                // Adjust cursor position after comma insertion/removal
                const diff = formatted.length - prevLen;
                try { this.setSelectionRange(start + diff, start + diff); } catch (e) {}
            });

            // On blur: ensure full 2-decimal formatting
            input.addEventListener('blur', function () {
                const num = numVal(this.value);
                if (num !== 0 || this.value.trim() !== '') {
                    this.value = fmtNum(num);
                }
            });

            // On focus: keep formatted (user can edit freely; input handler normalises)
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('input[type="number"]').forEach(applyFormatter);
    });
})();
