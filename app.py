from flask import Flask, request, redirect, session, render_template_string
import sqlite3, os, json
from datetime import datetime

# -------------------------
# Config
# -------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key-now")

DASH_USER = os.environ.get("DASH_USER", "admin")
DASH_PASS = os.environ.get("DASH_PASS", "admin123")  # change this

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "tax_intake.db")

# -------------------------
# DB
# -------------------------
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()
    con.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            full_name TEXT,
            email TEXT,
            phone TEXT,
            filing_year TEXT,
            answers_json TEXT,
            radar_json TEXT,
            email_request_json TEXT,
            preparer_summary TEXT
        )
    """)
    con.commit()
    con.close()

init_db()

# -------------------------
# Helpers
# -------------------------
def yn(v):
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("yes","y","true","1"):
        return True
    if s in ("no","n","false","0"):
        return False
    return None

def pick(v, default=""):
    return (v or default).strip()

def add_item(lst, level, title, why, forms=None):
    lst.append({
        "level": level,              # LIKELY / POSSIBLE / UNLIKELY / REVIEW
        "title": title,
        "why": why,
        "forms": forms or []
    })

def dedupe(seq):
    out = []
    seen = set()
    for x in seq:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out

def risk_note(text):
    return f"Verify eligibility before filing: {text}"

# -------------------------
# Screening Engine (Refund Radar)
# -------------------------
def evaluate(a: dict):
    """
    NO SSN / NO docs.
    Purpose: Never miss credits/deductions and guide preparers to ask the right follow-ups.
    """
    radar = []
    email_requests = []

    # --- basic ---
    marital = pick(a.get("marital_status")).lower()
    lived_us_6mo = yn(a.get("lived_us_6mo"))
    can_be_claimed = yn(a.get("can_be_claimed"))
    nonresident = yn(a.get("nonresident_or_dual_status"))

    # --- dependents / HOH / EITC due diligence ---
    has_deps = yn(a.get("has_dependents"))
    dep_lived_half = yn(a.get("dep_lived_half_year"))
    paid_half_home = yn(a.get("paid_half_home"))
    someone_else_claim = yn(a.get("someone_else_claim_child"))
    custody_8332 = yn(a.get("custody_agreement"))
    support_over_half = yn(a.get("you_provided_support"))
    child_age_signal = yn(a.get("child_under_19_or_student"))

    # --- income signals (no exact numbers needed, use ranges) ---
    earned_income = any(yn(a.get(k)) is True for k in ["has_w2","has_1099_nec","has_1099_k","cash_income","self_employed"])
    investment_income = yn(a.get("investment_income_significant"))
    investment_income_over_limit = yn(a.get("investment_income_over_limit"))  # user self-attest

    # --- credits drivers ---
    childcare = yn(a.get("childcare"))
    marketplace = yn(a.get("marketplace_1095a"))
    education = yn(a.get("education_1098t"))
    retirement_contrib = yn(a.get("retirement_contrib"))
    hsa = yn(a.get("hsa"))
    student_loan = yn(a.get("student_loan_interest"))

    # --- other ---
    moved_states = yn(a.get("moved_states"))
    self_employed = yn(a.get("self_employed"))
    business_expenses = yn(a.get("business_expenses"))
    mortgage_1098 = yn(a.get("mortgage_1098"))
    property_tax = yn(a.get("property_tax"))
    charity = yn(a.get("charity"))
    large_medical = yn(a.get("large_medical"))
    crypto = yn(a.get("crypto"))
    foreign_accounts = yn(a.get("foreign_accounts"))
    unemployment = yn(a.get("unemployment"))
    gambling = yn(a.get("gambling"))

    # -------------------------
    # EITC (screening)
    # -------------------------
    if nonresident is True:
        add_item(radar, "UNLIKELY", "EITC (Earned Income Tax Credit)",
                 "Nonresident/dual-status indicated. EITC often not allowed depending on status.",
                 forms=["EITC"])
        email_requests.append("Residency/immigration tax status clarification (email).")
    else:
        if earned_income and can_be_claimed is not True and lived_us_6mo in (True, None):
            if has_deps is True:
                if someone_else_claim is True:
                    add_item(radar, "POSSIBLE", "EITC (with qualifying child)",
                             "Earned income + dependents, but someone else may claim the child. Tie-breaker rules matter.",
                             forms=["EITC", "Due Diligence"])
                    email_requests.append("EITC QC: residency nights, relationship, competing claimant & tie-breaker facts (email).")
                elif custody_8332 is True:
                    add_item(radar, "POSSIBLE", "EITC (with qualifying child)",
                             "Custody/8332 possibility. Who can claim and EITC QC tests must be verified.",
                             forms=["EITC", "8332 (if relevant)"])
                    email_requests.append("Custody/claiming facts: who child lived with, any 8332 release (email).")
                elif dep_lived_half in (True, None):
                    add_item(radar, "LIKELY", "EITC (with qualifying child)",
                             "Strong signals present. Verify qualifying child tests + income limits.",
                             forms=["EITC", "Due Diligence"])
                    email_requests.append("EITC QC: dependent DOB/relationship/residency/support + confirm no other claimant (email).")
                else:
                    add_item(radar, "POSSIBLE", "EITC (with qualifying child)",
                             "Dependents indicated but residency > half year not confirmed.",
                             forms=["EITC"])
                    email_requests.append("Confirm dependent residency nights (email).")
            else:
                add_item(radar, "POSSIBLE", "EITC (no qualifying child)",
                         "Earned income present. Verify age rules and income/investment income limits.",
                         forms=["EITC"])
                email_requests.append("Confirm taxpayer age range + income range + investment income range (email).")
        else:
            add_item(radar, "UNLIKELY", "EITC (screening)",
                     "Missing core signals: earned income/residency or taxpayer might be claimable by someone else.",
                     forms=["EITC"])

    # investment income risk for EITC
    if investment_income_over_limit is True:
        add_item(radar, "REVIEW", "EITC Investment Income Limit Risk",
                 "Client indicated investment income may exceed EITC limits. Confirm amounts.",
                 forms=["EITC"])
        email_requests.append("Confirm interest/dividends/capital gains totals (email).")

    # -------------------------
    # Head of Household (HOH)
    # -------------------------
    if has_deps is True and paid_half_home is True and marital != "married":
        add_item(radar, "POSSIBLE", "Head of Household",
                 "Dependents + paid > half household costs. Verify qualifying person & marital/separation rules.",
                 forms=["Filing Status"])
        email_requests.append("HOH: household cost totals + who lived in home + marital separation facts (email).")
    else:
        add_item(radar, "UNLIKELY", "Head of Household (screening)",
                 "Needs qualifying person + > half household costs + correct marital rules.",
                 forms=["Filing Status"])

    # -------------------------
    # CTC / ACTC / ODC
    # -------------------------
    if has_deps is True:
        if child_age_signal is True:
            add_item(radar, "POSSIBLE", "Child Tax Credit / Additional CTC",
                     "Dependent age/student indicator suggests CTC/ACTC possible. Verify age/residency/SSN rules via docs by email.",
                     forms=["CTC/ACTC"])
        else:
            add_item(radar, "POSSIBLE", "Other Dependent Credit (ODC)",
                     "Dependents indicated; ODC may apply depending on dependent type.",
                     forms=["ODC"])
        if support_over_half is False:
            add_item(radar, "REVIEW", "Dependent Support Risk",
                     "Client indicated they may NOT provide > half support. Confirm support facts; may impact dependency credits.",
                     forms=["Dependency"])
            email_requests.append("Support facts: who supported dependent, shared support agreements (email).")
        email_requests.append("Dependents: ages/student status + residency + who else may claim (email).")
    else:
        add_item(radar, "UNLIKELY", "Child-related credits",
                 "No dependents indicated.",
                 forms=["CTC/ODC"])

    # -------------------------
    # Child & Dependent Care Credit (2441)
    # -------------------------
    if childcare is True:
        add_item(radar, "POSSIBLE", "Child & Dependent Care Credit",
                 "Childcare expenses indicated (must be to work/school).",
                 forms=["Form 2441"])
        email_requests.append("2441: provider name/address/EIN + amounts paid + reason (work/school) (email).")
    else:
        add_item(radar, "UNLIKELY", "Child & Dependent Care Credit",
                 "Not indicated.",
                 forms=["Form 2441"])

    # -------------------------
    # ACA Premium Tax Credit / 8962
    # -------------------------
    if marketplace is True:
        add_item(radar, "LIKELY", "Premium Tax Credit / ACA Reconciliation",
                 "Marketplace coverage indicated; 1095-A is required.",
                 forms=["Form 8962"])
        email_requests.append("Request 1095-A (Marketplace) (email).")
    else:
        add_item(radar, "UNLIKELY", "Premium Tax Credit / ACA",
                 "Not indicated.",
                 forms=["Form 8962"])

    # -------------------------
    # Education Credits (AOTC/LLC)
    # -------------------------
    if education is True:
        add_item(radar, "POSSIBLE", "Education Credit (AOTC / LLC)",
                 "Education indicated. Verify eligibility and qualified expenses.",
                 forms=["Form 8863"])
        email_requests.append("Request 1098-T + scholarships/grants + out-of-pocket expenses (email).")
    else:
        add_item(radar, "UNLIKELY", "Education Credits",
                 "Not indicated.",
                 forms=["Form 8863"])

    # -------------------------
    # Saver’s Credit
    # -------------------------
    if retirement_contrib is True:
        add_item(radar, "POSSIBLE", "Saver’s Credit / Retirement benefits",
                 "Retirement contributions indicated. Saver’s credit depends on AGI and filing status.",
                 forms=["Saver's Credit"])
        email_requests.append("Retirement contributions proof (IRA/401k) or W-2 retirement info (email).")
    else:
        add_item(radar, "UNLIKELY", "Saver’s Credit",
                 "Not indicated.",
                 forms=["Saver's Credit"])

    # -------------------------
    # HSA (8889)
    # -------------------------
    if hsa is True:
        add_item(radar, "POSSIBLE", "HSA deduction / distributions reporting",
                 "HSA activity indicated; may require Form 8889.",
                 forms=["Form 8889"])
        email_requests.append("Request HSA docs: 1099-SA and/or 5498-SA (email).")
    else:
        add_item(radar, "UNLIKELY", "HSA",
                 "Not indicated.",
                 forms=["Form 8889"])

    # -------------------------
    # Student Loan Interest (1098-E)
    # -------------------------
    if student_loan is True:
        add_item(radar, "POSSIBLE", "Student Loan Interest Deduction",
                 "Student loan interest indicated (income limits apply).",
                 forms=["1098-E"])
        email_requests.append("Request 1098-E (email).")
    else:
        add_item(radar, "UNLIKELY", "Student Loan Interest Deduction",
                 "Not indicated.",
                 forms=["1098-E"])

    # -------------------------
    # Schedule C / self-employment
    # -------------------------
    if self_employed is True or yn(a.get("has_1099_nec")) is True or yn(a.get("has_1099_k")) is True or yn(a.get("cash_income")) is True:
        add_item(radar, "LIKELY", "Schedule C (Self-employment)",
                 "Self-employment/1099/cash indicated. Expenses may reduce tax; confirm SE tax impact.",
                 forms=["Schedule C", "Schedule SE"])
        if business_expenses in (True, None):
            email_requests.append("Schedule C: income totals + expense categories (mileage, phone %, supplies, home office, etc.) (email).")
    else:
        add_item(radar, "UNLIKELY", "Schedule C",
                 "Not indicated.",
                 forms=["Schedule C"])

    # -------------------------
    # Itemized deductions (Schedule A)
    # -------------------------
    if any(x is True for x in [mortgage_1098, property_tax, charity, large_medical]):
        add_item(radar, "POSSIBLE", "Itemized Deductions (Schedule A)",
                 "Itemized signals present. Compare vs standard deduction.",
                 forms=["Schedule A"])
        email_requests.append("If itemizing: 1098 mortgage, property tax totals, charity receipts, medical totals (email).")
    else:
        add_item(radar, "UNLIKELY", "Itemized Deductions",
                 "No strong itemized signals.",
                 forms=["Schedule A"])

    # -------------------------
    # Multi-state
    # -------------------------
    if moved_states is True:
        add_item(radar, "POSSIBLE", "Multi-state / Part-year returns",
                 "Moved states indicated; may need part-year resident returns.",
                 forms=["State Returns"])
        email_requests.append("Move dates + state wage/withholding split (email).")
    else:
        add_item(radar, "UNLIKELY", "Multi-state",
                 "Not indicated.",
                 forms=["State Returns"])

    # -------------------------
    # Other compliance flags (not “refund” but critical)
    # -------------------------
    if unemployment is True:
        add_item(radar, "REVIEW", "Unemployment income",
                 "Unemployment indicated; ensure correct reporting and withholding.",
                 forms=["1099-G"])
        email_requests.append("Request 1099-G (email).")

    if crypto is True:
        add_item(radar, "REVIEW", "Crypto reporting",
                 "Crypto indicated; confirm whether taxable events occurred.",
                 forms=["Crypto"])
        email_requests.append("Crypto: exchange list + approximate activity (email). CSV can be requested later if needed.")

    if gambling is True:
        add_item(radar, "REVIEW", "Gambling income/losses",
                 "Gambling indicated; reporting and substantiation rules apply.",
                 forms=["W-2G", "Schedule A (losses if applicable)"])
        email_requests.append("Request W-2G + loss substantiation approach (email).")

    if foreign_accounts is True:
        add_item(radar, "REVIEW", "Foreign accounts awareness",
                 "Foreign accounts indicated; may have reporting requirements depending on thresholds.",
                 forms=["FBAR/FATCA (if applicable)"])
        email_requests.append("Foreign accounts: countries + max balances (email).")

    # Clean email requests
    email_requests = dedupe(email_requests)

    return radar, email_requests

def build_preparer_summary(full_name, year, answers, radar, email_requests):
    likely = [r["title"] for r in radar if r["level"] == "LIKELY"]
    possible = [r["title"] for r in radar if r["level"] == "POSSIBLE"]
    review = [r["title"] for r in radar if r["level"] == "REVIEW"]

    s = []
    s.append(f"CLIENT: {full_name} | YEAR: {year or '-'}")
    s.append("REFUND RADAR:")
    if likely:   s.append("  LIKELY:   " + ", ".join(likely))
    if possible: s.append("  POSSIBLE: " + ", ".join(possible))
    if review:   s.append("  REVIEW:   " + ", ".join(review))
    s.append("KEY NOTES (from client): " + (answers.get("client_note") or "-"))
    s.append("REQUEST VIA EMAIL (NO DOCS UPLOADED HERE):")
    if email_requests:
        for x in email_requests:
            s.append("  - " + x)
    else:
        s.append("  - None triggered")
    s.append("IMPORTANT: This is screening only. Verify eligibility with documents and IRS due diligence before filing.")
    return "\n".join(s)

# -------------------------
# HTML (single-file templates)
# -------------------------
BASE_HEAD = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<title>US Tax Deals Intake</title>
<style>
  .tiny { font-size: 0.88rem; }
  .badge-wide { padding: .45rem .6rem; }
</style>
</head>
<body class="bg-light">
<div class="container py-3" style="max-width: 980px;">
"""

BASE_FOOT = """
</div>
</body></html>
"""

INTAKE_HTML = BASE_HEAD + """
<div class="card shadow-sm">
  <div class="card-body">
    <h4 class="mb-1">Tax Intake (No SSN • No Document Uploads)</h4>
    <div class="text-muted tiny mb-3">
      Answer Yes/No/Not sure. This helps our preparers identify credits to maximize refund.
      If documents are needed (1095-A, 1098-T, etc.), we will request them by email.
    </div>

    {% if error %}<div class="alert alert-danger">{{ error }}</div>{% endif %}

    <form method="post" class="row g-2">
      <div class="col-12 col-md-6">
        <label class="form-label">Full Name *</label>
        <input name="full_name" class="form-control" required>
      </div>
      <div class="col-12 col-md-3">
        <label class="form-label">Tax Year</label>
        <input name="filing_year" class="form-control" placeholder="2025">
      </div>
      <div class="col-12 col-md-3">
        <label class="form-label">Phone</label>
        <input name="phone" class="form-control">
      </div>

      <div class="col-12">
        <label class="form-label">Email</label>
        <input name="email" class="form-control" placeholder="(for follow-up if documents needed)">
      </div>

      <hr class="my-2">

      <h6 class="mt-2">A) Basic</h6>
      <div class="col-12 col-md-4">
        <label class="form-label">Marital status (Dec 31)</label>
        <select name="marital_status" class="form-select">
          <option value="">Select</option>
          <option>Single</option><option>Married</option><option>Separated</option><option>Divorced</option><option>Widowed</option>
        </select>
      </div>
      <div class="col-12 col-md-4">
        <label class="form-label">Can someone claim you as dependent?</label>
        <select name="can_be_claimed" class="form-select">
          <option value="">Select</option><option>Yes</option><option>No</option><option>Not sure</option>
        </select>
      </div>
      <div class="col-12 col-md-4">
        <label class="form-label">Lived in U.S. at least 6 months?</label>
        <select name="lived_us_6mo" class="form-select">
          <option value="">Select</option><option>Yes</option><option>No</option><option>Not sure</option>
        </select>
      </div>

      <div class="col-12 col-md-6">
        <label class="form-label">Nonresident / Dual-status for the year?</label>
        <select name="nonresident_or_dual_status" class="form-select">
          <option value="">Select</option><option>No</option><option>Yes</option><option>Not sure</option>
        </select>
        <div class="text-muted tiny">This can affect credits like EITC.</div>
      </div>

      <hr class="my-2">

      <h6 class="mt-2">B) Dependents / Household (Big refund area)</h6>
      <div class="col-12 col-md-4">
        <label class="form-label">Do you have dependents you may claim?</label>
        <select name="has_dependents" class="form-select">
          <option value="">Select</option><option>Yes</option><option>No</option><option>Not sure</option>
        </select>
      </div>
      <div class="col-12 col-md-4">
        <label class="form-label">Did dependent(s) live with you > half year?</label>
        <select name="dep_lived_half_year" class="form-select">
          <option value="">Select</option><option>Yes</option><option>No</option><option>Not sure</option>
        </select>
      </div>
      <div class="col-12 col-md-4">
        <label class="form-label">Did you pay > half household costs?</label>
        <select name="paid_half_home" class="form-select">
          <option value="">Select</option><option>Yes</option><option>No</option><option>Not sure</option>
        </select>
      </div>

      <div class="col-12 col-md-4">
        <label class="form-label">Could someone else claim your child/dependent?</label>
        <select name="someone_else_claim_child" class="form-select">
          <option value="">Select</option><option>Yes</option><option>No</option><option>Not sure</option>
        </select>
      </div>
      <div class="col-12 col-md-4">
        <label class="form-label">Any custody agreement / 8332 possibility?</label>
        <select name="custody_agreement" class="form-select">
          <option value="">Select</option><option>Yes</option><option>No</option><option>Not sure</option>
        </select>
      </div>
      <div class="col-12 col-md-4">
        <label class="form-label">Did you provide > half dependent support?</label>
        <select name="you_provided_support" class="form-select">
          <option value="">Select</option><option>Yes</option><option>No</option><option>Not sure</option>
        </select>
      </div>

      <div class="col-12 col-md-6">
        <label class="form-label">Any dependent under 17 / under 19 / student under 24?</label>
        <select name="child_under_19_or_student" class="form-select">
          <option value="">Select</option><option>Yes</option><option>No</option><option>Not sure</option>
        </select>
      </div>

      <hr class="my-2">

      <h6 class="mt-2">C) Income Signals (for credits)</h6>
      {% for field,label in [
        ('has_w2','W-2 wages?'),
        ('has_1099_nec','1099-NEC contractor?'),
        ('has_1099_k','1099-K PayPal/Stripe/CashApp?'),
        ('cash_income','Any cash income not on forms?'),
        ('unemployment','Unemployment received?'),
        ('self_employed','Any side business/self-employed?'),
        ('business_expenses','If self-employed: any business expenses?'),
        ('investment_income_significant','Any interest/dividends/cap gains?'),
        ('investment_income_over_limit','Investment income may exceed EITC limits? (if known)'),
        ('crypto','Any crypto activity?'),
        ('gambling','Any gambling income?')
      ] %}
      <div class="col-12 col-md-4">
        <label class="form-label">{{ label }}</label>
        <select name="{{ field }}" class="form-select">
          <option value="">Select</option><option>Yes</option><option>No</option><option>Not sure</option>
        </select>
      </div>
      {% endfor %}

      <hr class="my-2">

      <h6 class="mt-2">D) Major Credits / Deductions</h6>
      {% for field,label in [
        ('childcare','Paid childcare so you can work/school?'),
        ('marketplace_1095a','Marketplace insurance (1095-A)?'),
        ('education_1098t','Education/college (1098-T)?'),
        ('retirement_contrib','Retirement contributions (IRA/401k)?'),
        ('hsa','HSA activity (contrib/distributions)?'),
        ('student_loan_interest','Student loan interest (1098-E)?'),
        ('moved_states','Moved states during the year?'),
        ('mortgage_1098','Mortgage interest (1098)?'),
        ('property_tax','Property taxes paid?'),
        ('charity','Large charitable donations?'),
        ('large_medical','Very large medical expenses?'),
        ('foreign_accounts','Foreign bank accounts/assets?')
      ] %}
      <div class="col-12 col-md-4">
        <label class="form-label">{{ label }}</label>
        <select name="{{ field }}" class="form-select">
          <option value="">Select</option><option>Yes</option><option>No</option><option>Not sure</option>
        </select>
      </div>
      {% endfor %}

      <div class="col-12 mt-2">
        <label class="form-label">Any short note to help maximize refund (optional)</label>
        <textarea name="client_note" rows="3" class="form-control" placeholder="Example: child lived with me, spouse separated, childcare paid cash, moved mid-year..."></textarea>
      </div>

      <div class="col-12 mt-3">
        <button class="btn btn-primary w-100">Submit</button>
        <div class="text-muted tiny mt-2">
          No SSN collected. No document uploads here. If needed, documents will be requested via email.
        </div>
      </div>
    </form>
  </div>
</div>
""" + BASE_FOOT

LOGIN_HTML = BASE_HEAD + """
<div class="card shadow-sm" style="max-width:420px;margin:0 auto;">
  <div class="card-body">
    <h4 class="mb-3">Preparer Login</h4>
    {% if error %}<div class="alert alert-danger">{{ error }}</div>{% endif %}
    <form method="post" class="d-grid gap-2">
      <input class="form-control" name="username" placeholder="Username" required>
      <input class="form-control" name="password" type="password" placeholder="Password" required>
      <button class="btn btn-primary">Login</button>
    </form>
  </div>
</div>
""" + BASE_FOOT

DASH_HTML = BASE_HEAD + """
<div class="d-flex justify-content-between align-items-center mb-2">
  <h4 class="mb-0">Preparer Dashboard</h4>
  <div class="d-flex gap-2">
    <a class="btn btn-outline-secondary btn-sm" href="/">Open Intake</a>
    <a class="btn btn-outline-danger btn-sm" href="/logout">Logout</a>
  </div>
</div>

{% if not items %}
  <div class="alert alert-info">No submissions yet.</div>
{% endif %}

{% for it in items %}
<div class="card shadow-sm mb-3">
  <div class="card-body">
    <div class="d-flex justify-content-between flex-wrap">
      <div>
        <h5 class="mb-1">{{ it.full_name }}</h5>
        <div class="text-muted tiny">
          ID #{{ it.id }} • Submitted {{ it.created_at }} • Year: {{ it.filing_year or "-" }} • Email: {{ it.email or "-" }} • Phone: {{ it.phone or "-" }}
        </div>
      </div>
    </div>

    <hr>

    <h6>Refund Radar (Might qualify)</h6>
    <div class="row">
      <div class="col-12 col-lg-7">
        {% for r in it.radar %}
          {% set badge = "secondary" %}
          {% if r.level == "LIKELY" %}{% set badge = "success" %}{% endif %}
          {% if r.level == "POSSIBLE" %}{% set badge = "warning" %}{% endif %}
          {% if r.level == "REVIEW" %}{% set badge = "info" %}{% endif %}
          {% if r.level == "UNLIKELY" %}{% set badge = "secondary" %}{% endif %}

          <div class="mb-2">
            <span class="badge text-bg-{{ badge }} badge-wide">{{ r.level }}</span>
            <b>{{ r.title }}</b>
            {% if r.forms and r.forms|length > 0 %}
              <span class="text-muted tiny">({{ r.forms|join(", ") }})</span>
            {% endif %}
            <div class="text-muted tiny">{{ r.why }}</div>
          </div>
        {% endfor %}
      </div>

      <div class="col-12 col-lg-5">
        <h6>Request via Email (no uploads here)</h6>
        <ul class="mb-0 tiny">
          {% for e in it.email_requests %}
            <li>{{ e }}</li>
          {% endfor %}
          {% if not it.email_requests %}
            <li class="text-muted">None triggered.</li>
          {% endif %}
        </ul>
      </div>
    </div>

    <hr>
    <h6>Preparer Summary (copy/paste)</h6>
    <textarea class="form-control" rows="7" id="sum-{{ it.id }}">{{ it.preparer_summary }}</textarea>
    <button class="btn btn-outline-primary btn-sm mt-2" onclick="copyIt('{{ it.id }}')">Copy Summary</button>

    <hr>
    <details>
      <summary class="text-primary">View client answers (raw)</summary>
      <pre class="small bg-white p-2 mt-2 border rounded">{{ it.answers | tojson(indent=2) }}</pre>
    </details>
  </div>
</div>
{% endfor %}

<script>
function copyIt(id){
  const el = document.getElementById("sum-" + id);
  el.select();
  el.setSelectionRange(0, 999999);
  document.execCommand("copy");
  alert("Copied ✅");
}
</script>
""" + BASE_FOOT

THANKYOU_HTML = BASE_HEAD + """
<div class="card shadow-sm">
  <div class="card-body">
    <h4>Thank you ✅</h4>
    <div class="text-muted">
      We received your intake details. If any document is needed, we’ll request it by email.
    </div>
    <a href="/" class="btn btn-primary mt-3">Submit another</a>
  </div>
</div>
""" + BASE_FOOT

# -------------------------
# Routes
# -------------------------
@app.route("/", methods=["GET","POST"])
def intake():
    if request.method == "POST":
        full_name = pick(request.form.get("full_name"))
        if not full_name:
            return render_template_string(INTAKE_HTML, error="Full name is required.")

        answers = dict(request.form)
        radar, email_requests = evaluate(answers)
        summary = build_preparer_summary(full_name, pick(answers.get("filing_year")), answers, radar, email_requests)

        con = db()
        con.execute("""
            INSERT INTO submissions (created_at, full_name, email, phone, filing_year, answers_json, radar_json, email_request_json, preparer_summary)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            datetime.utcnow().isoformat(),
            full_name,
            pick(answers.get("email")),
            pick(answers.get("phone")),
            pick(answers.get("filing_year")),
            json.dumps(answers),
            json.dumps(radar),
            json.dumps(email_requests),
            summary
        ))
        con.commit()
        con.close()
        return redirect("/thank-you")

    return render_template_string(INTAKE_HTML, error=None)

@app.route("/thank-you")
def thank_you():
    return render_template_string(THANKYOU_HTML)

@app.route("/login", methods=["GET","POST"])
def login():
    err = None
    if request.method == "POST":
        u = pick(request.form.get("username"))
        p = pick(request.form.get("password"))
        if u == DASH_USER and p == DASH_PASS:
            session["logged_in"] = True
            return redirect("/dashboard")
        err = "Invalid login."
    return render_template_string(LOGIN_HTML, error=err)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/dashboard")
def dashboard():
    if not session.get("logged_in"):
        return redirect("/login")

    con = db()
    rows = con.execute("SELECT * FROM submissions ORDER BY id DESC").fetchall()
    con.close()

    items = []
    for r in rows:
        answers = json.loads(r["answers_json"] or "{}")
        radar = json.loads(r["radar_json"] or "[]")
        email_requests = json.loads(r["email_request_json"] or "[]")
        items.append({
            "id": r["id"],
            "created_at": r["created_at"],
            "full_name": r["full_name"],
            "email": r["email"],
            "phone": r["phone"],
            "filing_year": r["filing_year"],
            "answers": answers,
            "radar": radar,
            "email_requests": email_requests,
            "preparer_summary": r["preparer_summary"] or ""
        })

    return render_template_string(DASH_HTML, items=items)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5050"))
    app.run(host="0.0.0.0", port=port, debug=False)

