from __future__ import annotations

class SalaryArchiveQueries:
    async def fetch_salary_archive(self, *, year=None, month=None, search=None,
                                   company_name=None, site_code=None, regional=None,
                                   asm=None, limit=100, offset=0, summary=False, name_exact=None, location_exact=None, person_id=None, source_company=None, data_source="history", location_unmapped=False):
        clauses, args = [], []
        def add(sql, value):
            args.append(value)
            clauses.append(sql.replace('?', '$'+str(len(args))))
        if year is not None:
            add('left(h.period,4)::integer = ?', year)
        if month is not None:
            add('right(h.period,2)::integer = ?', month)
        if name_exact:
            add("upper(regexp_replace(trim(h.full_name),'\\s+',' ','g')) = upper(regexp_replace(trim(?),'\\s+',' ','g'))", name_exact)
        if location_unmapped:
            clauses.append("h.site_code IS NULL AND NULLIF(BTRIM(h.location),'') IS NULL")
        if location_exact is not None:
            add('BTRIM(h.location) = BTRIM(?)', location_exact)
        if person_id:
            add('h.candidate_person_id = ?', person_id)
        if source_company:
            add('lower(h.company_name) = lower(?)', source_company)
        if search:
            add('h.full_name ILIKE ?', '%'+search+'%')
        if site_code:
            add('h.site_code = ANY(?::text[])', site_code)
        else:
            if company_name:
                add('lower(h.company_name) = lower(?)', company_name)
            if regional:
                add('s.regional = ?', regional)
            if asm:
                add('s.asm = ?', asm)
        where = ' AND '.join(clauses) or 'TRUE'
        if data_source == 'recorded':
            source = """(SELECT id::text AS source_row_key,
                to_char(year,'FM0000') || '-' || to_char(month,'FM00') AS period,
                company_name,full_name,site_code,locatie AS location,total_salary AS total_amount,
                'recorded'::text AS identity_status,ARRAY[]::text[] AS review_reasons,
                person_id AS candidate_person_id,'Salariu înregistrat'::text AS source_file,
                ''::text AS source_sheet,id::integer AS source_row,
                true AS selected,false AS pnl_eligible,true AS already_recorded
                FROM salary_records)"""
        elif data_source == 'history':
            source = 'salary_history_rows'
        else:
            raise ValueError('Unknown salary detail source')
        base = ' FROM '+source+' h LEFT JOIN stores s ON s.site_code=h.site_code WHERE '+where
        fields = '''h.period,h.company_name,h.full_name,h.site_code,h.location,
            h.total_amount,h.identity_status,h.review_reasons,h.candidate_person_id,
            h.source_file,h.source_sheet,h.source_row,h.selected,h.pnl_eligible,
            (h.already_recorded OR EXISTS (SELECT 1 FROM salary_records sr
                WHERE sr.year=left(h.period,4)::integer AND sr.month=right(h.period,2)::integer
                AND lower(sr.company_name)=lower(h.company_name))) AS already_recorded'''
        async with self.pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read', readonly=True):
                if summary:
                    eligible = base + ' AND h.selected AND h.total_amount IS NOT NULL AND h.period IS NOT NULL AND h.company_name IS NOT NULL'
                    overview = await conn.fetchrow('SELECT count(*) AS rows, COALESCE(sum(h.total_amount),0) AS total, count(DISTINCT h.period) AS months'+eligible, *args)
                    excluded = await conn.fetchval('SELECT count(*)'+base+' AND NOT (h.selected AND h.total_amount IS NOT NULL AND h.period IS NOT NULL AND h.company_name IS NOT NULL)', *args)
                    monthly = await conn.fetch('SELECT h.period, h.company_name, count(*) AS rows, sum(h.total_amount) AS total'+eligible+' GROUP BY h.period,h.company_name ORDER BY h.period DESC,h.company_name', *args)
                    stores = await conn.fetch("SELECT h.site_code, min(COALESCE(NULLIF(BTRIM(h.location),''),h.site_code,'Fără magazin precizat')) AS location, bool_and(h.site_code IS NULL AND NULLIF(BTRIM(h.location),'') IS NULL) AS location_unmapped, h.company_name, count(*) AS rows, count(DISTINCT h.period) AS months, sum(h.total_amount) AS total"+eligible+" GROUP BY h.site_code,CASE WHEN h.site_code IS NULL THEN NULLIF(BTRIM(h.location),'') END,h.company_name ORDER BY total DESC", *args)
                    agents = await conn.fetch("SELECT min(full_name) AS full_name,company_name,sum(month_total) AS total,count(*) AS months,sum(rows)::integer AS rows,COALESCE(avg(month_total) FILTER(WHERE month_total>=2000),0) AS avg_salary FROM (SELECT min(h.full_name) AS full_name,upper(regexp_replace(trim(h.full_name),'\\s+',' ','g')) AS name_key,h.company_name,h.period,sum(h.total_amount) AS month_total,count(*) AS rows"+eligible+" GROUP BY upper(regexp_replace(trim(h.full_name),'\\s+',' ','g')),h.company_name,h.period) a GROUP BY name_key,company_name ORDER BY total DESC", *args)
                    return {'agents':[dict(row) for row in agents],'total':overview['total'],'rows':overview['rows'],'months':overview['months'],'excluded_rows':excluded,'monthly':[dict(row) for row in monthly],'stores':[dict(row) for row in stores]}
                total = await conn.fetchval('SELECT count(*)'+base, *args)
                rows = await conn.fetch('SELECT '+fields+base+
                    ' ORDER BY h.period DESC NULLS LAST,h.company_name,h.full_name,h.source_row_key'
                    +f' LIMIT ${len(args)+1} OFFSET ${len(args)+2}', *args,limit,offset)
        return {'items':[dict(row) for row in rows], 'total_rows':total}
