/**
 * One-time, opt-in synchronization of WordPress seo_h1 metadata into Astro's
 * persistent raw + processed product caches. No images or WooCommerce fields
 * are rebuilt or changed. Aborts before writing on ANY mismatch.
 *
 * Run only after the verified WordPress H1 import, before astro build.
 */
import { readFile, writeFile, rename } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const equals = (a, b) => String(a ?? "").normalize("NFC").trim() === String(b ?? "").normalize("NFC").trim();

export function applyVerifiedH1ToCaches(manifest, wpProducts, rawProducts, processedEnvelope) {
  if (manifest?.counts?.import_seo_h1 !== 160 || manifest.products?.length !== 160)
    throw Error("Unexpected verified H1 manifest");
  if (!Array.isArray(rawProducts) || rawProducts.length === 0 ||
      processedEnvelope?.version !== 1 || !Array.isArray(processedEnvelope.products))
    throw Error("Valid raw and processed product cache are both required");
  const fromWP = new Map(wpProducts.map(x => [Number(x.id), x]));
  const rawById = new Map(rawProducts.map(x => [Number(x.id), x]));
  const processedById = new Map(processedEnvelope.products.map(x => [String(x._id), x]));
  const expectedIds = new Set();
  const prepared = [];
  for (const item of manifest.products) {
    const id = Number(item.id);
    if (!Number.isSafeInteger(id) || expectedIds.has(id)) throw Error("Duplicate or invalid product ID");
    expectedIds.add(id);
    const wp = fromWP.get(id);
    const raw = rawById.get(id);
    if (!wp || !raw || wp.slug !== item.slug || raw.slug !== item.slug)
      throw Error("Product slug/ID differs: " + id);
    const groupKey = String(raw.acf?.origin_product_id || raw.id);
    const processed = processedById.get(groupKey);
    if (!processed || processed.slug?.vi !== item.slug)
      throw Error("Processed cache product group/slug differs: " + id);
    const currentWP = String(wp.seo_h1 ?? "").trim();
    if (!currentWP || !equals(currentWP, item.seo_h1))
      throw Error("REST seo_h1 differs from original verified H1 for ID " + id);
    // Prevalidate every product before mutating any cache object.
    prepared.push({ raw, processed, h1: currentWP });
  }
  const changed = prepared.filter(p => !equals(p.processed.itemSeoH1?.vi, p.h1)).length;
  for (const {raw, processed, h1} of prepared) {
    raw.seo_h1 = h1;
    processed.itemSeoH1 ??= {};
    processed.itemSeoH1.vi = h1;
  }
  return { validated: prepared.length, changed };
}

async function readJSON(filename) {
  return JSON.parse(await readFile(filename, "utf8"));
}

async function fetchPublishedProducts(wpOrigin) {
  const result = [];
  for (let page = 1; page <= 4; page++) {
    const u = new URL("/wp-json/wp/v2/product", wpOrigin);
    u.searchParams.set("per_page", "100");
    u.searchParams.set("page", String(page));
    u.searchParams.set("_fields", "id,slug,seo_h1");
    let resultPage;
    for (let attempt = 0; attempt < 3; attempt++) {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 20000);
      try {
        const r = await fetch(u, { signal: ctrl.signal, headers: {"User-Agent":"ESC-Verified-SEO-H1-Cache-Refresh/1.0"}});
        if (!r.ok) throw Error("WordPress product REST HTTP " + r.status);
        resultPage = await r.json();
        break;
      } catch (error) {
        if (attempt === 2) throw error;
        await new Promise(r => setTimeout(r, (attempt + 1) * 1000));
      } finally { clearTimeout(timer); }
    }
    if (!Array.isArray(resultPage)) throw Error("Expected WordPress REST product array");
    result.push(...resultPage);
    if (resultPage.length < 100) return result;
  }
  throw Error("WordPress product listing exceeds 400 items");
}

async function atomicJSON(path, data) {
  const temp = path + ".h1refresh-" + process.pid + ".tmp";
  await writeFile(temp, JSON.stringify(data), "utf8");
  await rename(temp, path);
}

async function main() {
  const host = process.env.WC_URL;
  if (!host) throw Error("Missing WC_URL secret");
  const wp = new URL(host.includes("://") ? host : "https://" + host).origin;
  const root = resolve(process.env.ASTRO_CACHE_DIR || "source/.cache");
  const manifest = await readJSON(resolve(process.env.H1_MANIFEST || "actions-hub/reports/product-h1-verified-candidates.json"));
  const rawPath = resolve(root, "products.json");
  const processedPath = resolve(root, "products-processed.json");
  const raw = await readJSON(rawPath);
  const processed = await readJSON(processedPath);
  const wpProducts = await fetchPublishedProducts(wp);
  const result = applyVerifiedH1ToCaches(manifest, wpProducts, raw, processed);
  if (result.changed === 0) {
    console.log("SEO H1 cache already current; 160 metadata values verified.");
    return;
  }
  await atomicJSON(rawPath, raw);
  await atomicJSON(processedPath, processed);
  console.log("SEO H1 cache refresh:", JSON.stringify(result), "(no image regeneration)");
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  main().catch(err => { console.error("H1 cache refresh failed:", err.message); process.exitCode = 1; });
}
