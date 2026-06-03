from pathlib import Path

from openpyxl import load_workbook

from services.grile_monthly import (
    ExtractedAgentRow,
    StoreEntry,
    build_store_export_path,
    build_workbook,
    make_output_row,
    ro_month_label,
    safe_filename,
    validate_archive_manifest,
)


def test_ro_month_label_and_safe_filename():
    assert ro_month_label("2026-06") == "Iunie 2026"
    assert safe_filename("Mobiup/Bad:Name") == "Mobiup - Bad_Name"


def test_build_store_export_path_uses_company_folder(tmp_path: Path):
    entry = StoreEntry(
        company="Mobiup",
        store="Park Lake",
        sheet_id="sheet-1",
        site_code="PARKLAKE",
        manager="Andrei Stancu",
    )

    assert build_store_export_path(tmp_path, "Iunie 2026", entry) == (
        tmp_path / "archive" / "Iunie 2026" / "Mobiup" / "Park Lake.xlsx"
    )


def test_make_output_row_uses_new_salary_formulas():
    row = ExtractedAgentRow(
        company="Mobiup",
        store="Park Lake",
        slot=1,
        agent="Agent Test",
        base_salary=2600,
        sales_commission=300,
        extra_location_commission=25,
        extra_hours_pay=150,
        bonuri=480,
        worked_hours=176,
        status="OK",
        error="",
        sheet_id="sheet-1",
    )

    output = make_output_row(row, nr=1, metadata={"Manager": "Andrei Stancu"})

    assert output[:6] == [1, "Andrei Stancu", "Park Lake", "Agent Test", 2600, 300]
    assert output[7] == 25
    assert output[9] == 150
    assert output[10] == "=SUM(E2:J2,M2)"
    assert output[11] == "=K2-M2"
    assert output[12] == 480


def test_build_workbook_creates_company_sheets_and_audit(tmp_path: Path):
    rows = [
        ExtractedAgentRow("Mobiup", "Park Lake", 1, "A1", 2600, 300, 0, 150, 480, 176, "OK", "", "s1"),
        ExtractedAgentRow("Mobicell", "AFI Cotroceni", 1, "B1", 2600, 100, 0, 0, 480, 165, "OK", "", "s2"),
    ]
    output = tmp_path / "Tabel Salarii - Test.xlsx"

    build_workbook(
        rows,
        output,
        metadata_by_company_store={
            ("Mobiup", "Park Lake"): {"Manager": "Andrei Stancu"},
            ("Mobicell", "AFI Cotroceni"): {"Manager": "Andrei Stancu"},
        },
    )

    wb = load_workbook(output, data_only=False)
    assert wb.sheetnames == ["Mobiup", "Mobicell", "Audit"]
    assert wb["Mobiup"]["B2"].value == "Andrei Stancu"
    assert wb["Mobiup"]["C2"].value == "Park Lake"
    assert wb["Mobiup"]["F1"].value == "Comision vanzare"
    assert wb["Mobiup"]["K2"].value == "=SUM(E2:J2,M2)"
    assert wb["Audit"]["L2"].value == "OK"


def test_validate_archive_manifest_rejects_missing_zip(tmp_path: Path):
    xlsx = tmp_path / "store.xlsx"
    xlsx.write_bytes(b"x")
    manifest = {
        "registry_count": 1,
        "exported_count": 1,
        "error_count": 0,
        "zip_path": str(tmp_path / "missing.zip"),
        "stores": [{"company": "Mobiup", "store": "Park Lake", "status": "OK", "xlsx_path": str(xlsx)}],
    }

    ok, errors = validate_archive_manifest(manifest, expected_count=1)

    assert not ok
    assert any("missing or empty archive zip" in error for error in errors)
