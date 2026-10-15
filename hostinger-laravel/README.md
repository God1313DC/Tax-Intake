# Hostinger Laravel tax intake

Laravel 12 port deployed on ustaxdeals.com on 2026-10-15.

Routes: /tax-intake, /tax-intake/individual, /tax-intake/business and protected /tax-intake/team.

New route registration: append `require __DIR__.'/tax-intake.php';` to routes/web.php.
Homepage integration: include `intake.home-section` in the home view. Add a link to /tax-intake/team in the Admin/Editor dashboard. Add the three public intake URLs to the sitemap.

Submissions are encrypted with Laravel Crypt in storage/app/private/tax-intakes, with UUID filenames, stable per-record locks, atomic replacement, consent validation and per-session idempotency. Preserve the existing application key and private storage in hosting backups. Do not commit live client records or app secrets.

Mail uses the existing SMTP configuration and a private notification recipient setting on Hostinger. The generic config in this repository deliberately omits the recipient; configure INTAKE_NOTIFY_TO privately. Notifications contain a reference and authenticated link, not client tax answers. SMTP acceptance is not inbox receipt. If the process crashes after SMTP acceptance but before marking the record sent, an eventual retry can send a duplicate notification.

The deployment adds the `tax-intake:retry-notifications` Artisan command and a five-minute Hostinger cron job. Command implementation calls app(App\Services\TaxIntakeService::class)->retryPending() and outputs only an attempt count. Automatic retries stop after ten attempts; the protected workspace also offers manual retry. No mail credentials were changed.

Optional Ollama question explanations use INTAKE_OLLAMA_URL and INTAKE_OLLAMA_MODEL on an operator-controlled model service. They send predefined question text only. The launch uses the free on-device semantic helper described below; a server-side generative model is not connected. This is not an open-ended generative tax advisor or an automatic latest-law synchronization engine. Preparers must verify tax-year and state-specific requirements before filing.

Validation: PHP syntax checks; 16 service checks via tests/service-check.php (framework seams mocked); live Individual and Business synthetic submissions; business mail-server acceptance; duplicate retry and consent rejection. Anonymous workspace access redirects to login. Authenticated Admin review has passed; actual inbox receipt remains unverified.

The earlier Flask draft remains separate. Existing Render and Supabase projects were not changed by this Laravel deployment.


## Free on-device AI activation (2026-10-15)

The launch now includes a CPU/WASM MiniLM semantic-matching helper. Clients opt in using Enable free AI. The helper downloads model/runtime files (tens of MB), encodes questions locally and returns reviewed knowledge-card text with reference links. It does not use a generative language model, cloud inference key or per-message API billing. Low-confidence queries ask for clarification; eligibility/amount/deadline questions are referred to the preparer. A timeout/stop control preserves the working guided form. The optional intake summary is built deterministically from selected questionnaire facts and must be reviewed before inclusion. It is stored as client-supplied helper text, never trusted as an eligibility decision.

Build the worker asset with pinned dependencies:

```
cd browser-ai-build
npm ci
npx esbuild src/intake-ai-worker.js --bundle --format=esm --platform=browser --outfile=../public/intake-assets/intake-ai-worker.js --minify --legal-comments=eof
```

AI library: Transformers.js 3.8.1. Model: Xenova/all-MiniLM-L6-v2, q8, pinned revision 751bff37182d3f1213fa05d7196b954e230abad9. Bundled third-party license comments are preserved in the generated asset. Model files/runtime load from the model vendor/CDN; inference prompts and embeddings are not uploaded. Normal intake submission still sends answers to this Laravel server after consent.

TaxIntakeSources fetches two allowlisted IRS document-collection pages, retains the last available text and records fetch errors/content hashes. The existing notification cron also calls refreshIfDue() once per day. The protected workspace shows status, fetch times and change-review flags; Admin can refresh sources manually. This is source freshness monitoring, not automatic rewriting or validation of all federal/state tax rules. Both source fetches succeeded in live verification.

Authenticated Admin review is now verified: both original test submissions were visible and marked sent, plus the helper-summary test was saved and its notification accepted. Live AI tests verified semantic matching for a paraphrased employer wage statement and the preparer-only response to a refund eligibility question. A tiny generative model was tested privately, failed factual-quality review and was not enabled in the client interface.
