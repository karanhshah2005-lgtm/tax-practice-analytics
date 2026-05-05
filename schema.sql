-- =====================================================================
-- Tax Practice Analytics — Relational Schema
-- Synthetic data modeling a 35-client Canadian individual tax practice
-- =====================================================================

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS credits;
DROP TABLE IF EXISTS deductions;
DROP TABLE IF EXISTS income_items;
DROP TABLE IF EXISTS tax_returns;
DROP TABLE IF EXISTS clients;

-- ---------------------------------------------------------------------
-- clients : one row per client (anonymized — no names or SINs)
-- ---------------------------------------------------------------------
CREATE TABLE clients (
    client_id              TEXT PRIMARY KEY,        -- e.g. C-0001
    age_band               TEXT NOT NULL,           -- '<25','25-34','35-44','45-54','55-64','65+'
    marital_status         TEXT NOT NULL,           -- single|married|common-law|separated|widowed|divorced
    num_dependents         INTEGER NOT NULL DEFAULT 0,
    province               TEXT NOT NULL,           -- ON, QC, BC, AB, MB, NS
    occupation_category    TEXT NOT NULL,           -- employed|self_employed|retired|student|mixed|unemployed
    client_since_year      INTEGER NOT NULL,
    referral_source        TEXT NOT NULL            -- family|friend|social_media|walk_in|google|returning
);

-- ---------------------------------------------------------------------
-- tax_returns : one row per (client, tax_year)
-- ---------------------------------------------------------------------
CREATE TABLE tax_returns (
    return_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id              TEXT NOT NULL REFERENCES clients(client_id),
    tax_year               INTEGER NOT NULL,
    filing_status          TEXT NOT NULL,           -- on_time | late | extension
    filed_date             DATE NOT NULL,
    total_income           REAL NOT NULL,
    net_income             REAL NOT NULL,
    taxable_income         REAL NOT NULL,
    federal_tax            REAL NOT NULL,
    provincial_tax         REAL NOT NULL,
    cpp_contributions      REAL NOT NULL,
    ei_premiums            REAL NOT NULL,
    total_payable          REAL NOT NULL,           -- federal + provincial + CPP/EI - credits
    tax_withheld           REAL NOT NULL,           -- amount already paid via payroll/installments
    refund_or_owing        REAL NOT NULL,           -- positive = refund, negative = balance owing
    prep_fee               REAL NOT NULL,
    prep_minutes           INTEGER NOT NULL,
    complexity_score       INTEGER NOT NULL,        -- 1=simple T4, 5=multi-source self-employed
    UNIQUE(client_id, tax_year)
);

-- ---------------------------------------------------------------------
-- income_items : line-level income (T-slips, self-employment, rental, gains)
-- ---------------------------------------------------------------------
CREATE TABLE income_items (
    item_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    return_id              INTEGER NOT NULL REFERENCES tax_returns(return_id),
    slip_type              TEXT NOT NULL,           -- T4, T4A, T4A(P), T4A(OAS), T4E, T5, T3, T2125, Rental, CapitalGains
    amount                 REAL NOT NULL,
    issuer                 TEXT                     -- generic descriptor, e.g. 'Employer A'
);

-- ---------------------------------------------------------------------
-- deductions : line 20600–25600 of the T1
-- ---------------------------------------------------------------------
CREATE TABLE deductions (
    deduction_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    return_id              INTEGER NOT NULL REFERENCES tax_returns(return_id),
    deduction_type         TEXT NOT NULL,           -- RRSP, UnionDues, ChildCare, Moving, CarryingCharges,
                                                    -- EmploymentExpenses, BusinessExpenses, RentalExpenses, CapLossCarry
    amount                 REAL NOT NULL
);

-- ---------------------------------------------------------------------
-- credits : non-refundable + refundable
-- ---------------------------------------------------------------------
CREATE TABLE credits (
    credit_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    return_id              INTEGER NOT NULL REFERENCES tax_returns(return_id),
    credit_type            TEXT NOT NULL,           -- BasicPersonal, Spousal, EligibleDependant, AgeAmount,
                                                    -- DisabilityAmount, Tuition, MedicalExpenses, Charitable,
                                                    -- HomeBuyers, CanadaWorkersBenefit, CCB, GST_HST
    amount                 REAL NOT NULL,
    is_refundable          INTEGER NOT NULL DEFAULT 0   -- 0 = non-refundable, 1 = refundable
);

-- Indexes for analytical queries
CREATE INDEX idx_returns_year     ON tax_returns(tax_year);
CREATE INDEX idx_returns_client   ON tax_returns(client_id);
CREATE INDEX idx_income_return    ON income_items(return_id);
CREATE INDEX idx_income_slip      ON income_items(slip_type);
CREATE INDEX idx_ded_return       ON deductions(return_id);
CREATE INDEX idx_ded_type         ON deductions(deduction_type);
CREATE INDEX idx_credit_return    ON credits(return_id);
CREATE INDEX idx_credit_type      ON credits(credit_type);
