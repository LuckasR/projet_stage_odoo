/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { escape } from "@web/core/utils/strings";
import { parseXML } from "@web/core/utils/xml";


/**
 * Renders a custom QWeb-like popup template from XML.
 * Supports a subset of QWeb directives: t-if, t-esc, t-foreach, t-as.
 * Context values are injected as local variables for expression evaluation.
 *
 * @param {string} xml - The XML template string
 * @param {Object} context - Data context with field values
 * @returns {string} Rendered HTML string
 */
export function renderCustomTemplate(xml, context) {
  try {
    const root = parseXML(xml);
    if (!root) return "";
    return renderNode(root, context);
  } catch (error) {
    console.error("Failed to render custom popup template:", error);
    return `<div class="text-danger">${_t("Failed to render popup template")}</div>`;
  }
}

/**
 * Renders the default popup body showing key field values.
 * Iterates over the label fields (sidebar then taskbar), dateStart, dateEnd
 * and displays each as "label: value" in a simple div layout.
 * Dates are formatted with toFormat("dd/MM/yyyy") if available.
 *
 * @param {Object} context - Data context with field values
 * @param {Object} metaData - Model metadata containing field names
 * @returns {string} Rendered HTML string with field labels and values
 */
export function renderDefaultBody(context, metaData) {
  try {
    const { dateStart, dateEnd, sidebarLabelField, taskbarLabelField } = metaData;
    let body = "";
    const fields = [];
    if (sidebarLabelField) fields.push(sidebarLabelField);
    else if (taskbarLabelField) fields.push(taskbarLabelField);
    if (dateStart) fields.push(dateStart);
    if (dateEnd) fields.push(dateEnd);
    for (const key of fields) {
      const val = context[key];
      if (val == null) continue;
      // Format dates using the toFormat wrapper, or convert objects/values to string
      const display =
        typeof val.toFormat === "function"
          ? val.toFormat("dd/MM/yyyy")
          : typeof val === "object" && val !== null
            ? String(val[1] || val[0] || "")
            : String(val);
      const truncated =
        display.length > 300 ? display.substring(0, 300) + "...." : display;
      body += `<div class="mb-1">${escape(key)}: ${escape(truncated)}</div>`;
    }
    return body || `<div>${_t("No details")}</div>`;
  } catch (error) {
    console.error("Failed to render default popup body:", error);
    return `<div class="text-danger">${_t("Failed to load task details")}</div>`;
  }
}


/**
 * Evaluates a JavaScript expression string against a context object.
 * Provides helper functions: len(), str(), int(), float().
 * Uses a regex allowlist and blocks dangerous keywords for sandboxing.
 * Context values are injected as named parameters to a Function constructor.
 *
 * SECURITY NOTE: This uses new Function() which is inherently unsafe for
 * untrusted input. The allowlist + blocklist approach is a best-effort
 * defense for developer-authored templates only. If the XML template source
 * ever becomes user-editable (e.g. a configurable field in the database),
 * this MUST be replaced with a proper AST-based expression parser.
 *
 * @param {string} expr - The expression to evaluate (e.g. "record.name")
 * @param {Object} context - The data context for expression evaluation
 * @returns {*} The evaluated result, or empty string on error
 */
function evalExpr(expr, context) {
  // Helper functions available in template expressions
  const helpers = {
    len: (x) =>
      x ? (x.length !== undefined ? x.length : Object.keys(x).length) : 0,
    str: (x) => String(x ?? ""),
    int: (x) => parseInt(x, 10) || 0,
    float: (x) => parseFloat(x) || 0,
    min: (...args) => Math.min(...args),
    max: (...args) => Math.max(...args),
    round: (x) => Math.round(Number(x) || 0),
  };

  // Allowlist regex: safe JS expression characters (includes {} for object literals)
  // Blocks backticks, semicolons, backslashes, @, $, # — prevents template
  // literals, statement chaining, and regex/unicode escapes.
  const SAFE_RE = /^[\s\w[\]'"(){}.,+\-*/%&|!<>=?:]+$/;
  if (!SAFE_RE.test(expr)) {
    console.warn("Blocked unsafe expression syntax:", expr);
    return "";
  }

  // Block dangerous keywords/patterns that could bypass the sandbox.
  // Covers: prototype pollution, code constructors, global access, control
  // flow, module system, and common bypass techniques.
  const DANGEROUS =
    /constructor|__proto__|prototype|Function\b|eval\b|fetch\b|XMLHttpRequest|import\b|require\b|globalThis|global\b|window\b|document\b|self\b|this\b|new\b|throw\b|void\b|delete\b|typeof\b|instanceof\b|with\b|debugger\b|var\b|let\b|const\b|function\b|async\b|await\b|yield\b|return\b|Array\b|Object\b|String\b|Number\b|Boolean\b|Symbol\b|Proxy\b|Reflect\b|WeakMap\b|WeakSet\b|Map\b|Set\b|Date\b|RegExp\b|Error\b|Promise\b|atob\b|btoa\b|setTimeout\b|setInterval\b|requestAnimationFrame\b|importScripts\b/;
  if (DANGEROUS.test(expr)) {
    console.warn("Blocked dangerous expression:", expr);
    return "";
  }

  // Combine helpers and context (functions + values) for the Function constructor
  const allKeys = [...Object.keys(helpers), ...Object.keys(context)];
  const allValues = [...Object.values(helpers), ...Object.values(context)];
  try {
    return new Function(...allKeys, `return (${expr})`)(...allValues);
  } catch (error) {
    console.warn("Failed to evaluate popup expression:", expr, error);
    return "";
  }
}

/**
 * Recursively renders an XML DOM node into an HTML string.
 * Handles QWeb directives:
 *   - t-if: conditional rendering
 *   - t-foreach: iteration over arrays/objects
 *   - t-as: iteration variable name (used with t-foreach)
 *   - t-set / t-value: set a variable in the current context (mutates for siblings)
 *   - t-esc: escaped output of an expression
 *   - t-raw / t-out: unescaped HTML output of an expression
 * For regular elements and text nodes, delegates to renderElement().
 *
 * @param {Node} node - The XML DOM node to render
 * @param {Object} context - The data context for expression evaluation
 * @returns {string} Rendered HTML string
 */
function renderNode(node, context) {
  // Text nodes: return text content as-is
  if (node.nodeType === Node.TEXT_NODE) {
    return node.textContent;
  }
  // Non-element nodes: skip
  if (node.nodeType !== Node.ELEMENT_NODE) {
    return "";
  }

  const tag = node.tagName.toLowerCase();

  // Read QWeb directive attributes
  const tIf = node.getAttribute("t-if");
  const tEsc = node.getAttribute("t-esc");
  const tRaw = node.getAttribute("t-raw") ?? node.getAttribute("t-out");
  const tForeach = node.getAttribute("t-foreach");
  const tSet = node.getAttribute("t-set");
  const tValue = node.getAttribute("t-value");

  // t-if: conditionally render based on expression evaluation
  if (tIf !== null) {
    if (!evalExpr(tIf, context)) return "";
  }

  // t-set: set a variable in the current context (mutate so siblings can use it)
  if (tSet !== null) {
    const value = tValue !== null ? evalExpr(tValue, context) : "";
    context[tSet] = value;
    // Bare <t t-set="..." t-value="..."/> has no visual output
    if (
      tag === "t" &&
      tEsc === null &&
      tRaw === null &&
      tForeach === null &&
      node.childNodes.length === 0
    ) {
      return "";
    }
  }

  // t-foreach: iterate over a collection and render each item
  if (tForeach !== null) {
    const collection = evalExpr(tForeach, context);
    const as = node.getAttribute("t-as") || "item";
    if (collection == null) return "";
    let result = "";
    let index = 0;
    const arr = Array.isArray(collection)
      ? collection
      : Object.values(collection);
    for (const item of arr) {
      // Build context for each iteration with index, first, last variables
      const iterContext = {
        ...context,
        [as]: item,
        [`${as}_index`]: index,
        [`${as}_first`]: index === 0,
        [`${as}_last`]: index === arr.length - 1,
      };
      result += renderElement(node, iterContext);
      index++;
    }
    return result;
  }

  // t-raw / t-out: render unescaped HTML (needed for progress bars, etc.)
  // WARNING: This is an XSS sink — the output is NOT HTML-escaped.
  // A basic sanitizer strips script/event-handler vectors, but custom templates
  // should only use t-raw with trusted data (e.g. formatted numbers, not free text).
  if (tRaw !== null) {
    const val = evalExpr(tRaw, context);
    return val == null ? "" : sanitizeRawHtml(String(val));
  }

  // t-esc: render escaped expression value (truncated to 300 chars)
  if (tEsc !== null) {
    let val = String(evalExpr(tEsc, context) ?? "");
    if (val.length > 300) val = val.substring(0, 300) + "....";
    return escape(val);
  }

  // Default: render as regular element
  return renderElement(node, context);
}

/**
 * Renders a regular XML element to an HTML tag string.
 * Filters out t-* attributes (already processed by renderNode) and
 * recursively renders child nodes.
 * The special <t> tag renders children without a wrapper element.
 *
 * @param {Element} node - The XML element to render
 * @param {Object} context - The data context for expression evaluation
 * @returns {string} Rendered HTML string
 */
function renderElement(node, context) {
  const tag = node.tagName.toLowerCase();

  // <t> tag: transparent wrapper, renders children without a wrapping element
  if (tag === "t") {
    let result = "";
    for (const child of node.childNodes) {
      result += renderNode(child, context);
    }
    return result;
  }

  // Build the opening tag with attributes (excluding processed t-* attributes)
  let result = `<${tag}`;
  for (let i = 0; i < node.attributes.length; i++) {
    const attr = node.attributes[i];
    if (attr.name.startsWith("t-")) {
      // t-attf-*: interpolate #{expr} or {{expr}} in attribute value
      if (attr.name.startsWith("t-attf-")) {
        const attrName = attr.name.slice("t-attf-".length);
        const interpolated = attr.value.replace(
          /#\{([^}]+)\}|\{\{([^}]+)\}\}/g,
          (_, a, b) => {
            const val = evalExpr((a || b).trim(), context);
            return val == null ? "" : String(val);
          },
        );
        result += ` ${attrName}="${escape(interpolated)}"`;
      }
      // t-att-*: evaluate expression as attribute value
      else if (attr.name.startsWith("t-att-")) {
        const attrName = attr.name.slice("t-att-".length);
        const val = evalExpr(attr.value, context);
        if (val != null && val !== false) {
          result += ` ${attrName}="${escape(String(val))}"`;
        }
      }
      continue; // Skip other QWeb directives
    }
    result += ` ${attr.name}="${escape(attr.value)}"`;
  }
  result += ">";

  // Recursively render child nodes
  for (const child of node.childNodes) {
    result += renderNode(child, context);
  }

  // Closing tag
  result += `</${tag}>`;
  return result;
}

/**
 * Strips dangerous HTML elements and event handler attributes from a string.
 * Used as a safety net for t-raw/t-out output to reduce XSS surface.
 * This is NOT a full HTML sanitizer — it only blocks the most common vectors.
 *
 * @param {string} html - The raw HTML string to sanitize
 * @returns {string} Sanitized HTML string
 */
function sanitizeRawHtml(html) {
  if (!html || typeof html !== "string") return html;
  // Remove <script>, <iframe>, <object>, <embed>, <base>, <form> tags and their contents
  let safe = html.replace(
    /<(script|iframe|object|embed|base|form|meta|link)\b[^>]*>[\s\S]*?<\/\1\s*>/gi,
    ""
  );
  // Remove self-closing variants of those tags
  safe = safe.replace(
    /<(script|iframe|object|embed|base|form|meta|link)\b[^>]*\/?>/gi,
    ""
  );
  // Remove event handler attributes (onclick, onerror, onload, etc.)
  safe = safe.replace(/\bon\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, "");
  // Remove javascript: and vbscript: protocol URLs
  safe = safe.replace(
    /((?:href|src|action|formaction|data|codebase|dynsrc|lowsrc))\s*=\s*"\s*javascript\s*:/gi,
    '$1="blocked:'
  );
  safe = safe.replace(
    /((?:href|src|action|formaction|data|codebase|dynsrc|lowsrc))\s*=\s*'\s*javascript\s*:/gi,
    "$1='blocked:"
  );
  return safe;
}

