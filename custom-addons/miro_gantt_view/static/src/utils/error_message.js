/** @odoo-module **/

/**
 * Extracts a user-friendly, meaningful message from an error.
 *
 * A standard Odoo RPC error looks like:
 *   { message: "Odoo Server Error",                  // generic, not useful
 *     data:   { name, message, arguments, debug, ... } }
 *
 * The real message (UserError / ValidationError / AccessError text) lives in
 * `error.data.message` or `error.data.arguments[0]`. We never surface the
 * generic "Odoo Server Error" string.
 *
 * @param {Object|Error|null} error - The raised error
 * @param {string} [fallback] - Message returned when nothing usable is found
 * @returns {string} A readable error message
 */
export function extractErrorMessage(error, fallback = "An error has occurred.") {
  if (!error) return fallback;
  const data = error.data || {};
  if (typeof data.message === "string" && data.message.trim()) {
    return data.message.trim();
  }
  if (Array.isArray(data.arguments) && data.arguments.length) {
    const first = data.arguments[0];
    if (first != null && String(first).trim()) {
      return String(first).trim();
    }
  }
  if (data.name && String(data.name).trim()) {
    return String(data.name).trim();
  }
  const raw = error.message;
  if (
    typeof raw === "string" &&
    raw.trim() &&
    raw.trim() !== "Odoo Server Error"
  ) {
    return raw.trim();
  }
  return fallback;
}

