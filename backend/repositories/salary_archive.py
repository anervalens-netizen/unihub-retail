from __future__ import annotations

class SalaryArchiveQueries:
    async def fetch_salary_archive(self, *, year=None, month=None, search=None,
                                   company_name=None, site_code=None, regional=None,
                                   asm=None, limit=100, offset=0):
        clauses, args = [], []
        def add(sql, value):
            args.append(value)
            clauses.append(sql.replace('?', '$'+str(len(args))))
        if year is not None:
            add('left(h.period,4)::integer = ?', year)
        if month is not None:
            add('right(h.period,2)::integer = ?', month)
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
        base = ' FROM salary_history_rows h LEFT JOIN stores s ON s.site_code=h.site_code WHERE '+where
        fields = '''h.period,h.company_name,h.full_name,h.site_code,h.location,
            h.total_amount,h.identity_status,h.review_reasons,h.candidate_person_id,
            h.source_file,h.source_sheet,h.source_row,h.selected,h.pnl_eligible,
            (h.already_recorded OR EXISTS (SELECT 1 FROM salary_records sr
                WHERE sr.year=left(h.period,4)::integer AND sr.month=right(h.period,2)::integer
                AND lower(sr.company_name)=lower(h.company_name))) AS already_recorded'''
        async with self.pool.acquire() as conn:
            async with conn.transaction(isolation='repeatable_read', readonly=True):
                total = await conn.fetchval('SELECT count(*)'+base, *args)
                rows = await conn.fetch('SELECT '+fields+base+
                    ' ORDER BY h.period DESC NULLS LAST,h.company_name,h.full_name,h.source_row_key'
                    +f' LIMIT ${len(args)+1} OFFSET ${len(args)+2}', *args,limit,offset)
        return {'items':[dict(row) for row in rows], 'total_rows':total}
