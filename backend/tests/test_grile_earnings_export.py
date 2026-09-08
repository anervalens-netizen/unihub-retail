"""The exported money and hours share one projection, with no duplicate pay."""
from io import BytesIO
import json
from unittest.mock import AsyncMock
from zipfile import ZipFile

from fastapi import HTTPException
from openpyxl import load_workbook
import pytest

from grile.earnings_projection import project_earnings
from services.grile_calendar import GrileCalendarService
from services.grile_earnings_export import build_earnings_zip
from test_grile_earnings import sources


def test_archive_reconciles_money_hours_revisions_and_literal_names():
    data = sources()
    data['calendar']['roster'][0].update(display_name='=Literal name', identity_status='confirmed')
    calendar = GrileCalendarService.project_calendar('2026-09', data['calendar'])
    earnings = project_earnings(calendar, data)
    artifact = build_earnings_zip(calendar, earnings)
    try:
        with ZipFile(artifact.stream) as archive:
            money_manifest = json.loads(archive.read('castiguri-manifest.json'))
            attendance_manifest = json.loads(archive.read('manifest.json'))
            assert money_manifest['calendar_revision'] == attendance_manifest['projection_revision']
            assert money_manifest['projection_revision'] == earnings.projection_revision
            workbook = load_workbook(BytesIO(archive.read('Castiguri-provizorii-2026-09.xlsx')), data_only=False)
            sheet = workbook['Castiguri provizorii']
            assert sheet['A5'].value == 'AG1'
            assert sheet['B5'].value == '=Literal name' and sheet['B5'].data_type == 's'
            assert sheet['K5'].value == 222
            assert sheet.max_row == 7  # one total per person, not one per worked store
            assert workbook.properties.identifier == earnings.projection_revision
            assert workbook['Detalii zile'].max_row == 10
            workbook.close()
            hours = []
            for name in archive.namelist():
                if name.endswith('.xlsx') and not name.startswith('Castiguri'):
                    book = load_workbook(BytesIO(archive.read(name)), data_only=True)
                    hours.append(book['Pontaj']['AH8'].value)
                    book.close()
            assert sum(hours) == 33  # same person: 22 home + 11 away
    finally:
        artifact.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['sales', 'target', 'calendar', 'cutoff'])
async def test_export_rejects_changed_inputs_before_building(monkeypatch, change):
    data = sources()
    calendar = GrileCalendarService.project_calendar('2026-09', data['calendar'])
    revision = project_earnings(calendar, data).projection_revision
    if change == 'sales':
        data['sales'][0]['sales'] += 1
    elif change == 'target':
        data['targets'][0]['target_value'] += 1
    elif change == 'calendar':
        data['calendar']['days'][0]['revision'] += 1
    else:
        data['source'] = None
    read = AsyncMock(return_value=data)
    monkeypatch.setattr('services.grile_calendar.read_earnings_sources', read)
    with pytest.raises(HTTPException) as error:
        await GrileCalendarService(AsyncMock()).export_earnings('2026-09', revision)
    assert error.value.status_code == 409
    read.assert_awaited_once()


@pytest.mark.asyncio
async def test_export_missing_money_stays_blank_and_reads_once(monkeypatch):
    data = sources()
    data['source'] = None
    calendar = GrileCalendarService.project_calendar('2026-09', data['calendar'])
    revision = project_earnings(calendar, data).projection_revision
    read = AsyncMock(return_value=data)
    monkeypatch.setattr('services.grile_calendar.read_earnings_sources', read)
    artifact = await GrileCalendarService(AsyncMock()).export_earnings('2026-09', revision)
    try:
        with ZipFile(artifact.stream) as archive:
            book = load_workbook(BytesIO(archive.read('Castiguri-provizorii-2026-09.xlsx')), data_only=True)
            assert book['Castiguri provizorii']['K5'].value is None
            assert 'Bază salarială' in book['Castiguri provizorii']['B3'].value
            book.close()
    finally:
        artifact.close()
    read.assert_awaited_once()


def test_export_rejects_mixed_revisions_and_excessive_cohort():
    data = sources()
    calendar = GrileCalendarService.project_calendar('2026-09', data['calendar'])
    earnings = project_earnings(calendar, data)
    with pytest.raises(HTTPException) as error:
        build_earnings_zip(calendar, earnings.model_copy(update={'calendar_revision': 'wrong'}))
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        build_earnings_zip(calendar, earnings.model_copy(update={'agents': earnings.agents * 1000}))
    assert error.value.status_code == 422


def test_partial_build_failure_closes_artifact(monkeypatch):
    from services import grile_earnings_export as module
    data = sources()
    calendar = GrileCalendarService.project_calendar('2026-09', data['calendar'])
    earnings = project_earnings(calendar, data)
    artifact = module.build_attendance_zip(calendar)
    monkeypatch.setattr(module, 'build_attendance_zip', lambda _: artifact)
    def fail(_):
        raise OSError('synthetic disk failure')
    monkeypatch.setattr(module, '_workbook', fail)
    with pytest.raises(OSError):
        module.build_earnings_zip(calendar, earnings)
    assert artifact.stream.closed
