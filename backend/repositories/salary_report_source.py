"""Official monthly salary report source.

Archived HR rows remain available through the separate archive and review flows;
they enter official reports only after an approved salary import promotion.
"""
SALARY_MONTHLY_REPORT_SOURCE = """(
    SELECT id::text AS id,year,month,full_name,person_id,total_salary,
           company_name,site_code,locatie FROM salary_records
)"""
