// Shared parameter generator for the search_products scenarios, so MySQL and MongoDB receive the same requests.
// Pools come from the loaded dataset (bigdata-final): category sizes are active SKUs per category.
export const PAGE_SIZE = 20;

export const CATEGORIES = [
  ["Garment Upper body", 7818], ["Garment Lower body", 3636], ["Garment Full body", 1805], ["Underwear", 1647],
  ["Accessories", 1090], ["Swimwear", 1010], ["Socks & Tights", 611], ["Shoes", 452], ["Nightwear", 266],
];
export const COLORS = ["Black", "Dark Blue", "White", "Light Pink", "Grey", "Light Beige", "Blue", "Beige", "Light Blue", "Red"];
export const KEYWORDS = ["top", "dress", "shorts", "skinny", "jacket", "tee"];
export const PRICE_BANDS = [[0, 10], [10, 25], [25, 50], [50, 500]]; // inclusive on both ends

// Small deterministic generator (LCG): same seed, same sequence, in both databases and across runs.
function rng(seed) {
  let s = (seed >>> 0) || 1;
  const next = () => { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296; };
  next();
  return next;
}

function weightedCategory(r) {
  const total = CATEGORIES.reduce((a, c) => a + c[1], 0);
  let x = r() * total;
  for (const [name, w] of CATEGORIES) { x -= w; if (x < 0) return name; }
  return CATEGORIES[0][0];
}

// One search request: a category is always chosen; colour, price band and name keyword are optional filters.
// Pages are skewed to the first ones, like real browsing.
export function searchParams(vu, iter) {
  const r = rng(vu * 1000003 + iter * 7919 + 12345);
  const category = weightedCategory(r);
  const color = r() < 0.5 ? COLORS[Math.floor(r() * COLORS.length)] : null;
  const price = r() < 0.6 ? PRICE_BANDS[Math.floor(r() * PRICE_BANDS.length)] : null;
  const keyword = r() < 0.3 ? KEYWORDS[Math.floor(r() * KEYWORDS.length)] : null;
  const page = Math.floor(r() * r() * 8);
  return { category, color, price, keyword, page };
}

// xk6-sql returns text columns as byte arrays; decode them as UTF-8 so they compare equal to MongoDB strings.
export function text(v) {
  return typeof v === "string" ? v : new TextDecoder().decode(new Uint8Array(v));
}

// Same prices as strings with 2 decimals in both databases.
export function money(v) {
  const s = String(v);
  if (!s.includes(".")) return s + ".00";
  const f = s.split(".")[1].length;
  return f >= 2 ? s : s + "0".repeat(2 - f);
}

export const VERIFY_CASES = 60; // number of fixed requests compared across databases in VERIFY mode

// Load shape from the environment: constant VUs for a fixed time (one run per concurrency level).
export function loadOptions(name) {
  if (__ENV.VERIFY) return { vus: 1, iterations: 1 };
  return {
    scenarios: {
      [name]: { executor: "constant-vus", vus: Number(__ENV.VUS || 16), duration: __ENV.DURATION || "30s", gracefulStop: "10s" },
    },
    summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
  };
}
