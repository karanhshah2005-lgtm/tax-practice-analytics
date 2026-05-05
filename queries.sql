-- =====================================================================
-- queries.sql  —  Analytical SQL for the tax practice
-- Each section is delimited by  -- @name <query_name>  for the runner.
-- =====================================================================


-- @name practice_kpis
-- Headline KPIs across all years
WITH stats AS (
    SELECT
        COUNT(DISTINCT client_id)                    AS lifetime_clients,
        COUNT(*)                                     AS total_returns,
        ROUND(SUM(prep_fee), 2)                      AS lifetime_revenue,
        ROUND(AVG(prep_fee), 2)                      AS avg_fee_per_return,
        ROUND(AVG(complexity_score), 2)              AS avg_complexity,
        ROUND(AVG(refund_or_owing), 2)               AS avg_refund,
        ROUND(AVG(prep_minutes), 0)                  AS avg_minutes,
        ROUND(SUM(prep_fee) * 1.0 / SUM(prep_minutes) * 60, 2) AS effective_hourly_rate
    FROM tax_returns
)
SELECT * FROM stats;


-- @name yoy_growth
-- Year-over-year practice growth: clients, returns, revenue, avg fee
WITH yearly AS (
    SELECT
        tax_year,
        COUNT(DISTINCT client_id) AS clients_served,
        COUNT(*)                  AS returns_filed,
        ROUND(SUM(prep_fee), 2)   AS revenue,
        ROUND(AVG(prep_fee), 2)   AS avg_fee,
        ROUND(AVG(complexity_score), 2) AS avg_complexity
    FROM tax_returns
    GROUP BY tax_year
)
SELECT
    tax_year,
    clients_served,
    returns_filed,
    revenue,
    avg_fee,
    avg_complexity,
    ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY tax_year))
                / NULLIF(LAG(revenue) OVER (ORDER BY tax_year), 0), 1) AS revenue_growth_pct,
    ROUND(100.0 * (clients_served - LAG(clients_served) OVER (ORDER BY tax_year))
                / NULLIF(LAG(clients_served) OVER (ORDER BY tax_year), 0), 1) AS client_growth_pct
FROM yearly
ORDER BY tax_year;


-- @name income_distribution
-- Income percentiles by year — quartile-style approximation in SQLite
WITH ranked AS (
    SELECT tax_year, total_income,
           NTILE(4) OVER (PARTITION BY tax_year ORDER BY total_income) AS quartile
    FROM tax_returns
)
SELECT
    tax_year,
    ROUND(MIN(total_income), 0)            AS min_income,
    ROUND(MAX(CASE WHEN quartile <= 1 THEN total_income END), 0) AS p25,
    ROUND(MAX(CASE WHEN quartile <= 2 THEN total_income END), 0) AS median,
    ROUND(MAX(CASE WHEN quartile <= 3 THEN total_income END), 0) AS p75,
    ROUND(MAX(total_income), 0)            AS max_income,
    ROUND(AVG(total_income), 0)            AS mean_income
FROM ranked
GROUP BY tax_year
ORDER BY tax_year;


-- @name top_deductions
-- Most commonly claimed deductions: claim rate, avg amount, total $ deducted
WITH base AS (
    SELECT COUNT(*) AS n_returns FROM tax_returns
)
SELECT
    d.deduction_type,
    COUNT(DISTINCT d.return_id)                          AS returns_with_claim,
    ROUND(100.0 * COUNT(DISTINCT d.return_id) / b.n_returns, 1) AS claim_rate_pct,
    ROUND(AVG(d.amount), 2)                              AS avg_amount,
    ROUND(SUM(d.amount), 2)                              AS total_claimed
FROM deductions d, base b
GROUP BY d.deduction_type, b.n_returns
ORDER BY total_claimed DESC;


-- @name top_credits
-- Most claimed credits, separated refundable vs non-refundable
WITH base AS (SELECT COUNT(*) AS n_returns FROM tax_returns)
SELECT
    c.credit_type,
    CASE c.is_refundable WHEN 1 THEN 'refundable' ELSE 'non-refundable' END AS kind,
    COUNT(DISTINCT c.return_id)                          AS returns_with_claim,
    ROUND(100.0 * COUNT(DISTINCT c.return_id) / b.n_returns, 1) AS claim_rate_pct,
    ROUND(AVG(c.amount), 2)                              AS avg_amount,
    ROUND(SUM(c.amount), 2)                              AS total_claimed
FROM credits c, base b
GROUP BY c.credit_type, c.is_refundable, b.n_returns
ORDER BY total_claimed DESC;


-- @name slip_type_mix
-- Income source mix: what slips show up most often, what they pay
SELECT
    i.slip_type,
    COUNT(DISTINCT i.return_id)                          AS returns_with_slip,
    ROUND(AVG(i.amount), 2)                              AS avg_amount,
    ROUND(SUM(i.amount), 2)                              AS total_amount
FROM income_items i
GROUP BY i.slip_type
ORDER BY returns_with_slip DESC;


-- @name self_employment_growth
-- Track the rise of self-employed / gig clients
WITH se AS (
    SELECT DISTINCT return_id FROM income_items WHERE slip_type = 'T2125'
)
SELECT
    r.tax_year,
    COUNT(DISTINCT r.return_id)                          AS total_returns,
    COUNT(DISTINCT se.return_id)                         AS se_returns,
    ROUND(100.0 * COUNT(DISTINCT se.return_id)
                 / COUNT(DISTINCT r.return_id), 1)       AS se_share_pct
FROM tax_returns r
LEFT JOIN se USING (return_id)
GROUP BY r.tax_year
ORDER BY r.tax_year;


-- @name filing_timeliness
-- Are we filing on time? Break down by occupation
SELECT
    c.occupation_category,
    COUNT(*)                                             AS returns,
    SUM(CASE WHEN r.filing_status = 'on_time'  THEN 1 ELSE 0 END) AS on_time,
    SUM(CASE WHEN r.filing_status = 'late'     THEN 1 ELSE 0 END) AS late,
    SUM(CASE WHEN r.filing_status = 'extension' THEN 1 ELSE 0 END) AS extension,
    ROUND(100.0 * SUM(CASE WHEN r.filing_status = 'late' THEN 1 ELSE 0 END)
                / COUNT(*), 1)                            AS late_pct
FROM tax_returns r
JOIN clients c USING (client_id)
GROUP BY c.occupation_category
ORDER BY late_pct DESC;


-- @name complexity_vs_fee
-- Pricing alignment: avg fee per complexity tier
SELECT
    complexity_score,
    COUNT(*)                                             AS returns,
    ROUND(AVG(prep_fee), 2)                              AS avg_fee,
    ROUND(MIN(prep_fee), 2)                              AS min_fee,
    ROUND(MAX(prep_fee), 2)                              AS max_fee,
    ROUND(AVG(prep_minutes), 0)                          AS avg_minutes,
    ROUND(AVG(prep_fee) * 60.0 / AVG(prep_minutes), 2)   AS effective_hourly
FROM tax_returns
GROUP BY complexity_score
ORDER BY complexity_score;


-- @name client_retention
-- Cohort retention: of clients acquired in year X, how many filed each year?
WITH cohort_returns AS (
    SELECT
        c.client_since_year                  AS cohort,
        r.tax_year,
        COUNT(DISTINCT r.client_id)          AS active_clients
    FROM clients c
    JOIN tax_returns r USING (client_id)
    GROUP BY c.client_since_year, r.tax_year
),
cohort_size AS (
    SELECT client_since_year AS cohort, COUNT(*) AS cohort_size
    FROM clients
    GROUP BY client_since_year
)
SELECT
    cr.cohort,
    cs.cohort_size,
    cr.tax_year,
    cr.active_clients,
    ROUND(100.0 * cr.active_clients / cs.cohort_size, 1) AS retention_pct
FROM cohort_returns cr
JOIN cohort_size cs USING (cohort)
ORDER BY cr.cohort, cr.tax_year;


-- @name referral_source_value
-- Which acquisition channels bring the most valuable clients (lifetime fees)?
SELECT
    c.referral_source,
    COUNT(DISTINCT c.client_id)                          AS clients,
    COUNT(r.return_id)                                   AS returns_filed,
    ROUND(SUM(r.prep_fee), 2)                            AS lifetime_revenue,
    ROUND(AVG(r.prep_fee), 2)                            AS avg_fee_per_return,
    ROUND(SUM(r.prep_fee) * 1.0 / COUNT(DISTINCT c.client_id), 2) AS revenue_per_client
FROM clients c
LEFT JOIN tax_returns r USING (client_id)
GROUP BY c.referral_source
ORDER BY revenue_per_client DESC;


-- @name demographic_mix
-- Snapshot of client base by age/marital/occupation (most-recent year)
SELECT
    age_band,
    COUNT(*) AS clients
FROM clients
GROUP BY age_band
ORDER BY age_band;


-- @name province_mix
SELECT province, COUNT(*) AS clients
FROM clients
GROUP BY province
ORDER BY clients DESC;


-- @name refund_distribution_by_occupation
-- Are some occupation groups consistently getting refunds vs owing?
SELECT
    c.occupation_category,
    COUNT(*)                                             AS returns,
    ROUND(AVG(r.refund_or_owing), 2)                     AS avg_refund_or_owing,
    SUM(CASE WHEN r.refund_or_owing > 0 THEN 1 ELSE 0 END) AS refund_count,
    SUM(CASE WHEN r.refund_or_owing < 0 THEN 1 ELSE 0 END) AS owing_count,
    ROUND(100.0 * SUM(CASE WHEN r.refund_or_owing > 0 THEN 1 ELSE 0 END)
                / COUNT(*), 1)                           AS refund_rate_pct
FROM tax_returns r
JOIN clients c USING (client_id)
GROUP BY c.occupation_category
ORDER BY avg_refund_or_owing DESC;


-- @name missed_rrsp_opportunity
-- Clients with high income (>$70K) who didn't contribute to RRSP — sales lead list
WITH rrsp_contribs AS (
    SELECT return_id, SUM(amount) AS rrsp_amount
    FROM deductions
    WHERE deduction_type = 'RRSP'
    GROUP BY return_id
)
SELECT
    r.client_id,
    r.tax_year,
    ROUND(r.total_income, 0)        AS total_income,
    ROUND(r.federal_tax + r.provincial_tax, 0) AS tax_paid,
    COALESCE(ROUND(rc.rrsp_amount, 0), 0)      AS rrsp_contributed,
    -- Implied tax savings if they had contributed 10% of income
    ROUND(MIN(r.total_income * 0.10, 31560)
          * (CASE WHEN r.total_income > 111733 THEN 0.43
                  WHEN r.total_income >  55867 THEN 0.30
                  ELSE 0.20 END), 0)           AS potential_savings_at_10pct
FROM tax_returns r
LEFT JOIN rrsp_contribs rc USING (return_id)
JOIN clients c USING (client_id)
WHERE r.total_income > 70000
  AND COALESCE(rc.rrsp_amount, 0) < 1000
  AND c.occupation_category != 'retired'
  AND r.tax_year = (SELECT MAX(tax_year) FROM tax_returns)
ORDER BY potential_savings_at_10pct DESC
LIMIT 10;


-- @name top_balances_owing
-- Biggest balances owing — clients who likely under-withheld (good RRSP/installment talk)
SELECT
    r.client_id,
    r.tax_year,
    c.occupation_category,
    ROUND(r.total_income, 0)                AS total_income,
    ROUND(r.refund_or_owing, 0)             AS balance_owing
FROM tax_returns r
JOIN clients c USING (client_id)
WHERE r.refund_or_owing < 0
ORDER BY r.refund_or_owing ASC
LIMIT 10;


-- @name fee_realization_by_complexity
-- Effective hourly rate by complexity — surfaces under-priced segments
SELECT
    complexity_score,
    COUNT(*)                                            AS returns,
    ROUND(AVG(prep_fee), 2)                             AS avg_fee,
    ROUND(AVG(prep_minutes), 0)                         AS avg_minutes,
    ROUND(AVG(prep_fee * 60.0 / prep_minutes), 2)       AS effective_hourly_rate
FROM tax_returns
GROUP BY complexity_score
ORDER BY complexity_score;
