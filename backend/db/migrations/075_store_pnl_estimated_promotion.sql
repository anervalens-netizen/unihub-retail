-- Owner-approved estimated-only publication. Finance and Target stay separate.
CREATE TABLE public.store_pnl_estimate_control (
    id boolean PRIMARY KEY DEFAULT true CHECK (id),
    revision bigint NOT NULL DEFAULT 0 CHECK (revision >= 0)
);
INSERT INTO public.store_pnl_estimate_control DEFAULT VALUES;
CREATE TABLE public.store_pnl_estimate_generations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    manifest jsonb NOT NULL, manifest_sha256 text NOT NULL,
    scopes jsonb NOT NULL, through_month date NOT NULL,
    candidate jsonb NOT NULL, candidate_sha256 text NOT NULL,
    preimage jsonb NOT NULL, context_sha256 text NOT NULL,
    expected_revision bigint NOT NULL,
    staged_by text NOT NULL DEFAULT session_user,
    staged_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE public.store_pnl_estimate_events (
    revision bigint PRIMARY KEY,
    generation_id uuid NOT NULL REFERENCES public.store_pnl_estimate_generations(id),
    action text NOT NULL CHECK (action IN ('promoted','rolled_back')),
    context_sha256 text NOT NULL,
    actor text NOT NULL DEFAULT session_user,
    approval_reference text NOT NULL CHECK (length(btrim(approval_reference)) BETWEEN 8 AND 500),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (generation_id, action)
);
CREATE FUNCTION public._pnl_estimate_immutable() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
BEGIN RAISE EXCEPTION 'P&L estimate evidence is immutable'; END $$;
CREATE TRIGGER immutable_estimate_generation BEFORE UPDATE OR DELETE OR TRUNCATE
ON public.store_pnl_estimate_generations FOR EACH STATEMENT EXECUTE FUNCTION public._pnl_estimate_immutable();
CREATE TRIGGER immutable_estimate_event BEFORE UPDATE OR DELETE OR TRUNCATE
ON public.store_pnl_estimate_events FOR EACH STATEMENT EXECUTE FUNCTION public._pnl_estimate_immutable();

CREATE FUNCTION public._pnl_estimate_digest(v jsonb) RETURNS text
LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog,public AS $$
SELECT encode(sha256(convert_to(v::text,'UTF8')),'hex') $$;

CREATE FUNCTION public._pnl_estimate_authority() RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
    IF session_user <> 'unihub_operations_worker' OR NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname=session_user AND rolcanlogin AND rolinherit
        AND NOT (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
    ) OR (SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member
          WHERE r.rolname=session_user) <> 1 OR NOT EXISTS (
        SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member
        JOIN pg_roles p ON p.oid=m.roleid
        WHERE r.rolname=session_user AND p.rolname='unihub_operations'
          AND m.inherit_option AND NOT m.set_option AND NOT m.admin_option
    ) OR EXISTS (
        SELECT 1 FROM pg_roles r WHERE r.rolname NOT IN (session_user,'unihub_operations')
          AND pg_has_role(session_user,r.oid,'member')
    ) OR EXISTS (
        SELECT 1 FROM pg_shdepend d JOIN pg_roles r ON r.oid=d.refobjid
        WHERE r.rolname=session_user AND d.refclassid='pg_authid'::regclass AND d.deptype IN ('a','o')
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname='unihub_operations'
          AND NOT (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
    ) THEN RAISE EXCEPTION 'Authenticated operations principal required'; END IF;
END $$;

CREATE FUNCTION public._pnl_estimate_context(scopes jsonb, cutoff date) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
SELECT public._pnl_estimate_digest(jsonb_build_object(
 'pnl', (SELECT coalesce(jsonb_agg(v ORDER BY v::text),'[]'::jsonb) FROM (
   SELECT to_jsonb(p)-'id' v FROM public.store_pnl_monthly p
   JOIN jsonb_to_recordset(scopes) s(company text,period date)
     ON p.company_name=s.company AND p.period=s.period) q),
 'links',(SELECT coalesce(jsonb_agg(to_jsonb(l) ORDER BY l.company_name,l.source_site_code),'[]'::jsonb) FROM public.store_pnl_site_links l),
 'finance_heads',(SELECT coalesce(jsonb_agg(to_jsonb(h) ORDER BY h.company_name,h.period),'[]'::jsonb) FROM public.store_pnl_generation_heads h),
 'stores',(SELECT coalesce(jsonb_agg(v ORDER BY v::text),'[]'::jsonb) FROM (SELECT jsonb_build_array(site_code,locatie,firma) v FROM public.stores) q),
 'historical_sales',(SELECT coalesce(jsonb_agg(v ORDER BY v::text),'[]'::jsonb) FROM (
   SELECT jsonb_build_array(site_code,firma,import_month,total_value) v FROM public.historical_monthly_sales WHERE import_month<=to_char(cutoff,'YYYY-MM')) q),
 'reporting_sales',(SELECT coalesce(jsonb_agg(v ORDER BY v::text),'[]'::jsonb) FROM (
   SELECT jsonb_build_array(site_code,firma,import_month,sum(total_sales)) v FROM public.reporting_agent_month
   WHERE import_month<=to_char(cutoff,'YYYY-MM') GROUP BY site_code,firma,import_month) q),
 'salaries',(SELECT coalesce(jsonb_agg(v ORDER BY v::text),'[]'::jsonb) FROM (
   SELECT jsonb_build_array(company_name,year,month,site_code,locatie,count(*),sum(total_salary)) v
   FROM public.salary_records WHERE make_date(year,month,1)<=cutoff GROUP BY company_name,year,month,site_code,locatie) q),
 'hr',(SELECT coalesce(jsonb_agg(v ORDER BY v::text),'[]'::jsonb) FROM (
   SELECT jsonb_build_array(company_name,period,site_code,source_sha256,source_sheet,selected,pnl_eligible,already_recorded,count(*),count(total_amount),sum(total_amount)) v
   FROM public.salary_history_rows WHERE period<=to_char(cutoff,'YYYY-MM')
   GROUP BY company_name,period,site_code,source_sha256,source_sheet,selected,pnl_eligible,already_recorded) q)
)) $$;

CREATE FUNCTION public.inspect_store_pnl_estimate_context(scopes jsonb, cutoff date) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
 PERFORM public._pnl_estimate_authority();
 RETURN jsonb_build_object('revision',(SELECT revision FROM public.store_pnl_estimate_control WHERE id),
   'context_sha256',public._pnl_estimate_context(scopes,cutoff));
END $$;

CREATE FUNCTION public._pnl_estimate_lock(scopes jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE s record;
BEGIN
 PERFORM 1 FROM public.store_pnl_estimate_control WHERE id FOR UPDATE;
 FOR s IN SELECT company,period FROM jsonb_to_recordset(scopes) x(company text,period date) ORDER BY company,period LOOP
   PERFORM pg_advisory_xact_lock(hashtextextended('store-pnl:'||s.company||':'||s.period::text,0));
 END LOOP;
 LOCK TABLE public.store_pnl_monthly IN SHARE ROW EXCLUSIVE MODE;
 LOCK TABLE public.store_pnl_site_links,public.store_pnl_generation_heads,public.stores,
   public.historical_monthly_sales,public.reporting_agent_month,public.salary_records,public.salary_history_rows IN SHARE MODE;
END $$;

CREATE FUNCTION public.stage_store_pnl_estimate(manifest jsonb, candidate_text text, expected_context text, expected_revision bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE scopes jsonb:=manifest->'scopes'; cutoff date:=(manifest->>'through_month')::date;
 rows jsonb:=candidate_text::jsonb; gid uuid; before_rows jsonb; msha text;
BEGIN
 PERFORM public._pnl_estimate_authority();
 IF jsonb_typeof(scopes) IS DISTINCT FROM 'array' OR jsonb_array_length(scopes) NOT BETWEEN 1 AND 2400
    OR jsonb_typeof(rows) IS DISTINCT FROM 'array' OR jsonb_array_length(rows) NOT BETWEEN 12 AND 500000
    OR cutoff IS NULL OR cutoff<>date_trunc('month',cutoff)::date
    OR manifest->>'input_sha256' IS NULL OR (manifest->>'input_sha256') !~ '^[0-9a-f]{64}$'
    OR manifest->>'ruleset' IS DISTINCT FROM 'effective-vat-hr-v1'
    OR encode(sha256(convert_to(candidate_text,'UTF8')),'hex') IS DISTINCT FROM manifest->>'output_sha256'
 THEN RAISE EXCEPTION 'Invalid estimate manifest or candidate hash'; END IF;
 IF EXISTS (SELECT 1 FROM jsonb_to_recordset(scopes) s(company text,period date)
   WHERE company IS NULL OR company NOT IN ('Mobiup','Mobicell') OR period IS NULL
   OR period<>date_trunc('month',period)::date OR period>cutoff)
 OR (SELECT count(*) FROM jsonb_to_recordset(scopes) s(company text,period date)) <>
    (SELECT count(DISTINCT (company,period)) FROM jsonb_to_recordset(scopes) s(company text,period date))
 THEN RAISE EXCEPTION 'Invalid or duplicate estimate scope'; END IF;
 IF EXISTS (SELECT 1 FROM jsonb_array_elements(rows) r WHERE jsonb_typeof(r)<>'object'
     OR (SELECT count(*) FROM jsonb_object_keys(r))<>8
     OR NOT r ?& ARRAY['company_name','period','site_code','source_site_code','source_location_name','category_code','category_name','amount'])
 THEN RAISE EXCEPTION 'Unexpected candidate fields'; END IF;
 PERFORM public._pnl_estimate_lock(scopes);
 IF (SELECT revision FROM public.store_pnl_estimate_control WHERE id) IS DISTINCT FROM expected_revision
    OR public._pnl_estimate_context(scopes,cutoff) IS DISTINCT FROM expected_context
 THEN RAISE EXCEPTION 'Estimate input context or revision changed'; END IF;
 IF EXISTS (
   SELECT 1 FROM jsonb_to_recordset(rows) r(company_name text,period date,site_code text,source_site_code text,source_location_name text,category_code text,category_name text,amount numeric)
   LEFT JOIN public.stores st ON st.site_code=r.site_code
   LEFT JOIN public.store_pnl_site_links l ON l.company_name=r.company_name AND l.source_site_code=r.source_site_code
   WHERE st.site_code IS NULL OR coalesce(btrim(r.source_site_code),'') IN ('','__FINANCE_UNALLOCATED__')
   OR coalesce(l.site_code,r.source_site_code) IS DISTINCT FROM r.site_code
   OR coalesce(btrim(r.source_location_name),'')='' OR coalesce(btrim(r.category_name),'')=''
   OR r.category_code IS NULL OR r.category_code NOT IN ('v1','v11','v2','v3','c1','c11','c2','c3','c4','c5','c6','a1')
   OR r.amount IS NULL OR r.amount<0 OR r.amount>=100000000000000 OR r.amount::text IN ('NaN','Infinity','-Infinity') OR r.amount<>round(r.amount,2)
   OR NOT EXISTS (SELECT 1 FROM jsonb_to_recordset(scopes) s(company text,period date) WHERE s.company=r.company_name AND s.period=r.period)
   OR EXISTS (SELECT 1 FROM public.store_pnl_monthly a LEFT JOIN public.store_pnl_site_links al USING(company_name,source_site_code)
       WHERE a.data_kind='actual' AND a.company_name=r.company_name AND a.period=r.period AND coalesce(al.site_code,a.source_site_code)=r.site_code)
 ) OR EXISTS (SELECT 1 FROM jsonb_to_recordset(rows) r(company_name text,period date,site_code text,source_site_code text,category_code text)
    GROUP BY company_name,period,site_code HAVING count(*)<>12 OR count(DISTINCT category_code)<>12 OR count(DISTINCT source_site_code)<>1)
 OR EXISTS (SELECT 1 FROM jsonb_to_recordset(scopes) s(company text,period date)
    WHERE NOT EXISTS (SELECT 1 FROM jsonb_to_recordset(rows) r(company_name text,period date) WHERE r.company_name=s.company AND r.period=s.period))
 THEN RAISE EXCEPTION 'Invalid, incomplete, duplicate, unmapped or Finance-overlapping estimate rows'; END IF;
 -- Full canonical store-month coverage, derived from the same source precedence
 -- as all_missing_targets. A manifest cannot silently omit one whole store.
 IF EXISTS (
   WITH sales AS (
     SELECT CASE WHEN firma ILIKE 'mobicell%' THEN 'Mobicell' ELSE 'Mobiup' END company,
       to_date(import_month||'-01','YYYY-MM-DD') period,site_code,total_value::numeric gross,1 priority
       FROM public.historical_monthly_sales
     UNION ALL
     SELECT CASE WHEN firma ILIKE 'mobicell%' THEN 'Mobicell' ELSE 'Mobiup' END,
       to_date(import_month||'-01','YYYY-MM-DD'),site_code,sum(total_sales)::numeric,2
       FROM public.reporting_agent_month GROUP BY firma,import_month,site_code
   ), preferred AS (
     SELECT DISTINCT ON (company,period,site_code) company,period,site_code,gross
     FROM sales ORDER BY company,period,site_code,priority DESC
   ), expected AS (
     SELECT p.company,p.period,p.site_code FROM preferred p
     JOIN jsonb_to_recordset(scopes) s(company text,period date) USING(company,period)
     WHERE p.period BETWEEN date '2018-01-01' AND cutoff
       AND round(p.gross / CASE WHEN p.period<date '2025-08-01' THEN 1.19 ELSE 1.21 END,2)>0
       AND NOT EXISTS (SELECT 1 FROM public.store_pnl_monthly a
         LEFT JOIN public.store_pnl_site_links l USING(company_name,source_site_code)
         WHERE a.data_kind='actual' AND a.company_name=p.company AND a.period=p.period
           AND coalesce(l.site_code,a.source_site_code)=p.site_code)
   ), supplied AS (
     SELECT DISTINCT company_name company,period,site_code FROM jsonb_to_recordset(rows) r(company_name text,period date,site_code text)
   )
   (SELECT * FROM expected EXCEPT SELECT * FROM supplied)
   UNION ALL (SELECT * FROM supplied EXCEPT SELECT * FROM expected)
 ) THEN RAISE EXCEPTION 'Estimate store-month coverage differs from current sources'; END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(p)-'id' ORDER BY p.company_name,p.period,p.source_site_code,p.category_code,p.data_kind),'[]'::jsonb)
 INTO before_rows FROM public.store_pnl_monthly p JOIN jsonb_to_recordset(scopes) s(company text,period date) ON p.company_name=s.company AND p.period=s.period;
 msha:=public._pnl_estimate_digest(manifest);
 INSERT INTO public.store_pnl_estimate_generations(manifest,manifest_sha256,scopes,through_month,candidate,candidate_sha256,preimage,context_sha256,expected_revision)
 VALUES(manifest,msha,scopes,cutoff,rows,public._pnl_estimate_digest(rows),before_rows,expected_context,expected_revision) RETURNING id INTO gid;
 RETURN jsonb_build_object('generation_id',gid,'manifest_sha256',msha,'expected_revision',expected_revision,'rows',jsonb_array_length(rows));
END $$;

CREATE FUNCTION public.publish_store_pnl_estimate(generation uuid, expected_manifest text, expected_revision bigint, approval text, rollback boolean DEFAULT false) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE g public.store_pnl_estimate_generations%ROWTYPE; last_event public.store_pnl_estimate_events%ROWTYPE;
 revision_next bigint; after_hash text; source_label text;
BEGIN
 PERFORM public._pnl_estimate_authority();
 SELECT * INTO g FROM public.store_pnl_estimate_generations WHERE id=generation;
 IF NOT FOUND OR g.manifest_sha256 IS DISTINCT FROM expected_manifest
 OR g.manifest_sha256 IS DISTINCT FROM public._pnl_estimate_digest(g.manifest)
 OR g.candidate_sha256 IS DISTINCT FROM public._pnl_estimate_digest(g.candidate)
 OR approval IS NULL OR length(btrim(approval)) NOT BETWEEN 8 AND 500 OR rollback IS NULL
 THEN RAISE EXCEPTION 'Estimate generation, manifest or approval mismatch'; END IF;
 PERFORM public._pnl_estimate_lock(g.scopes);
 IF (SELECT revision FROM public.store_pnl_estimate_control WHERE id) IS DISTINCT FROM expected_revision
 THEN RAISE EXCEPTION 'Estimate publication revision changed'; END IF;
 SELECT * INTO last_event FROM public.store_pnl_estimate_events ORDER BY revision DESC LIMIT 1;
 IF rollback THEN
   IF last_event.generation_id IS DISTINCT FROM generation OR last_event.action IS DISTINCT FROM 'promoted'
      OR public._pnl_estimate_context(g.scopes,g.through_month) IS DISTINCT FROM last_event.context_sha256
   THEN RAISE EXCEPTION 'Estimate rollback context changed'; END IF;
 ELSE
   IF g.expected_revision IS DISTINCT FROM expected_revision
      OR EXISTS (SELECT 1 FROM public.store_pnl_estimate_events WHERE generation_id=generation)
      OR public._pnl_estimate_context(g.scopes,g.through_month) IS DISTINCT FROM g.context_sha256
   THEN RAISE EXCEPTION 'Estimate promotion context changed or generation already used'; END IF;
 END IF;
 DELETE FROM public.store_pnl_monthly p USING jsonb_to_recordset(g.scopes) s(company text,period date)
 WHERE p.data_kind='estimated' AND p.company_name=s.company AND p.period=s.period;
 IF rollback THEN
   INSERT INTO public.store_pnl_monthly(company_name,period,source_site_code,source_location_name,category_code,category_name,amount,data_kind,source_file,source_sha256,imported_at)
   SELECT company_name,period,source_site_code,source_location_name,category_code,category_name,amount,'estimated',source_file,source_sha256,imported_at
   FROM jsonb_to_recordset(g.preimage) r(company_name text,period date,source_site_code text,source_location_name text,category_code text,category_name text,amount numeric,data_kind text,source_file text,source_sha256 text,imported_at timestamptz)
   WHERE data_kind='estimated';
 ELSE
   source_label:='model:store-pnl-estimator-v3-effective-vat:hr-reconciled:'||generation::text;
   INSERT INTO public.store_pnl_monthly(company_name,period,source_site_code,source_location_name,category_code,category_name,amount,data_kind,source_file,source_sha256)
   SELECT company_name,period,source_site_code,source_location_name,category_code,category_name,amount,'estimated',source_label,g.manifest->>'output_sha256'
   FROM jsonb_to_recordset(g.candidate) r(company_name text,period date,source_site_code text,source_location_name text,category_code text,category_name text,amount numeric);
 END IF;
 revision_next:=expected_revision+1;
 UPDATE public.store_pnl_estimate_control SET revision=revision_next WHERE id;
 after_hash:=public._pnl_estimate_context(g.scopes,g.through_month);
 INSERT INTO public.store_pnl_estimate_events(revision,generation_id,action,context_sha256,approval_reference)
 VALUES(revision_next,generation,CASE WHEN rollback THEN 'rolled_back' ELSE 'promoted' END,after_hash,approval);
 RETURN jsonb_build_object('generation_id',generation,'revision',revision_next,'action',CASE WHEN rollback THEN 'rolled_back' ELSE 'promoted' END,'context_sha256',after_hash);
END $$;

REVOKE ALL ON public.store_pnl_estimate_control,public.store_pnl_estimate_generations,public.store_pnl_estimate_events FROM PUBLIC;
GRANT SELECT ON public.store_pnl_estimate_control,public.store_pnl_estimate_generations,public.store_pnl_estimate_events TO unihub_operations;
REVOKE ALL ON FUNCTION public._pnl_estimate_immutable(),public._pnl_estimate_digest(jsonb),public._pnl_estimate_authority(),public._pnl_estimate_context(jsonb,date),public._pnl_estimate_lock(jsonb),public.inspect_store_pnl_estimate_context(jsonb,date),public.stage_store_pnl_estimate(jsonb,text,text,bigint),public.publish_store_pnl_estimate(uuid,text,bigint,text,boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.inspect_store_pnl_estimate_context(jsonb,date),public.stage_store_pnl_estimate(jsonb,text,text,bigint),public.publish_store_pnl_estimate(uuid,text,bigint,text,boolean) TO unihub_operations;
