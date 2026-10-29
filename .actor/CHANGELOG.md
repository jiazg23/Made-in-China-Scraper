## Unreleased

- Continue to actual searches after a failed homepage warm-up, saving its diagnostic HTML and summary.
- Use Chrome TLS/HTTP2 impersonation and persistent cookies for Made-in-China requests, including multipart image uploads.
- Support explicit Apify/custom proxy configuration and a sticky proxy session; report proxy initialization failures instead of silently disabling proxies.
- Record keyword HTTP failures in the run summary and apply strict empty-result behavior after all keywords have been attempted.
- Add regressions for the reported monitors input, blocked searches, proxy settings, retries, and multipart compatibility.

## 0.1

- Initial Made-in-China Product & Supplier Scraper (Reverse Image Search) release.
- Added multi-keyword product search with a separate supplier limit per keyword.
- Added batch reverse-image search for uploaded images and public image URLs, with a separate supplier limit per image.
- Added one-row-per-supplier aggregation with every matched product and source input preserved.
- Added public supplier profile enrichment, audited-supplier and membership fields, normalized prices and MOQs, CSV exports, diagnostics, and run summaries.
- Enabled combined CSV output by default so every run creates a named file in the key-value store unless the user disables it.
- Removed the example keyword prefill and silent fallback; the selected search mode now requires its own explicit user input.
