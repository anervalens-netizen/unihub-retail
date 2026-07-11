from __future__ import annotations

import pytest

from services.receipt_identity import canonical_receipt_identity_sql


def test_canonical_receipt_identity_contains_all_business_dimensions() -> None:
    expression = canonical_receipt_identity_sql("st")

    assert expression == (
        "(st.sale_date, st.site_code, "
        "COALESCE(NULLIF(BTRIM(st.agent), ''), '<unknown>'), st.bon_nr)"
    )


@pytest.mark.parametrize(
    "alias",
    ["", "st;DROP TABLE sales_transactions", "st.alias", "1st", "st-alias"],
)
def test_canonical_receipt_identity_rejects_unsafe_aliases(alias: str) -> None:
    with pytest.raises(ValueError, match="Invalid SQL alias"):
        canonical_receipt_identity_sql(alias)
