"""Read-only monthly report composition; does not promote HR or create identities.

July source rows were checked: 161 distinct HR names, no repeated components.
Unlinked positions keep distinct local grouping keys, never a shared NULL person.
The fallback keys are not persisted or exposed by person-history endpoints.
"""
SALARY_MONTHLY_REPORT_SOURCE = """(
    SELECT id::text AS id,year,month,full_name,person_id,total_salary,
           company_name,site_code,locatie FROM salary_records
    UNION ALL
    SELECT source_row_key AS id,2026 AS year,7 AS month,full_name,
           COALESCE(candidate_person_id,'hr-position:' || source_row_key) AS person_id,
           total_amount AS total_salary,company_name,site_code,location AS locatie
    FROM salary_history_rows h
    WHERE period='2026-07' AND selected AND total_amount IS NOT NULL
      AND company_name IN ('Mobiup','Mobicell')
      AND NOT EXISTS (SELECT 1 FROM salary_records s
          WHERE s.year=2026 AND s.month=7 AND lower(s.company_name)=lower(h.company_name))
)"""
