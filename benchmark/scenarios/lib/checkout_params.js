// Shared parameters for the checkout scenarios, so MySQL and MongoDB receive the same requests.
// A checkout re-places the lines of a template order (benchmark/checkout_templates.py) as a new pending order.
import { loadOptions, text } from "./search_params.js";
export { loadOptions, text };

export const TPL = JSON.parse(open(__ENV.TEMPLATES || "/scripts/lib/checkout_templates.json"));
export const HOT_SHARE = Number(__ENV.HOT_SHARE || 0.5); // share of checkouts that use a "hot" template (contended SKUs)
export const MAX_ATTEMPTS = 3;                            // tries per checkout when a deadlock / write conflict happens
export const VERIFY_CHECKOUTS = 40;                       // fixed requests run by VERIFY=1
export const ALL_TEMPLATE_IDS = [...new Set([...TPL.hot, ...TPL.cold])];

// Payment method mix of the loaded data (payment rows per method).
const METHODS = [["credit_card", 744565], ["bank_transfer", 188130], ["cod", 50461], ["e_wallet", 55205]];

function rng(seed) {
  let s = (seed >>> 0) || 1;
  const next = () => { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296; };
  next();
  return next;
}

export function checkoutParams(vu, iter) {
  const r = rng(vu * 1000003 + iter * 7919 + 424242);
  const pool = r() < HOT_SHARE ? TPL.hot : TPL.cold;
  const templateId = pool[Math.floor(r() * pool.length)];
  const customerId = TPL.customers[Math.floor(r() * TPL.customers.length)];
  let x = r() * METHODS.reduce((a, m) => a + m[1], 0), method = METHODS[0][0];
  for (const [name, w] of METHODS) { x -= w; if (x < 0) { method = name; break; } }
  return { templateId, customerId, method, jitter: r() };
}

// MongoDB ids share the numbering of the MySQL ids (the numeric id is the last 3 bytes).
export const orderHex = (id) => "f001" + "0".repeat(14) + id.toString(16).padStart(6, "0");
export const customerHex = (id) => "e001" + "0".repeat(14) + id.toString(16).padStart(6, "0");
export const idFromBytes = (b) => b[9] * 65536 + b[10] * 256 + b[11];

// Sort key for lock ordering: (sku_id, warehouse_id).
export const byRow = (a, b) => (a.sku - b.sku) || (a.wh - b.wh);
