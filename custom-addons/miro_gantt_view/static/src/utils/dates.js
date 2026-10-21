/** @odoo-module **/

/**
 * Returns whether a raw date string carries a time component (space or "T"
 * separator), which determines if it should be treated as a datetime.
 * @param {*} val - The raw date value
 * @returns {boolean} True when the value is a string with a time component
 */
export function hasTime(val) {
    return typeof val === 'string' && (
        val.includes(' ') || val.includes('T')
    );
}

/**
 * Parses a raw date value from the backend into a Date. Datetime strings are
 * interpreted as UTC (so local getters reflect the user's timezone); date-only
 * values are normalized to local midnight. Invalid/empty values yield the epoch.
 * @param {string|Date} val - The raw date value
 * @returns {Date} The parsed Date
 */
export function parseDate(val) {
    if (!val) return new Date(0);

    const parts = val.split(/[- :T]/).map(Number);

    if (hasTime(val)) {
        const d = new Date(
            Date.UTC(
                parts[0],
                parts[1] - 1,
                parts[2] || 0,
                parts[3] || 0,
                parts[4] || 0,
                parts[5] || 0
            )
        );

        return isNaN(d.getTime()) ? new Date(0) : d;
    }

    const d = new Date(val);

    if (isNaN(d.getTime())) return new Date(0);

    d.setHours(0, 0, 0, 0);

    return d;
}