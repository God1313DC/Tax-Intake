import json

def yn(v):
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("yes","y","true","1"):
        return True
    if s in ("no","n","false","0"):
        return False
    return None

def add_flag(flags, level, title, why):
    flags.append({"level": level, "title": title, "why": why})

def dumps(x):
    return json.dumps(x, ensure_ascii=False)

def evaluate_answers(a: dict):
    flags = []
    req = []

    lived_us_6mo = yn(a.get("lived_us_6mo"))
    can_be_claimed = yn(a.get("can_be_claimed"))
    has_dependents = yn(a.get("has_dependents"))
    dep_lived_half = yn(a.get("dep_lived_half_year"))
    paid_half_home = yn(a.get("paid_half_home"))
    someone_else_claim = yn(a.get("someone_else_claim_child"))
    custody_agreement = yn(a.get("custody_agreement"))
    support_over_half = yn(a.get("you_provided_support"))
    child_age_signal = yn(a.get("child_under_19_or_student"))
    nonresident = yn(a.get("nonresident_or_dual_status"))
    investment_income_flag = yn(a.get("investment_income_over_limit"))

    marital = a.get("marital_status") or ""

    # Income signals
    earned_income_signal = any(
        yn(a.get(k)) is True for k in ["has_w2","has_1099_nec","has_1099_k","cash_income","self_employed"]
    )

    # -------------------------
    # EITC screening (no SSN collected)
    # -------------------------
    if nonresident is True:
        add_flag(flags, "UNLIKELY", "EITC",
                 "Nonresident/dual-status indicated — EITC often not allowed depending on status. Review residency rules.")
    else:
        if earned_income_signal and lived_us_6mo in (True, None) and can_be_claimed is not True:
            if has_dependents is True:
                # Strengthen with due diligence questions
                if someone_else_claim is True:
                    add_flag(flags, "POSSIBLE", "EITC (with qualifying child)",
                             "Earned income + dependents indicated, but another person may claim the child. Review tie-breaker rules.")
                    req += ["EITC QC due diligence via email: who may claim child, residency nights, relationship, support, and tie-breaker facts."]
                elif custody_agreement is True:
                    add_flag(flags, "POSSIBLE", "EITC (with qualifying child)",
                             "Custody/8332 possibility indicated. Review who can claim child and EITC rules.")
                    req += ["Custody/claiming verification via email: nights/residency + any 8332 release details."]
                elif dep_lived_half in (True, None):
                    add_flag(flags, "LIKELY", "EITC (with qualifying child)",
                             "Earned income + dependents + residency indicated. Verify QC tests, income limits, investment income limits.")
                    req += ["EITC QC due diligence via email: dependent relationship/residency/support + confirm no other claimant."]
                else:
                    add_flag(flags, "POSSIBLE", "EITC (with qualifying child)",
                             "Dependents indicated but residency > half year is No/uncertain. Verify qualifying child residency.")
                    req += ["EITC QC due diligence via email: residency nights, relationship, and support."]
            else:
                add_flag(flags, "POSSIBLE", "EITC (no qualifying child)",
                         "Earned income + residency indicated. Verify age/income/investment income limits.")
                req += ["EITC verification via email: age range + income range + investment income range."]
        else:
            add_flag(flags, "UNLIKELY", "EITC",
                     "Missing core signals: earned income, residency, or taxpayer may be claimable. Review if answers are uncertain.")

    # Investment income warning (applies to EITC)
    if investment_income_flag is True:
        add_flag(flags, "POSSIBLE", "EITC investment income limit risk",
                 "Client indicated significant investment income. Confirm investment income totals; may limit EITC.")
        req += ["Confirm investment income range via email (interest/dividends/cap gains)."]

    # -------------------------
    # Head of Household screening
    # -------------------------
    if (has_dependents is True) and (paid_half_home is True) and (marital.lower() not in ("married",)):
        if someone_else_claim is True:
            add_flag(flags, "POSSIBLE", "Head of Household",
                     "Paid > half home costs + dependents, but another person may claim dependent. Verify HOH qualifying person rules.")
            req += ["HOH verification via email: household costs + who qualifies as HOH dependent + who else may claim."]
        else:
            add_flag(flags, "POSSIBLE", "Head of Household",
                     "Dependents + paid > half home costs. Verify marital/separation rules and qualifying person.")
            req += ["HOH verification via email: rent/mortgage/utilities totals + who lived in home + marital separation facts."]
    else:
        add_flag(flags, "UNLIKELY", "Head of Household",
                 "Needs qualifying person + paid > half home costs + proper marital situation.")

    # -------------------------
    # Child Tax Credit / ODC / ACTC (screening)
    # -------------------------
    if has_dependents is True:
        if child_age_signal is True:
            add_flag(flags, "POSSIBLE", "Child Tax Credit / Additional CTC",
                     "Dependent age/student indicator suggests CTC/ACTC possible. Verify age/residency/support and refundable portion rules.")
        else:
            add_flag(flags, "POSSIBLE", "Other Dependent Credit (ODC)",
                     "Dependents indicated but age/student not confirmed. ODC may apply depending on dependent type.")
        req += ["Dependent verification via email: ages/student status, residency, relationship, and potential competing claimant."]
        if support_over_half is False:
            add_flag(flags, "POSSIBLE", "Dependent support risk",
                     "Client indicated they may NOT provide > half support. Confirm support facts; may affect dependent eligibility.")
            req += ["Support facts via email: who provided support, living arrangements, any shared support agreements."]
    else:
        add_flag(flags, "UNLIKELY", "Child-related credits",
                 "No dependents indicated.")

    # -------------------------
    # Self-employment / Schedule C
    # -------------------------
    se_signal = any(yn(a.get(k)) is True for k in ["self_employed","has_1099_nec","has_1099_k","cash_income"])
    if se_signal:
        add_flag(flags, "LIKELY", "Schedule C (Self-employment)",
                 "Self-employment/1099/cash indicated. Expenses can reduce tax; also check SE tax and credits impact.")
        if yn(a.get("business_expenses")) in (True, None):
            req += ["Schedule C via email: income totals + expense categories (mileage, phone %, supplies, home office, etc.)."]
    else:
        add_flag(flags, "UNLIKELY", "Schedule C",
                 "No self-employment/1099/cash income indicated.")

    # -------------------------
    # Other credits/deductions signals
    # -------------------------
    if yn(a.get("childcare")) is True:
        add_flag(flags, "POSSIBLE", "Child & Dependent Care Credit (Form 2441)",
                 "Childcare expenses indicated (if to work/school).")
        req += ["2441 via email: provider name/address/EIN + amounts paid + months + reason (work/school)."]
    if yn(a.get("marketplace_1095a")) is True:
        add_flag(flags, "LIKELY", "ACA / Premium Tax Credit (Form 8962)",
                 "Marketplace coverage indicated — 1095-A needed via email.")
        req += ["1095-A via email (Marketplace)."]
    if yn(a.get("education_1098t")) is True:
        add_flag(flags, "POSSIBLE", "Education credits (AOTC/LLC)",
                 "Education indicated; verify eligibility and qualified expenses.")
        req += ["1098-T + scholarships/grants + out-of-pocket expenses via email."]
    if yn(a.get("retirement_contrib")) is True:
        add_flag(flags, "POSSIBLE", "Saver’s Credit / retirement benefits",
                 "Retirement contributions indicated. Saver’s credit depends on AGI and filing status.")
        req += ["Retirement contribution proof via email (IRA/401k statements or W-2 retirement info)."]
    if yn(a.get("hsa")) is True:
        add_flag(flags, "POSSIBLE", "HSA (Form 8889)",
                 "HSA activity indicated; may need 1099-SA/5498-SA.")
        req += ["HSA forms via email (1099-SA / 5498-SA) if applicable."]
    if yn(a.get("student_loan_interest")) is True:
        add_flag(flags, "POSSIBLE", "Student Loan Interest Deduction",
                 "Student loan interest indicated (AGI limits apply).")
        req += ["1098-E via email."]

    # Itemized signals
    if any(yn(a.get(k)) is True for k in ["mortgage_1098","property_tax","charity","large_medical"]):
        add_flag(flags, "POSSIBLE", "Itemized deductions (Schedule A)",
                 "Itemized deduction signals present; compare vs standard deduction.")
        req += ["If itemizing: 1098 mortgage, property taxes, charity receipts, medical totals via email."]

    # Other alerts
    if yn(a.get("crypto")) is True:
        add_flag(flags, "POSSIBLE", "Crypto reporting",
                 "Crypto indicated. Confirm transactions; may require reporting.")
        req += ["Crypto details via email (exchange + approximate activity; CSV may be requested later)."]
    if yn(a.get("moved_states")) is True:
        add_flag(flags, "POSSIBLE", "Multi-state",
                 "Moved states indicated; may need part-year returns.")
        req += ["Move dates + state wage/withholding split via email."]
    if yn(a.get("unemployment")) is True:
        add_flag(flags, "POSSIBLE", "Unemployment (1099-G)",
                 "Unemployment indicated; ensure correct reporting.")
        req += ["1099-G via email."]
    if yn(a.get("gambling")) is True:
        add_flag(flags, "POSSIBLE", "Gambling",
                 "Gambling indicated. Confirm W-2G and loss substantiation if used.")
        req += ["W-2G via email."]
    if yn(a.get("foreign_accounts")) is True:
        add_flag(flags, "POSSIBLE", "Foreign accounts awareness",
                 "Foreign account indicated. Confirm thresholds and reporting requirements.")
        req += ["Foreign accounts details via email (country + max balances)."]

    # Deduplicate req list
    req = list(dict.fromkeys(req))
    return flags, req
