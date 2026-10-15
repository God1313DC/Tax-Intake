# Tax Intake

A tax intake workflow and document collection system designed to streamline client onboarding, organize submitted information, and support a smoother tax preparation process.

## Overview

This project helps collect, manage, and review tax-related intake information in a structured way. It is built to reduce manual back-and-forth, improve organization, and make document handling easier.

## Features

- Client tax intake workflow
- Document collection and organization
- Rule-based handling for tax-related inputs
- Simple backend structure
- Template-driven interface

## Project Structure

.
├── app.py
├── models.py
├── requirements.txt
├── tax_rules.py
├── templates/
└── instance/

## Tech Stack

- Python
- Flask
- HTML templates
- SQLite or local development database

## Setup

Clone the repository:

git clone https://github.com/God1313DC/Tax-Intake.git
cd Tax-Intake

Create a virtual environment:

python3 -m venv .venv
source .venv/bin/activate

Install dependencies:

pip install -r requirements.txt

Run the application:

python app.py

## Notes

- This repository is intended for project demonstration and workflow presentation.
- Do not upload real client data, confidential tax documents, or secret keys.
- Use sample or dummy data only.

## Future Improvements

- Better UI/UX for intake flow
- Secure authentication
- Cloud database integration
- Document status tracking
- Admin dashboard and analytics

## Author

Dev Chauhan

## Guided intake (implementation preview)

New routes: `/start`, `/intake/individual`, `/intake/business`, and authenticated
`/intake-team`. The original `/` form and historical dashboard are preserved.
Dashboard navigation links to the new workspace.

This branch is an implementation preview, not a verified production launch.
It uses this Flask app's SQLite database; it does **not** migrate or write to the
separate Supabase RefundIQ project. Confirm which database should be the system
of record before live client use. `DATABASE_PATH` must point at durable storage
on Render, or replace the persistence layer with reviewed Supabase integration.
Render ephemeral disk must not hold the only copy of client submissions.

### Email setup

Set these server environment variables through the hosting dashboard:
`SMTP_HOST`, `SMTP_PORT` (587 by default, STARTTLS required), `SMTP_USER`,
`SMTP_PASSWORD`, `MAIL_FROM`, `INTAKE_NOTIFY_TO`, and `PUBLIC_BASE_URL` (HTTPS).
Use provider-approved SMTP credentials; never commit credentials. The recipient
address must be explicitly confirmed by the owner. Unconfigured delivery remains
pending; delivery failures remain visible as failed. Schedule
`flask --app app retry-intake-email` every few minutes to retry pending/failed
mail. Inspect any `sending` records after a process crash before resetting them;
the SMTP server may already have accepted their message.

Notifications contain a reference and authenticated workspace link, not customer
answers. Send an authorized sample intake and confirm actual receipt before
launch. SMTP acceptance does not prove inbox delivery. This workflow is at-least-
once delivery: a crash after SMTP acceptance can require manual reconciliation.

### Optional AI

Set `OLLAMA_URL` to an operator-controlled Ollama server and `OLLAMA_MODEL` to an
installed model. Keep the endpoint private/authenticated at the network layer;
do not publicly expose an unauthenticated Ollama server. This integration sends
only predefined question text, never client answers, and offers AI explanations
via Explain question. Without a model, or when the model fails, built-in help
continues working. The default is guided/rule-based mode, not generative AI.
A local model has no per-call API bill but needs compute and availability.
This release does not implement open-ended tax chat or AI-generated eligibility.

### Tax guidance boundary

Document categories reference IRS personal-document and business-record guidance
reviewed October 15, 2026. They are collection prompts, not a complete annual
federal/state rules engine. There are no automatic law updates, credit/refund
calculations, eligibility decisions, or filing deadline calculations. Before
launch, preparers must review both flows, add tax-year/source-versioned rules and
state-specific coverage, and test representative cases. Never advertise this
preview as automatically compliant with the latest tax law.

### Website buttons

After staging verification, link website buttons to the deployed routes:

```html
<a href="https://tax-intake.onrender.com/intake/individual">Individual Tax Intake</a>
<a href="https://tax-intake.onrender.com/intake/business">Business Tax Intake</a>
```

These links require deploying this branch first. No website files or production
Supabase schema have been changed by this branch.

### Validation

`python -m unittest discover -s tests -v`

Production configuration must include `SECRET_KEY`, `DASH_USER`, and a strong
`DASH_PASS`. Cookies default to Secure, HttpOnly and SameSite=Lax. Use
`COOKIE_SECURE=false` only for local HTTP development. Rate limiting, retention,
authentication hardening and durable database setup need review before launch.
