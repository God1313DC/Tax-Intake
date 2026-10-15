# Hostinger Laravel tax intake

Laravel 12 port deployed on ustaxdeals.com on 2026-10-15.

Routes: /tax-intake, /tax-intake/individual, /tax-intake/business and protected /tax-intake/team.

New route registration: append `require __DIR__.'/tax-intake.php';` to routes/web.php.
Homepage integration: include `intake.home-section` in the home view. Add a link to /tax-intake/team in the Admin/Editor dashboard. Add the three public intake URLs to the sitemap.

Submissions are encrypted with Laravel Crypt in storage/app/private/tax-intakes, with UUID filenames, stable per-record locks, atomic replacement, consent validation and per-session idempotency. Preserve the existing application key and private storage in hosting backups. Do not commit live client records or app secrets.

Mail uses the existing SMTP configuration and a private notification recipient setting on Hostinger. The generic config in this repository deliberately omits the recipient; configure INTAKE_NOTIFY_TO privately. Notifications contain a reference and authenticated link, not client tax answers. SMTP acceptance is not inbox receipt. If the process crashes after SMTP acceptance but before marking the record sent, an eventual retry can send a duplicate notification.

The deployment adds the `tax-intake:retry-notifications` Artisan command and a five-minute Hostinger cron job. Command implementation calls app(App\Services\TaxIntakeService::class)->retryPending() and outputs only an attempt count. Automatic retries stop after ten attempts; the protected workspace also offers manual retry. No mail credentials were changed.

Optional Ollama question explanations use INTAKE_OLLAMA_URL and INTAKE_OLLAMA_MODEL on an operator-controlled model service. They send predefined question text only. No model is connected at launch: guided help and deterministic document screening work without one. This is not an open-ended generative tax advisor or an automatic latest-law synchronization engine. Preparers must verify tax-year and state-specific requirements before filing.

Validation: PHP syntax checks; 16 service checks via tests/service-check.php (framework seams mocked); live Individual and Business synthetic submissions; business mail-server acceptance; duplicate retry and consent rejection. Anonymous workspace access redirects to login. An authenticated human review and inbox receipt were not completed during deployment.

The earlier Flask draft remains separate. Existing Render and Supabase projects were not changed by this Laravel deployment.
