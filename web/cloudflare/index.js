/**
 * worker/index.js — IndicGovBench Edge Router & D1 API Service
 * 
 * Cloudflare Worker running on Free Tier constraints:
 * - Sub-2ms CPU execution time (pure JS, non-blocking D1 SQL).
 * - Serves Static Assets (HTML, CSS, JS, WebP images).
 * - Serves JSON REST APIs matching Python backend contracts.
 * - Collects crowd-sourced bug & annotation error reports into D1.
 * - Protects benchmark integrity by disabling authoring POST endpoints.
 */

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS, HEAD",
  "Access-Control-Allow-Headers": "Content-Type",
};

const JSON_HEADERS = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "public, max-age=60, s-maxage=300",
  ...CORS_HEADERS,
};

const PROVIDER_META_MAP = {
  gemini_3_1_pro: { display_name: "Gemini 3.1 Pro", org: "Google", category: "proprietary", tags: ["VLM", "Proprietary"], supports_batching: true, color: "#2563eb" },
  openai_gpt_6_1_sol: { display_name: "GPT-6.1 Sol", org: "OpenAI", category: "proprietary", tags: ["VLM", "Proprietary"], supports_batching: true, color: "#059669" },
  openai_gpt_6_luna: { display_name: "GPT-6 Luna", org: "OpenAI", category: "proprietary", tags: ["VLM", "Proprietary"], supports_batching: true, color: "#10b981" },
  openai_gpt_5_6_tera: { display_name: "GPT-5.6 Terra", org: "OpenAI", category: "proprietary", tags: ["VLM", "Proprietary"], supports_batching: true, color: "#059669" },
  mistral_api: { display_name: "Mistral OCR", org: "Mistral AI", category: "proprietary", tags: ["Doc VLM", "Proprietary"], supports_batching: false, color: "#e11d48" },
  gemini_3_8_flash: { display_name: "Gemini 3.8 Flash", org: "Google", category: "proprietary", tags: ["VLM", "Proprietary"], supports_batching: true, color: "#0284c7" },
  datalab_api: { display_name: "Marker API", org: "DataLab", category: "proprietary", tags: ["Doc AI", "Proprietary"], supports_batching: false, color: "#0891b2" },
  sarvam_api: { display_name: "Sarvam Vision API", org: "Sarvam AI", category: "proprietary", tags: ["Indic VLM", "Proprietary"], supports_batching: false, color: "#7c3aed" },
  claude_sonnet_5_5: { display_name: "Claude Sonnet 5.5", org: "Anthropic", category: "proprietary", tags: ["VLM", "Proprietary"], supports_batching: true, color: "#d97706" },
  qwen3_vl_8b: { display_name: "Qwen3-VL-8B", org: "Modal GPU", category: "open_weights", tags: ["VLM", "Open Weights"], supports_batching: false, color: "#4f46e5" },
  gemini_3_5_flash_lite: { display_name: "Gemini 3.5 Flash-Lite", org: "Google", category: "proprietary", tags: ["VLM", "Proprietary"], supports_batching: true, color: "#0ea5e9" },
  openai_gpt_5_6_luna: { display_name: "GPT-5.6 Luna", org: "OpenAI", category: "proprietary", tags: ["VLM", "Proprietary"], supports_batching: true, color: "#10b981" },
  claude_haiku_4_5: { display_name: "Claude Haiku 4.5", org: "Anthropic", category: "proprietary", tags: ["VLM", "Proprietary"], supports_batching: true, color: "#ea580c" },
  paddleocr_hpd: { display_name: "PaddleOCR v4", org: "PaddlePaddle", category: "classical_ocr", tags: ["OCR", "Open Source"], supports_batching: false, color: "#ca8a04" },
  tesseract: { display_name: "Tesseract 5.3", org: "Open Source", category: "classical_ocr", tags: ["OCR", "Open Source"], supports_batching: false, color: "#4b5563" },
};

const LANG_DISPLAY_NAMES = {
  marathi: "Marathi (मराठी)",
  hindi: "Hindi (हिन्दी)",
  english: "English",
  tamil: "Tamil (தமிழ்)",
  telugu: "Telugu (తెలుగు)",
  gujarati: "Gujarati (ગુજરાતી)",
  bengali: "Bengali (বাংলা)",
  kannada: "Kannada (ಕನ್ನಡ)",
  malayalam: "Malayalam (മലയാളം)",
  odia: "Odia (ଓଡ଼ିଆ)",
  punjabi: "Punjabi (ਪੰਜਾਬੀ)",
  assamese: "Assamese (অসমীয়া)",
  urdu: "Urdu (اردو)",
  sanskrit: "Sanskrit (संस्कृतम्)",
};

function jsonResponse(data, status = 200, customHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...JSON_HEADERS, ...customHeaders },
  });
}

function errorResponse(message, status = 400) {
  return jsonResponse({ status: "error", message }, status);
}

function safeParseJson(str, fallback) {
  if (!str) return fallback;
  try {
    return JSON.parse(str);
  } catch {
    return fallback;
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    // Handle CORS preflight
    if (method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    // -------------------------------------------------------------------------
    // 1. API Route Dispatcher
    // -------------------------------------------------------------------------
    if (path.startsWith("/api/")) {
      try {
        return await handleApiRequest(path, method, url, request, env);
      } catch (err) {
        return errorResponse(`Server Error: ${err.message}`, 500);
      }
    }

    // -------------------------------------------------------------------------
    // 2. Static Assets & Image Handling
    // -------------------------------------------------------------------------
    if (env.ASSETS) {
      // Direct rewrite for /protocol and /protocol/
      if (path === "/protocol" || path === "/protocol/") {
        return env.ASSETS.fetch(new Request(new URL("/protocol.html", request.url), request));
      }

      // Direct rewrite for /metrics and /metrics/
      if (path === "/metrics" || path === "/metrics/" || path === "/metrics_demo" || path === "/metrics_demo/") {
        return env.ASSETS.fetch(new Request(new URL("/metrics.html", request.url), request));
      }

      // Direct rewrite for /pricing and /pricing/
      if (path === "/pricing" || path === "/pricing/") {
        return env.ASSETS.fetch(new Request(new URL("/pricing.html", request.url), request));
      }

      // Query-based routing for landing page vs provider vs audit
      if (path === "/" || path === "/index.html") {
        if (url.searchParams.has("doc") || url.searchParams.has("doc_id")) {
          return env.ASSETS.fetch(new Request(new URL(`/audit.html${url.search}`, request.url), request));
        } else if (url.searchParams.has("provider") && url.searchParams.get("view") !== "attributes" && url.searchParams.get("view") !== "coverage") {
          return env.ASSETS.fetch(new Request(new URL(`/provider.html${url.search}`, request.url), request));
        }
      }

      // Smart WebP routing for /images/*
      if (path.startsWith("/images/")) {
        let filename = path.replace(/^\/images\//, "").replace(/\.png$/i, "");
        if (!filename.endsWith(".webp")) {
          filename += ".webp";
        }
        const imgUrl = new URL(`/images/${filename}`, request.url);
        const imgResp = await env.ASSETS.fetch(new Request(imgUrl, request));
        if (imgResp.status !== 404) {
          // Add aggressive edge caching for immutable document images
          const headers = new Headers(imgResp.headers);
          headers.set("Cache-Control", "public, max-age=86400, s-maxage=604800, immutable");
          return new Response(imgResp.body, {
            status: imgResp.status,
            headers,
          });
        }
      }

      // Default static asset fetch
      const assetResp = await env.ASSETS.fetch(request);
      if (assetResp.status !== 404) {
        return assetResp;
      }

      // Clean URLs candidate: e.g. /provider -> /provider.html
      const htmlCandidateUrl = new URL(`${path}.html${url.search}`, request.url);
      const htmlResp = await env.ASSETS.fetch(new Request(htmlCandidateUrl, request));
      if (htmlResp.status !== 404) {
        return htmlResp;
      }

      // SPA fallback to index.html for unknown HTML paths
      return env.ASSETS.fetch(new Request(new URL("/index.html", request.url), request));
    }

    return new Response("Not Found", { status: 404 });
  },
};

/**
 * Dispatches all `/api/*` endpoints
 */
async function handleApiRequest(path, method, url, request, env) {
  const db = env.DB;
  if (!db) {
    return errorResponse("Database binding (DB) not configured", 500);
  }

  // ---------------------------------------------------------------------------
  // GET /api/leaderboard
  // ---------------------------------------------------------------------------
  if (path === "/api/leaderboard" && (method === "GET" || method === "HEAD")) {
    const runId = url.searchParams.get("run") || url.searchParams.get("run_id") || "default";

    // 1. Fetch corpus evaluation metrics
    const ceStmt = db.prepare(`
      SELECT provider, composite_score, token_f1, textCER_norm, e2eNED_norm,
             TEDS, TEDS_S, ci_95_json, num_docs, num_tables,
             total_realtime_cost_inr, total_batch_cost_inr, total_savings_inr,
             avg_realtime_cost_inr, avg_batch_cost_inr, cost_per_1k_inr,
             native_currency, billing_mode
      FROM corpus_evaluations
      WHERE run_id = ?
      ORDER BY composite_score DESC
    `).bind(runId);

    // 2. Fetch dynamic dataset strata (Language x Horizon)
    const strataStmt = db.prepare(`
      SELECT 
          lower(trim(language)) as lang,
          lower(trim(horizon)) as horiz,
          count(*) as cnt
      FROM documents
      WHERE language IS NOT NULL AND trim(language) != ''
      GROUP BY lower(trim(language)), lower(trim(horizon))
    `);

    const [ceRes, strataRes] = await db.batch([ceStmt, strataStmt]);

    const providers = (ceRes.results || []).map((row) => {
      const p = { ...row };
      p.ci_95 = safeParseJson(p.ci_95_json, {});
      delete p.ci_95_json;

      const provId = p.provider;
      const meta = PROVIDER_META_MAP[provId] || {
        display_name: provId.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
        org: "Unknown",
        category: provId.includes("api") ? "proprietary" : "open_weights",
        tags: ["VLM"],
        color: "#94a3b8",
      };
      return { ...p, ...meta };
    });

    // Build dynamic language breakdown
    const languages = {};
    const totals = { current: 0, archive: 0, total: 0 };

    for (const sr of strataRes.results || []) {
      const l = sr.lang;
      if (!l) continue;
      const h = (sr.horiz || "").includes("archive") ? "archive" : "current";
      const cnt = sr.cnt || 0;

      if (!languages[l]) {
        languages[l] = {
          lang_key: l,
          display_name: LANG_DISPLAY_NAMES[l] || l.charAt(0).toUpperCase() + l.slice(1),
          current: 0,
          archive: 0,
          total: 0,
        };
      }

      languages[l][h] += cnt;
      languages[l].total += cnt;
      totals[h] += cnt;
      totals.total += cnt;
    }

    const preferredOrder = ["marathi", "hindi", "english"];
    const sortedLangKeys = Object.keys(languages).sort((a, b) => {
      const idxA = preferredOrder.indexOf(a);
      const idxB = preferredOrder.indexOf(b);
      if (idxA !== -1 && idxB !== -1) return idxA - idxB;
      if (idxA !== -1) return -1;
      if (idxB !== -1) return 1;
      return languages[b].total - languages[a].total;
    });

    const sortedLanguages = {};
    for (const k of sortedLangKeys) {
      sortedLanguages[k] = languages[k];
    }

    const strata = {
      languages: sortedLanguages,
      totals,
    };
    for (const [k, v] of Object.entries(sortedLanguages)) {
      strata[k] = v;
    }

    return jsonResponse({
      run_id: runId,
      strata,
      providers,
    });
  }

  // ---------------------------------------------------------------------------
  // GET /api/documents
  // ---------------------------------------------------------------------------
  if (path === "/api/documents" && (method === "GET" || method === "HEAD")) {
    const runId = url.searchParams.get("run") || url.searchParams.get("run_id") || "default";
    const provider = url.searchParams.get("provider") || "sarvam_api";
    const filterType = url.searchParams.get("filter") || "all";
    const search = (url.searchParams.get("search") || "").toLowerCase().trim();

    const docQuery = `
      SELECT 
          d.doc_id, d.has_tables, d.table_count, d.audit_status,
          d.department, d.horizon, d.language, d.scan_type, d.meta_json,
          pe.composite_score, pe.token_f1, pe.textCER_norm, pe.e2eNED_norm,
          pe.TEDS, pe.diff_counts_json, pe.evaluated_at,
          p.cost_realtime_inr, p.cost_batch_inr, p.prompt_tokens,
          p.candidates_tokens, p.total_tokens, p.pages_processed,
          p.gpu_seconds, p.billing_mode, p.native_currency
      FROM documents d
      LEFT JOIN page_evaluations pe 
          ON d.doc_id = pe.doc_id AND pe.provider = ? AND pe.run_id = ?
      LEFT JOIN predictions p
          ON d.doc_id = p.doc_id AND p.provider = ?
      ORDER BY d.doc_id ASC
    `;

    const provQuery = `SELECT * FROM corpus_evaluations WHERE run_id = ? AND provider = ?`;

    const [docRes, provRes] = await db.batch([
      db.prepare(docQuery).bind(provider, runId, provider),
      db.prepare(provQuery).bind(runId, provider),
    ]);

    const docs = [];
    for (const r of docRes.results || []) {
      const meta = safeParseJson(r.meta_json, {});
      const diffCounts = safeParseJson(r.diff_counts_json, {});
      delete r.meta_json;
      delete r.diff_counts_json;

      r.notes = meta.notes || "";
      r.diff_counts = diffCounts;
      r.is_stale = false; // Always verified on edge

      const comp = r.composite_score;

      // Filter logic
      if (filterType === "high_error" && (comp === null || comp >= 0.50)) continue;
      if (filterType === "low_error" && (comp === null || comp < 0.85)) continue;
      if (filterType === "has_table" && !r.has_tables) continue;
      if (filterType === "gt_review" && r.audit_status !== "needs_review") continue;
      if (search && !r.doc_id.toLowerCase().includes(search)) continue;

      docs.push(r);
    }

    const provStats = provRes.results && provRes.results[0] ? { ...provRes.results[0] } : {};
    if (provStats.ci_95_json) {
      provStats.ci_95 = safeParseJson(provStats.ci_95_json, {});
      delete provStats.ci_95_json;
    }

    return jsonResponse({
      run_id: runId,
      provider,
      filter: filterType,
      total_docs: docs.length,
      provider_stats: provStats,
      documents: docs,
    });
  }

  // ---------------------------------------------------------------------------
  // GET /api/document
  // ---------------------------------------------------------------------------
  if (path === "/api/document" && (method === "GET" || method === "HEAD")) {
    const docId = url.searchParams.get("doc_id") || url.searchParams.get("doc");
    if (!docId) return errorResponse("Missing 'doc_id' parameter", 400);

    const provider = url.searchParams.get("provider") || "sarvam_api";
    const runId = url.searchParams.get("run") || url.searchParams.get("run_id") || "default";

    const docStmt = db.prepare("SELECT * FROM documents WHERE doc_id = ?").bind(docId);
    const gtStmt = db.prepare(`
      SELECT block_id AS id, type, scope, order_idx, poly_json, text, html, reason, content, doc_category
      FROM ground_truth_blocks
      WHERE doc_id = ?
      ORDER BY order_idx ASC, block_id ASC
    `).bind(docId);
    const predStmt = db.prepare(`
      SELECT blocks_json, cost_realtime_inr, cost_batch_inr, prompt_tokens,
             candidates_tokens, total_tokens, pages_processed, gpu_seconds,
             billing_mode, native_currency, cost_info_json
      FROM predictions WHERE provider = ? AND doc_id = ?
    `).bind(provider, docId);
    const evalStmt = db.prepare(`
      SELECT composite_score, token_f1, textCER_norm, e2eNED_norm, TEDS, TEDS_S,
             diff_counts_json, table_evaluations_json, matched_units_json, diff_tokens_json, evaluated_at
      FROM page_evaluations
      WHERE run_id = ? AND provider = ? AND doc_id = ?
    `).bind(runId, provider, docId);
    const provsStmt = db.prepare(`
      SELECT p.provider, pe.textCER_norm, pe.diff_counts_json
      FROM predictions p
      LEFT JOIN page_evaluations pe 
          ON p.provider = pe.provider AND p.doc_id = pe.doc_id AND pe.run_id = ?
      WHERE p.doc_id = ?
      ORDER BY pe.composite_score DESC, p.provider ASC
    `).bind(runId, docId);
    const prevStmt = db.prepare("SELECT doc_id FROM documents WHERE doc_id < ? ORDER BY doc_id DESC LIMIT 1").bind(docId);
    const nextStmt = db.prepare("SELECT doc_id FROM documents WHERE doc_id > ? ORDER BY doc_id ASC LIMIT 1").bind(docId);
    const allStmt = db.prepare("SELECT doc_id FROM documents ORDER BY doc_id ASC");

    const [docR, gtR, predR, evalR, provsR, prevR, nextR, allR] = await db.batch([
      docStmt, gtStmt, predStmt, evalStmt, provsStmt, prevStmt, nextStmt, allStmt
    ]);

    const docRow = docR.results && docR.results[0];
    if (!docRow) return errorResponse(`Document '${docId}' not found`, 404);

    const docDict = { ...docRow };
    const meta = safeParseJson(docDict.meta_json, {});
    delete docDict.meta_json;
    docDict.meta = meta;
    docDict.notes = meta.notes || "";
    docDict.content_bbox = safeParseJson(docDict.content_bbox_json, []);
    delete docDict.content_bbox_json;

    // Process GT blocks
    const gtBlocks = [];
    let targetCounter = 0;
    for (const b of gtR.results || []) {
      const blk = { ...b };
      blk.poly = safeParseJson(blk.poly_json, []);
      delete blk.poly_json;
      blk.visual_order = blk.order_idx;
      if (blk.scope === "target") {
        blk.reading_order = targetCounter;
        blk.order = targetCounter;
        targetCounter++;
      } else {
        blk.reading_order = null;
        blk.order = null;
      }
      gtBlocks.push(blk);
    }

    // Process Predictions
    const predRow = predR.results && predR.results[0];
    const predBlocks = predRow ? safeParseJson(predRow.blocks_json, []) : [];
    let costInfo = predRow ? safeParseJson(predRow.cost_info_json, null) : null;
    if (!costInfo && predRow) {
      const cRt = predRow.cost_realtime_inr;
      const cBa = predRow.cost_batch_inr;
      costInfo = {
        pricing_type: predRow.billing_mode || "free",
        native_currency: predRow.native_currency || "INR",
        pages: predRow.pages_processed || 1,
        tokens: {
          input: predRow.prompt_tokens,
          output: predRow.candidates_tokens,
          total: predRow.total_tokens,
        },
        compute_details: {
          gpu_seconds: predRow.gpu_seconds,
        },
        cost_inr: {
          realtime: cRt,
          batch: cBa,
          savings: Math.max(0, (cRt || 0) - (cBa || 0)),
        },
      };
    }

    // Process Evaluation Data
    const peRow = evalR.results && evalR.results[0];
    const evalData = {};
    if (peRow) {
      evalData.composite_score = peRow.composite_score;
      evalData.token_f1 = peRow.token_f1;
      evalData.textCER_norm = peRow.textCER_norm;
      evalData.e2eNED_norm = peRow.e2eNED_norm;
      evalData.TEDS = peRow.TEDS;
      evalData.TEDS_S = peRow.TEDS_S;
      evalData.evaluated_at = peRow.evaluated_at;
      evalData.diff_counts = safeParseJson(peRow.diff_counts_json, {});
      evalData.word_alignments = []; // Omitted on Cloudflare to minimize payload
      evalData.table_evaluations = safeParseJson(peRow.table_evaluations_json, []);
      evalData.matched_units = safeParseJson(peRow.matched_units_json, []);
      evalData.diff_tokens = safeParseJson(peRow.diff_tokens_json, []);
    }

    // Available provider options
    const providerOptions = (provsR.results || []).map((r) => {
      const diffs = safeParseJson(r.diff_counts_json, {});
      return {
        provider: r.provider,
        textCER: r.textCER_norm,
        diff_count: diffs.all || 0,
      };
    });

    const prevDocId = prevR.results && prevR.results[0] ? prevR.results[0].doc_id : null;
    const nextDocId = nextR.results && nextR.results[0] ? nextR.results[0].doc_id : null;
    const allDocIds = (allR.results || []).map((r) => r.doc_id);

    return jsonResponse({
      run_id: runId,
      provider,
      doc_id: docId,
      document: docDict,
      ground_truth_blocks: gtBlocks,
      gcv_words: [], // Omitted on Cloudflare
      predictions: predBlocks,
      evaluation: evalData,
      provider_options: providerOptions,
      is_stale: false,
      revert_available: false,
      prev_doc_id: prevDocId,
      next_doc_id: nextDocId,
      all_doc_ids: allDocIds,
      cost_info: costInfo,
    });
  }

  // ---------------------------------------------------------------------------
  // GET /api/metadata/coverage
  // ---------------------------------------------------------------------------
  if (path === "/api/metadata/coverage" && (method === "GET" || method === "HEAD")) {
    const horizon = (url.searchParams.get("horizon") || "all").toLowerCase();
    const language = (url.searchParams.get("language") || "all").toLowerCase();
    const hasTables = (url.searchParams.get("has_tables") || "all").toLowerCase();
    const dept = url.searchParams.get("dept") || "all";

    const rowsRes = await db.prepare("SELECT * FROM documents ORDER BY doc_id ASC").all();
    const rows = rowsRes.results || [];

    const deptsSet = new Set();
    const langsSet = new Set();
    const horizSet = new Set();

    for (const r of rows) {
      if (r.department && r.department.trim()) deptsSet.add(r.department.trim());
      if (r.language && r.language.trim()) langsSet.add(r.language.trim().charAt(0).toUpperCase() + r.language.trim().slice(1));
      if (r.horizon && r.horizon.trim()) horizSet.add(r.horizon.trim().toLowerCase());
    }

    const filteredDocs = [];
    for (const r of rows) {
      const dHasTables = Boolean(r.has_tables);
      const dHorizon = (r.horizon || (r.doc_id.includes("_archive_") ? "archive" : "current")).trim().toLowerCase();
      const dLang = (r.language || "").trim().toLowerCase();
      const dDept = (r.department || "").trim();
      const meta = safeParseJson(r.meta_json, {});

      if (horizon !== "all" && dHorizon !== horizon) continue;
      if (language !== "all") {
        const docLangs = (meta.languages || []).map((l) => String(l).toLowerCase());
        if (dLang !== language && !docLangs.includes(language)) continue;
      }
      if (hasTables === "true" && !dHasTables) continue;
      if (hasTables === "false" && dHasTables) continue;
      if (dept !== "all" && dDept.toLowerCase() !== dept.toLowerCase()) continue;

      filteredDocs.push({
        doc_id: r.doc_id,
        horizon: dHorizon,
        language: dLang,
        department: dDept,
        has_tables: dHasTables,
        table_count: r.table_count || 0,
        scan_type: r.scan_type || "good",
        audit_status: r.audit_status || "unreviewed",
      });
    }

    const n = filteredDocs.length;
    const byHorizon = {};
    const byLang = {};
    const byDept = {};
    let tableCount = 0;

    for (const d of filteredDocs) {
      byHorizon[d.horizon] = (byHorizon[d.horizon] || 0) + 1;
      byLang[d.language] = (byLang[d.language] || 0) + 1;
      byDept[d.department] = (byDept[d.department] || 0) + 1;
      if (d.has_tables) tableCount++;
    }

    return jsonResponse({
      total_benchmark_docs: rows.length,
      filtered_count: n,
      coverage_pct: rows.length > 0 ? (n / rows.length) * 100 : 0,
      filters: { horizon, language, has_tables: hasTables, dept },
      distinct_values: {
        departments: Array.from(deptsSet).sort(),
        languages: Array.from(langsSet).sort(),
        horizons: Array.from(horizSet).sort(),
      },
      breakdowns: {
        by_horizon: byHorizon,
        by_language: byLang,
        by_department: byDept,
        tables_vs_not: {
          with_tables: tableCount,
          without_tables: n - tableCount,
        },
      },
      documents: filteredDocs,
    });
  }

  // ---------------------------------------------------------------------------
  // GET /api/attributes / /api/attributes/explorer
  // ---------------------------------------------------------------------------
  if ((path === "/api/attributes" || path === "/api/attributes/explorer") && (method === "GET" || method === "HEAD")) {
    const runId = url.searchParams.get("run") || url.searchParams.get("run_id") || "default";

    const ceStmt = db.prepare(`
      SELECT provider, composite_score, textCER_norm, e2eNED_norm, TEDS,
             avg_batch_cost_inr, avg_realtime_cost_inr, num_docs
      FROM corpus_evaluations
      WHERE run_id = ?
      ORDER BY composite_score DESC
    `).bind(runId);

    const docsStmt = db.prepare("SELECT * FROM documents ORDER BY doc_id ASC");

    const peStmt = db.prepare(`
      SELECT provider, doc_id, composite_score, textCER_norm, e2eNED_norm, TEDS,
             cost_batch_inr, cost_realtime_inr
      FROM page_evaluations
      WHERE run_id = ?
    `).bind(runId);

    const [ceRes, docsRes, peRes] = await db.batch([ceStmt, docsStmt, peStmt]);

    // Group evaluations by doc_id -> provider and compute exact page-level macro averages
    const peMap = {};
    const peStatMap = {};
    for (const r of peRes.results || []) {
      if (!peMap[r.doc_id]) peMap[r.doc_id] = {};
      peMap[r.doc_id][r.provider] = {
        composite_score: r.composite_score,
        textCER_norm: r.textCER_norm,
        e2eNED_norm: r.e2eNED_norm,
        TEDS: r.TEDS,
        cost_batch_inr: r.cost_batch_inr,
        cost_realtime_inr: r.cost_realtime_inr,
      };

      if (!peStatMap[r.provider]) {
        peStatMap[r.provider] = {
          count: 0,
          sumComposite: 0,
          sumTextCer: 0,
          sumNed: 0,
          sumTeds: 0,
          countTeds: 0,
          sumBatchCost: 0,
          sumRtCost: 0,
        };
      }
      const st = peStatMap[r.provider];
      st.count++;
      if (r.composite_score != null) st.sumComposite += r.composite_score;
      if (r.textCER_norm != null) st.sumTextCer += r.textCER_norm;
      if (r.e2eNED_norm != null) st.sumNed += r.e2eNED_norm;
      if (r.TEDS != null) {
        st.sumTeds += r.TEDS;
        st.countTeds++;
      }
      if (r.cost_batch_inr != null) st.sumBatchCost += r.cost_batch_inr;
      if (r.cost_realtime_inr != null) st.sumRtCost += r.cost_realtime_inr;
    }

    const providers = (ceRes.results || []).map((r) => {
      const pId = r.provider;
      const meta = PROVIDER_META_MAP[pId] || {
        display_name: pId.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
        org: "Provider",
        category: pId.includes("api") ? "proprietary" : "open_weights",
        tags: ["VLM"],
        color: "#6b7280",
        supports_batching: false,
      };

      const st = peStatMap[pId];
      const avgComposite = (st && st.count > 0) ? (st.sumComposite / st.count) : r.composite_score;
      const avgTextCer = (st && st.count > 0) ? (st.sumTextCer / st.count) : r.textCER_norm;
      const avgNed = (st && st.count > 0) ? (st.sumNed / st.count) : r.e2eNED_norm;
      const avgTeds = (st && st.countTeds > 0) ? (st.sumTeds / st.countTeds) : r.TEDS;
      const avgBatchCost = (st && st.count > 0) ? (st.sumBatchCost / st.count) : r.avg_batch_cost_inr;
      const avgRtCost = (st && st.count > 0) ? (st.sumRtCost / st.count) : r.avg_realtime_cost_inr;

      return {
        provider: pId,
        display_name: meta.display_name,
        org: meta.org,
        category: meta.category,
        tags: meta.tags || ["VLM"],
        supports_batching: Boolean(meta.supports_batching),
        color: meta.color,
        macro_composite: avgComposite,
        macro_textcer: avgTextCer,
        macro_ned: avgNed,
        macro_teds: avgTeds,
        avg_batch_cost_inr: avgBatchCost,
        avg_realtime_cost_inr: avgRtCost,
        baseline: {
          composite_score: avgComposite,
          textCER_norm: avgTextCer,
          e2eNED_norm: avgNed,
          TEDS: avgTeds,
        },
        corpus_baseline: {
          composite_score: r.composite_score,
          textCER_norm: r.textCER_norm,
          e2eNED_norm: r.e2eNED_norm,
          TEDS: r.TEDS,
        },
        doc_count: r.num_docs,
      };
    });

    const documents = (docsRes.results || []).map((r) => {
      const meta = safeParseJson(r.meta_json, {});
      const dId = r.doc_id;

      // Language
      let lang = r.language;
      if (!lang) {
        if (dId.includes("_mr_")) lang = "marathi";
        else if (dId.includes("_hi_")) lang = "hindi";
        else if (dId.includes("_en_")) lang = "english";
        else lang = "marathi";
      }
      lang = lang.toLowerCase().trim();

      // Horizon
      let horiz = r.horizon || (dId.includes("_archive_") ? "archive" : "current");
      horiz = horiz.toLowerCase().trim();

      // Scans: Tilt & Dots
      const scanTilt = Boolean(meta.scan_has_tilt);
      const scanDots = Boolean(meta.scan_has_dots || meta.scan_has_noise_dots);

      // Tables
      const hasTbl = Boolean(r.has_tables || meta.has_tables);
      let tblLayout = null;
      let tblBorders = null;
      const tblMerging = [];
      let tblCellSize = null;

      if (hasTbl) {
        // Layout
        if (typeof meta.table_has_full_page === "boolean") {
          tblLayout = meta.table_has_full_page ? "full" : "half";
        } else {
          const rawLayout = (meta.table_layout || "").toLowerCase();
          if (rawLayout.includes("full")) {
            tblLayout = "full";
          } else if (rawLayout.includes("half")) {
            tblLayout = "half";
          } else {
            tblLayout = ((meta.table_count || 0) > 1) ? "full" : "half";
          }
        }

        // Borders
        const rowLines = Boolean(meta.table_row_has_lines || meta.table_has_lines);
        const outerBorder = Boolean(meta.table_has_full_outer_border || meta.table_has_border_lines);
        const topBottom = Boolean(meta.table_has_only_bottom_top_border);

        if (rowLines && outerBorder) {
          tblBorders = "both";
        } else if (topBottom) {
          tblBorders = "top_bottom";
        } else {
          tblBorders = "no_border";
        }

        // Merging
        if (meta.table_has_merged_cols || meta.table_has_col_span) {
          tblMerging.push("col_merge");
        }
        if (meta.table_has_merged_rows || meta.table_has_row_span) {
          tblMerging.push("row_merge");
        }
        if (meta.table_has_multi_merged_cells) {
          tblMerging.push("cells_merged");
        }
        if (tblMerging.length === 0) {
          tblMerging.push("no_merge");
        }

        // Cell size
        const multiLine = Boolean(meta.table_cell_has_multi_lines || meta.table_has_multi_lines);
        tblCellSize = multiLine ? "multi_line" : "single_line";
      }

      return {
        doc_id: dId,
        language: lang,
        horizon: horiz,
        department: r.department || "Other",
        scan_type: r.scan_type || "good",
        scan_tilt: scanTilt,
        scan_dots: scanDots,
        has_tables: hasTbl,
        table_count: r.table_count || 0,
        table_layout: tblLayout,
        table_borders: tblBorders,
        table_merging: tblMerging,
        table_cell_size: tblCellSize,
        has_watermark: Boolean(r.has_watermark),
        rotation: r.rotation || 0,
        attributes: meta.attributes || {},
        evaluations: peMap[dId] || {},
      };
    });

    return jsonResponse({
      run_id: runId,
      total_docs: documents.length,
      total_documents: documents.length,
      providers,
      documents,
      evaluations: peMap,
    });
  }

  // ---------------------------------------------------------------------------
  // POST /api/report-error (Crowd-sourced Feedback)
  // ---------------------------------------------------------------------------
  if (path === "/api/report-error" && method === "POST") {
    let body;
    try {
      body = await request.json();
    } catch {
      return errorResponse("Invalid JSON payload", 400);
    }

    const { doc_id, provider, block_id, report_type, description, suggested_correction, reporter_name, reporter_email } = body;

    if (!doc_id || !report_type || !description) {
      return errorResponse("Missing required fields: doc_id, report_type, and description are required", 400);
    }

    const userAgent = request.headers.get("user-agent") || "";
    const clientIp = request.headers.get("cf-connecting-ip") || "";
    // Create an anonymized hash of IP for rate limiting / abuse prevention
    const clientIpHash = clientIp ? await hashString(clientIp) : "";

    const insertStmt = db.prepare(`
      INSERT INTO error_reports (
          doc_id, provider, block_id, report_type, description,
          suggested_correction, reporter_name, reporter_email,
          user_agent, client_ip_hash, created_at, status
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), 'pending')
    `).bind(
      doc_id,
      provider || null,
      block_id !== undefined && block_id !== null ? Number(block_id) : null,
      report_type,
      description.trim(),
      (suggested_correction || "").trim() || null,
      (reporter_name || "").trim() || null,
      (reporter_email || "").trim() || null,
      userAgent.slice(0, 255),
      clientIpHash
    );

    const res = await insertStmt.run();
    const reportId = res.meta && res.meta.last_row_id ? res.meta.last_row_id : null;

    return jsonResponse({
      status: "success",
      report_id: reportId,
      message: "Thank you! Your error report has been logged and queued for review.",
    });
  }

  // ---------------------------------------------------------------------------
  // Read-only block for local authoring APIs
  // ---------------------------------------------------------------------------
  if (path.startsWith("/api/gt/") || path.startsWith("/api/doc/")) {
    return errorResponse(
      "Modifications and re-evaluations are disabled on the public Cloudflare deployment. Please use the 'Report Error' feature to suggest corrections.",
      403
    );
  }

  return errorResponse(`Endpoint '${path}' not found`, 404);
}

/**
 * SHA-256 IP hasher for privacy-preserving client identification
 */
async function hashString(str) {
  const msgUint8 = new TextEncoder().encode(str + "-salt-indic");
  const hashBuffer = await crypto.subtle.digest("SHA-256", msgUint8);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 16);
}
