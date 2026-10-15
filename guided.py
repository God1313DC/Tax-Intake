"""Guided intake: additive routes; no changes to historical submissions."""
import json
import os
import re
import secrets
import smtplib
import ssl
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from urllib.request import Request, urlopen
from flask import Blueprint, abort, current_app, jsonify, render_template, request, session

bp = Blueprint('guided', __name__)
SOURCES = {
    'individual': 'https://www.irs.gov/filing/gather-your-documents',
    'business': 'https://www.irs.gov/businesses/small-businesses-self-employed/what-kind-of-records-should-i-keep',
}
# Document collection guidance, not tax-year-specific eligibility determinations.
GUIDANCE_REVIEWED = '2026-10-15'
YESNO = ['Yes', 'No', 'Not sure']

def q(key, label, choices=None, when=None, help=''):
    return dict(key=key, label=label, choices=choices, when=when, help=help)

COMMON = [
    q('full_name', 'What is your full name?'),
    q('email', 'Which email can our team use to contact you?'),
    q('filing_year', 'Which tax year are you filing for?', ['2026', '2025', '2024', '2023', 'Other']),
    q('other_year', 'Enter the four-digit tax year.', when=['filing_year','Other']),
    q('states', 'Which states did you live in or do business in during that year?'),
]
INDIVIDUAL = [
    q('marital', 'What was your marital status on December 31?', ['Single','Married','Separated','Divorced','Widowed','Not sure']),
    q('residency', 'What was your U.S. tax residency status?', ['Resident all year','Nonresident','Dual-status','Not sure'], help='Immigration status and tax residency can differ. Select Not sure if you need help.'),
    q('visa', 'Which visa/status did you hold, and in which years were you present in the U.S.? Do not enter ID numbers.', when=['residency',['Nonresident','Dual-status','Not sure']]),
    q('dependents', 'Might you claim any children or other dependents?', YESNO),
    q('dependent_facts', 'For each possible dependent, give age, relationship, months living with you, student status, support details, and whether anyone else may claim them. No names or IDs needed.', when=['dependents',['Yes','Not sure']]),
    q('wages', 'Did you receive employee wages (W-2)?', YESNO),
    q('self_employed', 'Any freelance, gig, cash, or self-employment income?', YESNO),
    q('gig_details', 'What kind of work did you do, and did you track expenses or business mileage?', when=['self_employed','Yes']),
    q('investments', 'Any interest, dividends, stock sales, or digital asset transactions?', YESNO),
    q('retirement_income', 'Any retirement distributions, pension, or Social Security income?', YESNO),
    q('unemployment', 'Any unemployment or gambling income?', YESNO),
    q('rental', 'Any rental property income?', YESNO),
    q('education', 'Did you or a possible dependent have college education expenses?', YESNO),
    q('childcare', 'Did you pay care expenses so you or your spouse could work or look for work?', YESNO),
    q('marketplace', 'Did anyone on your return have Marketplace health insurance (1095-A)?', YESNO),
    q('hsa', 'Any HSA contributions or distributions?', YESNO),
    q('retirement', 'Did you contribute to an IRA or workplace retirement plan?', YESNO),
    q('deductions', 'Any mortgage interest, property taxes, donations, medical costs, or student loan interest?', YESNO),
    q('new_items', 'Any tips, overtime, vehicle purchases, home energy improvements, or other major changes?', YESNO),
    q('new_details', 'Describe the change and when it happened. Your preparer will check the tax-year rules.', when=['new_items','Yes']),
    q('foreign', 'Any foreign income, accounts, assets, or ownership interests?', YESNO),
    q('payments', 'Did you make estimated payments, file an extension, or receive tax notices?', YESNO),
]
BUSINESS = [
    q('business_name', 'What is the business name? Do not enter its EIN.'),
    q('entity', 'How is the business taxed?', ['Sole proprietor','Single-member LLC / disregarded','Partnership','S corporation','C corporation','Nonprofit','Not sure'], help='An LLC is a legal structure. Its federal tax treatment can differ.'),
    q('activity', 'Briefly describe what the business does.'),
    q('year_end', 'What is the fiscal year-end date (month/day)?'),
    q('owners', 'How many owners are there, and did ownership change during the year? No owner IDs needed.'),
    q('books', 'Are year-end bookkeeping records ready?', ['Yes','Partially','No','Not sure']),
    q('payroll', 'Did the business pay employees or owner wages?', YESNO),
    q('contractors', 'Did the business pay independent contractors?', YESNO),
    q('inventory', 'Did the business buy or sell inventory?', YESNO),
    q('assets', 'Any equipment, vehicles, property purchases, sales, or disposals?', YESNO),
    q('loans', 'Any business loans, owner contributions, distributions, or related-party transactions?', YESNO),
    q('foreign', 'Any foreign owners, accounts, income, or international transactions?', YESNO),
    q('multistate', 'Did the business operate, sell, employ people, or hold property in more than one state?', YESNO),
    q('payments', 'Any estimated tax payments, extensions, or IRS/state notices?', YESNO),
]
END = [q('notes', 'Anything else your preparer should know? Enter None if nothing else. Do not enter SSNs, EINs, bank numbers, or document contents.'),
       q('consent', 'May US Tax Deals save these answers and contact you about this intake?', ['I agree','I do not agree'])]

def questions(kind):
    return COMMON + (INDIVIDUAL if kind == 'individual' else BUSINESS) + END

def active_questions(kind, answers):
    out = []
    for item in questions(kind):
        when = item['when']
        if when:
            allowed = when[1] if isinstance(when[1], list) else [when[1]]
            if answers.get(when[0]) not in allowed:
                continue
        out.append(item)
    return out

def analyse(kind, a):
    source = SOURCES[kind]
    docs, flags = [], []
    def add(title, reason):
        docs.append(dict(title=title, reason=reason, source=source))
    add('Prior-year return and relevant tax notices', 'Helps your preparer reconcile prior information and carryovers.')
    if kind == 'individual':
        mapping = {
            'wages': ('W-2 forms', 'Employment income reported.'),
            'self_employed': ('Income records, 1099-NEC/1099-K if received, expense receipts and mileage logs', 'Self-employment activity reported; all income needs review, even without a form.'),
            'dependents': ('Dependent eligibility, residency, support and custody records', 'Possible dependents require separate eligibility checks.'),
            'investments': ('1099-INT, 1099-DIV, brokerage and digital asset transaction records as applicable', 'Investment or digital asset activity reported.'),
            'retirement_income': ('1099-R / SSA-1099 and distribution records as applicable', 'Retirement or Social Security income reported.'),
            'unemployment': ('1099-G / W-2G and supporting records as applicable', 'Unemployment or gambling activity reported.'),
            'rental': ('Rental income, expenses and depreciation history', 'Rental activity reported.'),
            'education': ('1098-T, tuition receipts, scholarship and grant records', 'Education expenses need reconciliation.'),
            'childcare': ('Care payment records and provider details through a secure channel', 'Work-related dependent care reported.'),
            'marketplace': ('1095-A for each Marketplace policy', 'Marketplace coverage needs reconciliation review.'),
            'hsa': ('1099-SA, 5498-SA and coverage/contribution records', 'HSA activity reported.'),
            'retirement': ('Retirement contribution records', 'Retirement contributions reported.'),
            'deductions': ('Relevant 1098/1098-E, property tax, donation and medical expense records', 'Potential adjustments or itemized deductions need review.'),
            'new_items': ('Dated supporting records for tips, overtime, purchases or improvements mentioned', 'Preparer must verify the applicable tax-year law and effective dates.'),
        }
        for key, (title, reason) in mapping.items():
            if a.get(key) == 'Yes': add(title, reason)
        if a.get('residency') != 'Resident all year':
            flags.append('Confirm tax residency, treaty eligibility and return type before assessing credits.')
        if a.get('dependents') == 'Yes': flags.append('Review each dependent separately; no dependency or credit eligibility has been determined.')
    else:
        add('Year-end profit and loss, balance sheet and general ledger', 'Core business bookkeeping for return preparation.')
        add('Business bank/card reconciliations and revenue/expense support', 'Supports completeness and classification of the books.')
        add('Formation documents, prior elections and ownership records', 'Confirm entity classification and applicable return.')
        mapping = {
            'payroll': ('Payroll summaries, W-2/W-3, 941/940 and state payroll records', 'Employee or owner compensation reported.'),
            'contractors': ('Contractor payment ledger and information-return records', 'Review reporting obligations; do not send W-9 IDs in this form.'),
            'inventory': ('Beginning/ending inventory and purchase records', 'Inventory activity reported.'),
            'assets': ('Asset register, purchase/sale records and depreciation schedules', 'Asset changes need tax-year-specific treatment.'),
            'loans': ('Loan statements, interest records and owner transaction/basis schedules', 'Financing and owner transactions reported.'),
            'multistate': ('Revenue, payroll and property by state, plus state filings', 'State nexus and apportionment require preparer review.'),
        }
        for key, (title, reason) in mapping.items():
            if a.get(key) == 'Yes': add(title, reason)
        flags.append('Confirm entity elections, fiscal year and ownership before selecting the return or due date.')
        if a.get('books') != 'Yes': flags.append('Bookkeeping completion or reconciliation may be needed before preparation.')
    if a.get('foreign') == 'Yes':
        add('Foreign income/account/ownership summaries through a secure channel', 'International reporting may apply; thresholds and exceptions need review.')
        flags.append('International tax specialist review recommended.')
    if a.get('payments') == 'Yes': add('Estimated payment confirmations, extensions and notices', 'Reconcile payments and correspondence.')
    for key, value in a.items():
        if value == 'Not sure': flags.append(f'Clarify: {key.replace("_", " ")}.')
    year = a.get('other_year') if a.get('filing_year') == 'Other' else a.get('filing_year')
    flags.append(f'Tax year {year}: verify current federal and state instructions before advice or filing. No refund or credit eligibility calculated.')
    return dict(documents=docs, review=flags, guidance_reviewed=GUIDANCE_REVIEWED,
                scope='Document collection guidance only; tax-year eligibility and state rules require preparer verification.')


def register(app, connection):
    bp.connection = connection
    with connection() as con:
        con.execute('''CREATE TABLE IF NOT EXISTS guided_submissions (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, kind TEXT NOT NULL,
            answers_json TEXT NOT NULL, analysis_json TEXT NOT NULL,
            email_status TEXT NOT NULL DEFAULT 'pending', email_attempts INTEGER NOT NULL DEFAULT 0)''')
    app.register_blueprint(bp)
    @app.cli.command('retry-intake-email')
    def retry():
        """Retry undelivered notifications; schedule this command periodically."""
        with connection() as con:
            ids = [r['id'] for r in con.execute("SELECT id FROM guided_submissions WHERE email_status != 'sent'")]
        for submission_id in ids:
            deliver(submission_id)
        print(f'Processed {len(ids)} pending notifications')


def csrf():
    if 'intake_csrf' not in session: session['intake_csrf'] = secrets.token_urlsafe(32)
    return session['intake_csrf']

@bp.get('/start')
def start():
    return render_template('guided.html', kind=None, config=None)

@bp.get('/intake/<kind>')
def guided_form(kind):
    if kind not in ('individual', 'business'): abort(404)
    return render_template('guided.html', kind=kind, config=dict(kind=kind, questions=questions(kind), csrf=csrf()))


def clean(kind, payload):
    if not isinstance(payload, dict): abort(400)
    values = payload.get('answers', {})
    if not isinstance(values, dict): abort(400)
    if not secrets.compare_digest(str(payload.get('csrf','')), str(session.get('intake_csrf','missing'))): abort(403)
    result = {}
    for item in active_questions(kind, values):
        value = values.get(item['key'])
        if not isinstance(value, str) or not value.strip() or len(value) > 1500: abort(400)
        value = value.strip()
        if item['choices'] and value not in item['choices']: abort(400)
        result[item['key']] = value
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', result.get('email','')): abort(400)
    if result.get('filing_year') == 'Other' and not re.fullmatch(r'(19|20)\d{2}', result.get('other_year','')): abort(400)
    if result.get('consent') != 'I agree': abort(400)
    return result

@bp.post('/api/intake/<kind>/submit')
def submit(kind):
    if kind not in ('individual','business'): abort(404)
    a = clean(kind, request.get_json(silent=True))
    token = str(request.headers.get('Idempotency-Key', ''))
    try: uuid.UUID(token)
    except (ValueError, AttributeError): abort(400)
    analysis = analyse(kind, a)
    # Same browser may safely retry after a timeout, without duplicate records/mail.
    owned = session.get('intake_ids', [])
    with bp.connection() as con:
        exists = con.execute('SELECT id FROM guided_submissions WHERE id=?', (token,)).fetchone()
        if exists and token not in owned: abort(409)
        if not exists:
            con.execute('INSERT INTO guided_submissions (id,created_at,kind,answers_json,analysis_json) VALUES (?,?,?,?,?)',
                        (token,datetime.now(timezone.utc).isoformat(),kind,json.dumps(a),json.dumps(analysis)))
    if token not in owned:
        session['intake_ids'] = (owned + [token])[-5:]
    deliver(token)
    return jsonify(id=token, analysis=analysis)


def deliver(submission_id):
    """Email contains a case reference, not the client's tax answers."""
    required = ['SMTP_HOST','SMTP_USER','SMTP_PASSWORD','MAIL_FROM','INTAKE_NOTIFY_TO','PUBLIC_BASE_URL']
    if not all(os.environ.get(k) for k in required): return False
    # Atomic claim avoids concurrent retries sending duplicates.
    with bp.connection() as con:
        claimed = con.execute("UPDATE guided_submissions SET email_status='sending', email_attempts=email_attempts+1 WHERE id=? AND email_status IN ('pending','failed')", (submission_id,)).rowcount
    if not claimed: return False
    try:
        base = os.environ['PUBLIC_BASE_URL'].rstrip('/')
        if not base.startswith('https://'): raise ValueError('HTTPS dashboard required')
        message = EmailMessage()
        message['Subject'] = 'New US Tax Deals intake submission'
        message['From'] = os.environ['MAIL_FROM']
        message['To'] = os.environ['INTAKE_NOTIFY_TO']
        message.set_content(f'A client completed a tax intake.\nReference: {submission_id}\nSign in to review answers and document checklist:\n{base}/intake-team\n')
        with smtplib.SMTP(os.environ['SMTP_HOST'], int(os.environ.get('SMTP_PORT','587')), timeout=8) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
            smtp.send_message(message)
        status = 'sent'
    except Exception:
        current_app.logger.warning('Intake notification delivery failed; details withheld')
        status = 'failed'
    with bp.connection() as con:
        con.execute('UPDATE guided_submissions SET email_status=? WHERE id=?', (status,submission_id))
    return status == 'sent'

@bp.get('/intake-team')
def team():
    if not session.get('logged_in'): return __import__('flask').redirect('/login')
    with bp.connection() as con:
        rows = con.execute('SELECT * FROM guided_submissions ORDER BY created_at DESC LIMIT 100').fetchall()
    items = [dict(r, answers=json.loads(r['answers_json']), analysis=json.loads(r['analysis_json'])) for r in rows]
    return render_template('guided_team.html', items=items)

@bp.post('/api/intake/explain')
def explain():
    """Optional model explains a fixed question; no client answers sent to the model."""
    payload = request.get_json(silent=True) or {}
    if not secrets.compare_digest(str(payload.get('csrf','')), str(session.get('intake_csrf','missing'))): abort(403)
    kind = payload.get('kind')
    if kind not in ('individual','business'): abort(400)
    question = next((x for x in questions(kind) if x['key'] == payload.get('key')), None)
    if not question: abort(400)
    fallback = question['help'] or 'This helps your preparer identify the records and follow-up information needed. Choose Not sure when available if you need help. Do not enter tax IDs or bank details.'
    endpoint, model = os.environ.get('OLLAMA_URL'), os.environ.get('OLLAMA_MODEL')
    if not endpoint or not model: return jsonify(text=fallback, mode='guided')
    try:
        data = json.dumps(dict(model=model, stream=False, messages=[
            dict(role='system',content='Explain this intake question in at most 60 plain-English words. Do not give eligibility, refund, tax-rate, deadline or legal advice. Do not request SSN, EIN, bank details, names or documents.'),
            dict(role='user', content=question['label'])], options=dict(num_predict=120))).encode()
        req = Request(endpoint.rstrip('/')+'/api/chat', data=data, headers={'Content-Type':'application/json'})
        with urlopen(req, timeout=10) as response: output = json.load(response)
        text = output['message']['content']
        if not isinstance(text,str) or not text.strip(): raise ValueError()
        return jsonify(text=text[:1500], mode='ai')
    except Exception:
        return jsonify(text=fallback, mode='guided')
