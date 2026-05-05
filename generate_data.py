"""
generate_data.py
================
Populates tax_practice.db with synthetic but realistic data for a
Canadian individual tax preparation practice (~35-40 clients, 3 tax years).

All clients, employers, and amounts are fabricated — no real PII.

Distributions are calibrated to roughly match Canadian household income
profiles and CRA-published claim frequencies for common deductions/credits.

Usage:
    python generate_data.py
"""

import sqlite3
import random
import os
from datetime import date, timedelta
from pathlib import Path

# Deterministic output for reproducible portfolio screenshots
random.seed(42)

DB_PATH = Path(__file__).parent / "tax_practice.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# --------------------------------------------------------------------- #
# Configuration                                                          #
# --------------------------------------------------------------------- #
TAX_YEARS = [2022, 2023, 2024]
N_CLIENTS = 38

# 2024 federal brackets (used as a single approximation for all years)
FED_BRACKETS = [(55867, 0.15), (111733, 0.205), (173205, 0.26),
                (246752, 0.29), (float("inf"), 0.33)]

# 2024 Ontario brackets
ON_BRACKETS = [(51446, 0.0505), (102894, 0.0915), (150000, 0.1116),
               (220000, 0.1216), (float("inf"), 0.1316)]

# Province multipliers for non-Ontario clients (rough effective-rate proxy)
PROV_MULT = {"ON": 1.00, "QC": 1.20, "BC": 0.92, "AB": 0.85, "MB": 1.05, "NS": 1.10}

BASIC_FED = 15000   # rounded basic personal amount (avg across years)
BASIC_PROV = 12000

PROVINCES = ["ON", "ON", "ON", "ON", "ON", "ON", "ON",   # ~70% Ontario
             "QC", "BC", "AB", "MB", "NS"]

REFERRAL_SOURCES = ["family", "friend", "social_media", "walk_in",
                    "google", "returning"]

OCCUPATION_CATEGORIES = ["employed", "employed", "employed", "employed",
                        "self_employed", "self_employed",
                        "retired", "retired",
                        "student",
                        "mixed",
                        "unemployed"]

EMPLOYER_POOL = ["TechCo Inc", "Northern Logistics", "Riverside Hospital",
                 "Maple Retail Group", "City Public Service", "Ottawa Schools Board",
                 "BlueWave Consulting", "GoldStar Manufacturing", "PineHill Bank",
                 "Capital Communications", "Crown Properties", "MedRx Pharmacy"]


def tier_tax(amount: float, brackets) -> float:
    """Apply a tiered tax-bracket schedule."""
    if amount <= 0:
        return 0.0
    tax = 0.0
    prev = 0.0
    for limit, rate in brackets:
        chunk = min(amount, limit) - prev
        if chunk > 0:
            tax += chunk * rate
        prev = limit
        if amount <= limit:
            break
    return tax


def generate_client(idx: int) -> dict:
    """Fabricate one client profile."""
    age_band = random.choices(
        ["<25", "25-34", "35-44", "45-54", "55-64", "65+"],
        weights=[8, 25, 25, 18, 14, 10]
    )[0]

    marital = random.choices(
        ["single", "married", "common-law", "separated", "widowed", "divorced"],
        weights=[35, 35, 15, 5, 4, 6]
    )[0]

    # Dependents correlate with marital status & age
    if age_band in ("<25",):
        deps = 0
    elif marital in ("married", "common-law") and age_band in ("25-34", "35-44", "45-54"):
        deps = random.choices([0, 1, 2, 3], weights=[20, 30, 35, 15])[0]
    elif marital in ("separated", "divorced", "widowed"):
        deps = random.choices([0, 1, 2], weights=[40, 35, 25])[0]
    else:
        deps = random.choices([0, 1, 2], weights=[70, 20, 10])[0]

    province = random.choice(PROVINCES)

    # Occupation correlates with age
    if age_band == "<25":
        occ = random.choices(["student", "employed", "mixed"], weights=[55, 35, 10])[0]
    elif age_band == "65+":
        occ = random.choices(["retired", "employed", "self_employed"], weights=[70, 15, 15])[0]
    else:
        occ = random.choice(OCCUPATION_CATEGORIES)

    # Acquisition curve — practice has been growing
    client_since_year = random.choices(
        [2020, 2021, 2022, 2023, 2024],
        weights=[5, 10, 25, 35, 25]
    )[0]

    # New clients more likely from social/google; older from family/referral
    if client_since_year >= 2023:
        ref = random.choices(REFERRAL_SOURCES, weights=[15, 20, 25, 10, 25, 5])[0]
    else:
        ref = random.choices(REFERRAL_SOURCES, weights=[35, 25, 10, 15, 5, 10])[0]

    return {
        "client_id": f"C-{idx:04d}",
        "age_band": age_band,
        "marital_status": marital,
        "num_dependents": deps,
        "province": province,
        "occupation_category": occ,
        "client_since_year": client_since_year,
        "referral_source": ref,
    }


def generate_income_items(client: dict, year: int) -> list[tuple[str, float, str | None]]:
    """Generate income slips for one client-year. Returns list of (slip_type, amount, issuer)."""
    items = []
    occ = client["occupation_category"]
    age = client["age_band"]

    # T4 employment income
    if occ in ("employed", "mixed"):
        # Log-normalish — base salary varies by age band
        base = {
            "<25": 32000, "25-34": 58000, "35-44": 78000,
            "45-54": 92000, "55-64": 86000, "65+": 45000
        }[age]
        # Annual growth
        year_mult = 1.0 + 0.03 * (year - 2022)
        salary = max(15000, random.gauss(base * year_mult, base * 0.30))
        items.append(("T4", round(salary, 2), random.choice(EMPLOYER_POOL)))

        # Some clients have a secondary T4 (job change or 2nd job)
        if random.random() < 0.18:
            items.append(("T4", round(random.uniform(4000, 22000), 2),
                         random.choice(EMPLOYER_POOL)))

    if occ == "self_employed" or (occ == "mixed" and random.random() < 0.7):
        # T2125 self-employment net income (gross less expenses)
        gross = random.uniform(35000, 180000) * (1.0 + 0.04 * (year - 2022))
        items.append(("T2125", round(gross, 2), "Self-Employed"))

    if occ == "retired":
        # CPP, OAS, RRIF/private pension
        items.append(("T4A(P)", round(random.uniform(8000, 16500), 2), "Service Canada"))
        items.append(("T4A(OAS)", round(random.uniform(7000, 8400), 2), "Service Canada"))
        if random.random() < 0.6:
            items.append(("T4A", round(random.uniform(8000, 60000), 2), "Pension Plan"))

    if occ == "student":
        # Part-time T4 + maybe T4A scholarship
        items.append(("T4", round(random.uniform(6000, 22000), 2),
                     random.choice(EMPLOYER_POOL)))
        if random.random() < 0.4:
            items.append(("T4A", round(random.uniform(1500, 9000), 2), "University"))

    if occ == "unemployed":
        if random.random() < 0.7:
            items.append(("T4E", round(random.uniform(8000, 22000), 2), "Service Canada"))

    # Investment income — ~35% of clients
    if random.random() < 0.35:
        items.append(("T5", round(random.uniform(120, 8500), 2), "Bank Interest/Div"))
    if random.random() < 0.18:
        items.append(("T3", round(random.uniform(200, 12000), 2), "Trust/ETF"))

    # Capital gains — ~20% of clients
    if random.random() < 0.20:
        gain = random.uniform(-4000, 35000)  # can be a loss
        items.append(("CapitalGains", round(gain, 2), "Brokerage"))

    # Rental — ~8% of clients
    if random.random() < 0.08:
        items.append(("Rental", round(random.uniform(8000, 32000), 2), "Rental Property"))

    return items


def generate_deductions(client: dict, total_income: float, has_business: bool, has_rental: bool,
                       year: int) -> list[tuple[str, float]]:
    """Returns list of (deduction_type, amount)."""
    out = []
    occ = client["occupation_category"]
    deps = client["num_dependents"]

    # RRSP — ~55% contribute, more likely with higher income
    rrsp_prob = min(0.85, 0.20 + total_income / 200000)
    if random.random() < rrsp_prob and occ != "retired":
        room = min(total_income * 0.18, 31560)  # 2024 limit
        contrib = random.uniform(0.05, 0.95) * room
        if contrib > 500:
            out.append(("RRSP", round(contrib, 2)))

    # Union/Professional dues — employed clients
    if occ in ("employed", "mixed") and random.random() < 0.30:
        out.append(("UnionDues", round(random.uniform(200, 1800), 2)))

    # Childcare — only if dependents
    if deps > 0 and random.random() < 0.55:
        max_per_child = 8000 if deps >= 2 else 5000
        out.append(("ChildCare", round(random.uniform(2000, max_per_child * deps), 2)))

    # Moving expenses — rare
    if random.random() < 0.04:
        out.append(("Moving", round(random.uniform(800, 6500), 2)))

    # Carrying charges — investors
    if random.random() < 0.15:
        out.append(("CarryingCharges", round(random.uniform(80, 1200), 2)))

    # Employment expenses (T2200) — rare
    if occ in ("employed", "mixed") and random.random() < 0.08:
        out.append(("EmploymentExpenses", round(random.uniform(500, 5500), 2)))

    # Business expenses — if T2125 income
    if has_business:
        out.append(("BusinessExpenses", round(random.uniform(8000, 45000), 2)))

    # Rental expenses
    if has_rental:
        out.append(("RentalExpenses", round(random.uniform(3000, 18000), 2)))

    # Capital loss carry-forward — rare
    if random.random() < 0.05:
        out.append(("CapLossCarry", round(random.uniform(500, 6000), 2)))

    return out


def generate_credits(client: dict, taxable_income: float, year: int) -> list[tuple[str, float, int]]:
    """Returns list of (credit_type, amount, is_refundable)."""
    out = []

    # Basic personal amount — everyone
    out.append(("BasicPersonal", BASIC_FED, 0))

    # Spousal — married/common-law with potentially low-income spouse
    if client["marital_status"] in ("married", "common-law") and random.random() < 0.35:
        out.append(("Spousal", round(random.uniform(2000, 14000), 2), 0))

    # Eligible dependant — single parents
    if (client["marital_status"] in ("separated", "divorced", "widowed", "single")
            and client["num_dependents"] >= 1 and random.random() < 0.7):
        out.append(("EligibleDependant", round(random.uniform(8000, 14000), 2), 0))

    # Age amount — 65+
    if client["age_band"] == "65+":
        out.append(("AgeAmount", round(random.uniform(4500, 8400), 2), 0))

    # Disability — ~6%
    if random.random() < 0.06:
        out.append(("DisabilityAmount", round(random.uniform(8000, 9500), 2), 0))

    # Tuition — students
    if client["occupation_category"] == "student" or client["age_band"] == "<25":
        if random.random() < 0.7:
            out.append(("Tuition", round(random.uniform(2500, 12000), 2), 0))

    # Medical — ~40%
    if random.random() < 0.40:
        out.append(("MedicalExpenses", round(random.uniform(200, 6500), 2), 0))

    # Charitable — ~50%
    if random.random() < 0.50:
        out.append(("Charitable", round(random.uniform(50, 2200), 2), 0))

    # Home buyers — rare
    if random.random() < 0.04:
        out.append(("HomeBuyers", 10000.00, 0))

    # Canada Workers Benefit — refundable, low-income
    if taxable_income < 35000 and taxable_income > 5000 and random.random() < 0.5:
        out.append(("CanadaWorkersBenefit", round(random.uniform(200, 1400), 2), 1))

    # CCB — refundable, with kids (technically not on T1 but tracked)
    if client["num_dependents"] > 0 and random.random() < 0.7:
        per_child = random.uniform(1500, 7400)
        out.append(("CCB", round(per_child * client["num_dependents"], 2), 1))

    # GST/HST — refundable, low-income
    if taxable_income < 50000 and random.random() < 0.6:
        out.append(("GST_HST", round(random.uniform(150, 700), 2), 1))

    return out


def compute_taxes(total_income: float, deduction_total: float, credit_nonref_total: float,
                  province: str) -> dict:
    """Approximate federal + provincial tax."""
    net_income = max(0, total_income - deduction_total)
    taxable = net_income  # simplified — net = taxable for our purposes

    fed_tax_gross = tier_tax(taxable, FED_BRACKETS)
    prov_tax_gross = tier_tax(taxable, ON_BRACKETS) * PROV_MULT.get(province, 1.0)

    # Non-refundable credits reduce tax at 15% federal / 5.05% provincial
    fed_credit = credit_nonref_total * 0.15
    prov_credit = credit_nonref_total * 0.0505

    fed_tax = max(0, fed_tax_gross - fed_credit)
    prov_tax = max(0, prov_tax_gross - prov_credit)

    # CPP/EI on employment income — simplified flat % on income up to cap
    cpp = min(taxable, 68500) * 0.0595 if taxable > 3500 else 0
    ei = min(taxable, 63200) * 0.0166 if taxable > 0 else 0

    return {
        "net_income": round(net_income, 2),
        "taxable_income": round(taxable, 2),
        "federal_tax": round(fed_tax, 2),
        "provincial_tax": round(prov_tax, 2),
        "cpp_contributions": round(cpp, 2),
        "ei_premiums": round(ei, 2),
    }


def generate_return(client: dict, year: int) -> dict:
    """Generate a complete return for one client-year."""
    income_items = generate_income_items(client, year)
    total_income = sum(amt for _, amt, _ in income_items)

    has_business = any(s == "T2125" for s, _, _ in income_items)
    has_rental = any(s == "Rental" for s, _, _ in income_items)

    deductions = generate_deductions(client, total_income, has_business, has_rental, year)
    deduction_total = sum(amt for _, amt in deductions)

    # Credits depend on taxable income, which depends on deductions
    taxable_estimate = max(0, total_income - deduction_total)
    credits_data = generate_credits(client, taxable_estimate, year)
    credit_nonref_total = sum(amt for t, amt, refundable in credits_data if not refundable)
    credit_ref_total = sum(amt for t, amt, refundable in credits_data if refundable)

    tx = compute_taxes(total_income, deduction_total, credit_nonref_total, client["province"])

    total_payable = (tx["federal_tax"] + tx["provincial_tax"]
                     + tx["cpp_contributions"] + tx["ei_premiums"])

    # Tax already withheld via payroll — typically ~85-110% of liability for employed
    occ = client["occupation_category"]
    if occ in ("employed", "retired"):
        withheld = total_payable * random.uniform(0.92, 1.18)
    elif occ == "self_employed":
        withheld = total_payable * random.uniform(0.50, 0.95)
    else:
        withheld = total_payable * random.uniform(0.70, 1.10)

    refund = round(withheld - total_payable + credit_ref_total, 2)

    # Filing status & date
    deadline = date(year + 1, 4, 30)
    se_deadline = date(year + 1, 6, 15)
    filing_status = random.choices(["on_time", "late", "extension"],
                                   weights=[80, 15, 5])[0]
    if filing_status == "on_time":
        filed = deadline - timedelta(days=random.randint(0, 75))
    elif filing_status == "extension" and has_business:
        filed = se_deadline - timedelta(days=random.randint(0, 30))
    else:  # late
        filed = deadline + timedelta(days=random.randint(7, 180))

    # Complexity & fee
    complexity = 1
    if has_business: complexity += 2
    if has_rental: complexity += 1
    if any(s in ("T5", "T3", "CapitalGains") for s, _, _ in income_items): complexity += 1
    complexity = min(5, complexity)

    base_fee = {1: 90, 2: 140, 3: 200, 4: 280, 5: 380}[complexity]
    fee_growth = 1.0 + 0.06 * (year - 2022)  # he's raising prices yearly
    prep_fee = round(base_fee * fee_growth * random.uniform(0.92, 1.10), 2)
    prep_minutes = complexity * random.randint(20, 45) + random.randint(15, 30)

    return {
        "income_items": income_items,
        "deductions": deductions,
        "credits": credits_data,
        "summary": {
            "tax_year": year,
            "filing_status": filing_status,
            "filed_date": filed.isoformat(),
            "total_income": round(total_income, 2),
            **tx,
            "total_payable": round(total_payable, 2),
            "tax_withheld": round(withheld, 2),
            "refund_or_owing": refund,
            "prep_fee": prep_fee,
            "prep_minutes": prep_minutes,
            "complexity_score": complexity,
        }
    }


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Apply schema
    with open(SCHEMA_PATH, "r") as f:
        cur.executescript(f.read())

    # Generate clients
    clients = [generate_client(i + 1) for i in range(N_CLIENTS)]
    for c in clients:
        cur.execute("""
            INSERT INTO clients VALUES (?,?,?,?,?,?,?,?)
        """, (c["client_id"], c["age_band"], c["marital_status"], c["num_dependents"],
              c["province"], c["occupation_category"], c["client_since_year"],
              c["referral_source"]))

    # Generate returns
    n_returns = 0
    for c in clients:
        for year in TAX_YEARS:
            if year < c["client_since_year"]:
                continue
            r = generate_return(c, year)
            s = r["summary"]
            cur.execute("""
                INSERT INTO tax_returns
                (client_id, tax_year, filing_status, filed_date, total_income, net_income,
                 taxable_income, federal_tax, provincial_tax, cpp_contributions, ei_premiums,
                 total_payable, tax_withheld, refund_or_owing, prep_fee, prep_minutes,
                 complexity_score)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (c["client_id"], s["tax_year"], s["filing_status"], s["filed_date"],
                  s["total_income"], s["net_income"], s["taxable_income"],
                  s["federal_tax"], s["provincial_tax"], s["cpp_contributions"],
                  s["ei_premiums"], s["total_payable"], s["tax_withheld"],
                  s["refund_or_owing"], s["prep_fee"], s["prep_minutes"],
                  s["complexity_score"]))
            return_id = cur.lastrowid

            for slip, amt, issuer in r["income_items"]:
                cur.execute("INSERT INTO income_items (return_id, slip_type, amount, issuer) "
                            "VALUES (?,?,?,?)", (return_id, slip, amt, issuer))
            for ded_type, amt in r["deductions"]:
                cur.execute("INSERT INTO deductions (return_id, deduction_type, amount) "
                            "VALUES (?,?,?)", (return_id, ded_type, amt))
            for cr_type, amt, refundable in r["credits"]:
                cur.execute("INSERT INTO credits (return_id, credit_type, amount, is_refundable) "
                            "VALUES (?,?,?,?)", (return_id, cr_type, amt, refundable))

            n_returns += 1

    conn.commit()
    conn.close()

    print(f"✓ Generated {len(clients)} clients, {n_returns} returns")
    print(f"✓ Database: {DB_PATH}  ({DB_PATH.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
