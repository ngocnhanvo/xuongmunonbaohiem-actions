# Blue Sea Astro: Google CSP and GTM performance fix — 2026-10-09

## Deployment

- Astro development repository: `ngocnhanvo/xuongmunonbaohiem-astro`, branch `github`, commit `829e5bd1074a99e583eb097e1a6206ca9ccb3f8d`.
- Production branch: `master`, PR [#36](https://github.com/ngocnhanvo/xuongmunonbaohiem-astro/pull/36), merge commit `b363b4ca92c056c67e07613b892ac3e05ea52d17`.
- Build / FTP deploy: [Actions #37908707107](https://github.com/ngocnhanvo/xuongmunonbaohiem-actions/actions/runs/37908707107) — SUCCESS.
- Production smoke: [Actions #37908844080](https://github.com/ngocnhanvo/xuongmunonbaohiem-actions/actions/runs/37908844080) — SUCCESS.
- CSP + deferred loader server/HTML smoke: [Actions #37908890721](https://github.com/ngocnhanvo/xuongmunonbaohiem-actions/actions/runs/37908890721) — SUCCESS.
- Full browser E2E (no leads submitted): [Actions #37909503078](https://github.com/ngocnhanvo/xuongmunonbaohiem-actions/actions/runs/37909503078) — SUCCESS.

## Source changes

1. `scripts/inject-handler.js`: add explicit `connect-src` allowed hosts `analytics.google.com`, `stats.g.doubleclick.net`, `ad.doubleclick.net`, `googleads.g.doubleclick.net`; permit the latter in `script-src`. Existing restrictive default/object policies stay in place; no wildcards.
2. `src/astro/components/Layout/GoogleServices.astro`: GTM loads on first pointer/touch/keyboard interaction or 8 seconds after `window.load`, whichever comes first. Direct `gtag` mode unchanged. `dataLayer` is initialized immediately; each page starts GTM at most once; no UA or Lighthouse detection.
3. `src/lib/googleLeadConversions.ts`: when a form is server-confirmed, invoke deferred GTM bootstrap before queueing `event: "form"` with non-PII `form_type`. The previously implemented form deduplication remains.
4. `src/lib/googleTrackingRuntime.test.ts`: tests inlined runtime GTM loader, 8 second fallback, first interaction, at-most-once startup, lead event ordering, ignored dev host, and actual generated CSP policy.

No WordPress changes. All build/bench/test/deploy workflows run in `xuongmunonbaohiem-actions`, not PHP/Astro repositories.

## Lighthouse comparison

Five Lighthouse 13.4.1 **mobile** runs per version on GitHub Actions Ubuntu/Chrome runners; same CLI arguments and target URL. Compare these numbers with each other, not with user-local Windows/PSI results.

| Median | Before | After |
|---|---:|---:|
| Performance | 48 | **97** |
| Total Blocking Time | 947 ms | **0 ms** |
| LCP | 9,092 ms | **2,304 ms** |
| FCP | 2,412 ms | **1,417 ms** |
| CLS | 0 | **0** |

- Baseline [#37908305849](https://github.com/ngocnhanvo/xuongmunonbaohiem-actions/actions/runs/37908305849), five completed runs.
- After [#37909112635](https://github.com/ngocnhanvo/xuongmunonbaohiem-actions/actions/runs/37909112635), five completed runs; a transient Chrome NO_NAVSTART was retried. No successful sample was repeated.

### Caveats

- Third-party JS execution is shifted **later**, not permanently removed. Lighthouse lab scores principally reflect reduced work *during its observation window*. Users who interact early may still experience deferred third-party work.
- Pageviews from visitors leaving before the delayed GTM load may be missed. The user explicitly accepted this risk.
- A confirmed lead starts GTM immediately and queues the `form` event, but the old Google Ads account/container remains external. Test scripts intentionally did not generate fake leads or claim Ads conversion ingestion.
- The reported `ad.doubleclick.net` HTTP 405 is distinct from a CSP refusal and cannot be guaranteed fixed by changing headers.
- The CSP still inherits some historical ESC-related allowed hosts. Any further tightening should verify website-specific dependencies and be done separately, not by blanket domain removal.
