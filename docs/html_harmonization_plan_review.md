# Review: HTML Harmonization & Mobile Plan

Feedback on `docs/html_harmonization_and_mobile_plan.md`, checked against the current code in `web/`. Apply these changes to the plan before you implement it.

---

## A. Owner decisions (these override the plan)

1. **Do not link Protocol from anywhere.** Leave it out of the header nav, the mobile drawer, the footer and the landing page. The owner shares the URL directly when needed. The global nav therefore has **4 items**: Leaderboard, Pricing, Metrics, Attributes. `protocol.html` itself still gets the shared header, footer, tokens and mobile fixes. Keep the assertions in `tests/test_studio.py:24-25`.
2. **Footer licence: CC BY 4.0.**
3. **Add the contact email `info@orgpedia.in` to the footer** (`mailto:` link). Keep the existing "Official Site" link (`https://indicgovbench.orgpedia.in`) in the header, alongside GitHub and HuggingFace.
4. **No mobile audit view.** Drop the 3-tab segmented control. For `audit.html`, only make sure the shared header renders and the page doesn't overflow horizontally on phones. The audit workspace stays a desktop tool.

---

## B. Fix this first (existing bug on Cloudflare)

`web/cloudflare/index.js:124` redirects `provider.html?run=…&provider=X` to `/provider_X` and drops the query string. `js/provider_page.js` then finds no `provider` parameter and falls back to `gemini_3_1_pro`. On Cloudflare, every pre-built provider page therefore:
- overwrites its correct pre-rendered badge with `gemini_3_1_pro (default)`;
- opens **Gemini's** audit view when a document row is clicked (`views/provider_workspace.js:370,379`).

The local server (`web/studio/server.py:261`) keeps the query string, which is why this only shows up in production.

Fix both:
- Keep the query string in the redirect: `` new URL(`/provider_${prov}${url.search}`, request.url) ``.
- Have `generate_provider_pages.py` write the provider and run into the page (for example `<body data-provider="…" data-run="…">`). `provider_page.js` should read those first and fall back to URL params only if they're missing. The page should never depend on the query string to know which provider it shows.

---

## C. Architecture changes the plan needs

### C1. One source for the header and footer

The header is currently written separately in all of these places:
- `web/studio/templates/index.template.html`
- `generate_pricing_html.py`
- `generate_protocol_html.py` (line ~622)
- `generate_provider_pages.py` (line ~314)
- `metrics_tutorial/generate_html.py` (no header at all)
- the hand-written `static/attributes.html` and `static/provider.html`
- `js/app.js`, which builds it with `innerHTML` in **5 places** (lines 133, 186, 228, 269, 380). The header in `audit.html` is empty and only JS fills it (`renderHeader()`).

Required:
- Create one Python module, e.g. `web/studio/site_chrome.py`, with `render_header(active, badge, actions_html="")` and `render_footer()`. Every generator imports it, including `metrics_tutorial/generate_html.py`.
- For the hand-written pages (`attributes.html`, `provider.html`, `audit.html`), either generate them through the same helper, or paste the identical markup and add a test that compares it with the helper's output.
- In `app.js`, replace the 5 header builders with one function that produces the same markup. It must include an **actions slot** for page-specific buttons: audit needs back-to-provider, Notes, Shortcuts and the strata text. The plan's header markup has no place for these.
- Put the shared hamburger/drawer behaviour in `js/nav.js`. `cf_export.py` already copies `js/` wholesale, so the new file will be deployed with no extra work.

### C2. Split `layout.css` instead of linking it everywhere

`layout.css` applies to every page that links it:
- `* { margin: 0; padding: 0 }` (line 4)
- `html, body { height: 100vh; width: 100vw; overflow: hidden }` (line 31)

Pages escape this only through `body.landing-mode`, which overrides it with `!important` rules; `components.css` has 343 `!important` declarations.

**Phase 3 links `layout.css` into protocol and metrics. Don't do that as-is.** It would lock both pages so they can't scroll, and it would strip the spacing from the protocol's markdown (list indents, paragraph and heading margins).

Instead:
- Make the base styles assume a normal scrolling page: a light reset with no blanket margin/padding removal, and no `100vh` lock.
- Move the fixed full-screen layout (`#app-container` at 100vh, the pane grids, `overflow: hidden`) under an opt-in class `body.app-shell`. Only `audit.html` and the provider pages use it.
- Remove the `landing-mode` override block (`components.css` around lines 1600–1800) and fold its rules into the defaults.
- Use `width: 100%` instead of `100vw`. `100vw` causes horizontal overflow whenever a vertical scrollbar is visible.

### C3. Limit the mobile scroll unlock to document pages

§3.2 says to override `height: 100vh; overflow: hidden` with `!important` under 768px on every page. That breaks the provider and audit pages, which rely on the locked layout so their inner panels scroll (`.doc-list-table-wrapper { flex: 1; overflow-y: auto }`). Once C2 is done, this override isn't needed: document pages already scroll, and `.app-shell` pages need their own small-screen rules.

### C4. Budget for removing inline styles

Shared colour variables and media queries can't override `style="…"` attributes without `!important`. Approximate counts:

| File | Inline `style=` |
|---|---|
| `js/views/attributes.js` | 128 |
| `metrics_tutorial/generate_html.py` | 121 |
| `js/app.js` | 115 |
| `templates/index.template.html` | 74 |
| `js/landing.js` | 56 |
| `generate_pricing_html.py` | 35 |
| `generate_provider_pages.py` | 28 |
| `js/views/provider_workspace.js` | 22 |
| `generate_landing_html.py` | 20 |

For each page you touch, move the layout and colour inline styles into classes in `components.css`. Treat this as an explicit task in each phase; it is the main cost of the work.

---

## D. Corrections to the plan's description of the current pages

- **protocol.html** already has a `#global-header` with back-to-leaderboard and metrics links, already links `css/tokens.css`, and uses the same system fonts. Its problems are the inline `:root` block, the scroll lock and the 320px sidebar. The work is to swap in the shared header (with Protocol not in the nav) and fix the layout. Also remove its current "Audit Workspace →" and "Metrics Demo ↗" header buttons, or replace them through the shared header.
- **metrics.html** is the only page with no site header.
- **pricing.html** has **no** inline `:root` block. Its `<style>` block defines `.pricing-stat-box`, `.compact-table`, `.source-*-link` and others, and these exist **only** there. Move them into `components.css` before deleting the block. Also remove the stale arXiv link from its header (the paper link was removed elsewhere).
- **There is no "980px fixed" pricing table.** 980px is the `max-width` of `.summary-container` (`components.css:1665`). The table is already inside `.benchmark-table-wrapper`, which has `overflow-x: auto` (`components.css:1795`). **Don't add a new `.table-scroll-wrapper`.** Reuse and generalize `.benchmark-table-wrapper` and `.doc-list-table-wrapper`.
- **The leaderboard table and cards are built in the browser by `js/landing.js`** (around line 225; `viewMode = 'table'` at line 32; toggle around line 982). They are not built by `generate_landing_html.py` or the template, so add `landing.js` to Phase 4. For "cards by default under 640px": choose the initial mode with `matchMedia('(max-width: 640px)')` and don't override a mode the user picked.
- **The attribute grid's `minmax(360px, 1fr)` appears in 3 places:** `generate_landing_html.py:213`, `generate_landing_html.py:282`, `js/attribute_catalog.js:216`. Apply `minmax(min(100%, 320px), 1fr)` in all three, or better, move it into one CSS class.

---

## E. Page-specific technical notes

**Protocol**
- Back-to-top and its visibility check are tied to `#main-reader` (`protocol.html:3799–3812`, generated by `generate_protocol_html.py`). With normal page scrolling on mobile, listen on `window` instead, or switch based on the active layout.
- The TOC drawer must close when a link is tapped, and the sticky "📑 Table of Contents" bar must not cover content.
- Add `scroll-margin-top` (header height + sticky bar + a few px) to `h1–h4[id]`. No such rule exists yet, so TOC links will land with the heading hidden under the sticky header.
- Removing the inline `:root` changes colours. For example, protocol's `--text-muted: #64748b` currently overrides tokens.css's `#475569`. Map each old variable to a token on purpose, and rename collisions (`--border`, `--accent`, `--text-primary`, etc.) to the token names.

**Metrics**
- `.doc-sheet` has a fixed `height: 480px` with blocks positioned in percentages (`generate_html.py` around line 358). At 100% width on a phone this distorts the layout and makes the 11px block text unreadable. Use `aspect-ratio` (from the document's width/height) instead of a fixed height, and allow horizontal scroll or pinch-zoom inside the sheet below about 480px.
- Turn the 340px case sidebar into a top `<select>` or a drawer under 768px. The body currently has `display: flex; height: 100vh; overflow: hidden`.

**Sticky first column (pricing, provider document table)**
- `.doc-list-table` has `overflow: hidden` and a border radius (`components.css:1151`). Remove the overflow and put the rounding on the wrapper, or sticky cells may not stick.
- Pricing has `colspan="6"` group rows. Make sure the sticky rule doesn't apply to these group cells.
- Two sticky columns (`#` and Model) need the second column's `left` offset set to the first column's width. Sticky cells need an opaque background.

**Anchor offsets everywhere**
- Add a global rule `[id] { scroll-margin-top: calc(var(--header-height) + 8px); }` (or similar). Otherwise `index.html#section-results` lands with the heading under the sticky header.

---

## F. Contradictions in the plan to resolve

- **Palette.** The plan mixes the slate family (`#0f172a`, `#e2e8f0`, `#64748b`, used by tokens.css, protocol and metrics) with Tailwind's gray family (`#111827`, `#e5e7eb`, `#6b7280`, used in the `landing-mode` CSS and inline styles). **Use slate, matching the existing `tokens.css`:** keep `--border-subtle: #e2e8f0` and `--text-main: #0f172a`. Update the checklist in §7, which says `#111827`, and §3.1, which says `#e5e7eb`.
- **Nav labels.** Use "Metrics" in both the header and the drawer (§3.1 says "Metrics Demo").
- **Hamburger breakpoint.** At 768px the header won't fit (brand, badge, 4 links, 3 repo links, page actions) between roughly 800 and 1100px. Either raise the breakpoint to about 1024px or hide the badge or repo labels at medium widths. Test at 900px and 1024px as well.
- **Breadcrumbs.** The brand link, the "Leaderboard" nav item and a "← Back to Leaderboard" button on every page all go to the same place. Drop the generic back button. Keep breadcrumbs only where they add a level: provider pages (Leaderboard › Provider) and audit (Leaderboard › Provider › Doc).
- **Context badge.** Use the display name (`PROVIDER_DISPLAY_NAMES` in `generate_provider_pages.py`), e.g. "Gemini 3.1 Pro", not `gemini_3_1_pro (default)`. `provider_page.js` must stop overwriting the pre-rendered badge (see B).
- **Drawer accessibility** (the plan calls it "accessible"):
  - toggle with a class, not inline `style="display:none"`;
  - add `aria-expanded` and `aria-controls` on the hamburger, and an `aria-label` on the ✕ button;
  - close on Escape and on backdrop click, and return focus to the hamburger;
  - add `rel="noopener noreferrer"` on every `target="_blank"` link, including the drawer and footer;
  - drop `maximum-scale=5.0` from the viewport tag; it isn't needed.
- **Deploy command.** `cf_deploy` already depends on `cf_export`, which depends on `html`, so `make cf_export SKIP_IMAGES=1 && make cf_deploy` builds twice. Use `make cf_deploy SKIP_IMAGES=1`.
- **Roadmap.** The Gantt chart and Phase 4 leave out `attributes.html`, `provider.html`, `audit.html`, `js/app.js` and `js/landing.js`. Add them.

---

## G. Revised footer

Plain text, no emoji:

```
IndicGovBench-Orders — A standardized benchmark for document transcription and
table extraction across Indian government orders.
Orgpedia Foundation · CC BY 4.0
GitHub · HuggingFace · Contact: info@orgpedia.in
```

Show it on the pages that scroll normally (index, pricing, protocol, metrics, attributes). It's optional on the full-screen `.app-shell` pages (provider, audit).

---

## H. Revised phase order

1. **Fix the Cloudflare provider redirect and the badge/provider source** (section B). Add a test that checks each pre-built provider page has the correct `data-provider`.
2. **CSS foundation:** split `layout.css` into base + `.app-shell`, remove the `landing-mode` overrides, finalize the slate tokens, add the `scroll-margin-top` rule, and add `.mobile-only` / `.desktop-only` and the table wrapper rules.
3. **Shared header, footer and `nav.js`** through `site_chrome.py`, plus the single header function in `app.js`.
4. **Protocol and Metrics** generators: shared chrome, TOC/case drawers, scroll handling, `aspect-ratio` on the doc sheet.
5. **Landing (template + `landing.js`), Pricing, Provider pages, Attributes:** move inline styles into classes, sticky columns, cards default on phones, attribute grid fix in all 3 places.
6. **Audit:** shared header only, no horizontal overflow. No mobile tabs.
7. **`make html`, then test at 375, 412, 768, 900, 1024 and 1440px wide, then `make cf_deploy SKIP_IMAGES=1`.**

## I. Extra acceptance checks

- [ ] No `href` to `/protocol` or `protocol.html` in any nav, drawer, footer or landing page. `tests/test_studio.py` passes.
- [ ] On the Cloudflare deployment, `/provider.html?provider=tesseract` shows the Tesseract badge, and clicking a document row opens the Tesseract audit view.
- [ ] Every page's header markup comes from `site_chrome.py` or exactly matches its output (enforced by a test).
- [ ] The protocol TOC links and `index.html#section-results` land with the heading visible below the sticky header.
- [ ] Back-to-top on the protocol page works on both desktop and mobile.
- [ ] No horizontal page scroll at 375px on any page, including audit (whose panes may still be cramped).
- [ ] Inline `style=` counts go down in every file touched, and no new `!important` rules are added.
