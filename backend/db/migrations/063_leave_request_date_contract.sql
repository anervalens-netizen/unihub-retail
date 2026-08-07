DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM leave_requests
        WHERE start_date > end_date
    ) THEN
        RAISE EXCEPTION
            'leave_requests contains rows with start_date after end_date; repair data before migration 063';
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_leave_requests_date_order'
          AND conrelid = 'leave_requests'::regclass
    ) THEN
        ALTER TABLE leave_requests
            ADD CONSTRAINT ck_leave_requests_date_order
            CHECK (start_date <= end_date) NOT VALID;
    END IF;
END
$$;

ALTER TABLE leave_requests
    VALIDATE CONSTRAINT ck_leave_requests_date_order;

COMMENT ON CONSTRAINT ck_leave_requests_date_order ON leave_requests IS
    'Leave intervals are inclusive and cannot end before they start.';
