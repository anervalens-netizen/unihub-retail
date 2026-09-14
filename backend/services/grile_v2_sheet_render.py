"""Render canonical V2 values using the owner-approved native Sheet geometry.

One batchUpdate publishes all three tabs atomically. No source business formulas.
"""
from copy import deepcopy
import re
from services.grile_v2_sheet_values import build_values


def _canonical_title(value):
    """Accept a legacy Windows mojibake copy of the Romanian tab title."""
    try:
        repaired = value.encode('cp1252').decode('utf-8')
    except (AttributeError, UnicodeEncodeError, UnicodeDecodeError):
        return value
    return repaired if repaired else value


def _value(v):
    if v is None or v == '':
        return {}
    return {'numberValue': v} if isinstance(v, (int, float)) else {'stringValue': str(v)}


def _sheet_rows(rowmap, source, cols, title, cells, sid):
    raw = source['data'][0]
    source_rows = raw.get('rowData', [])
    rows, dimensions = [], []
    for outrow, inrow in enumerate(rowmap):
        old = source_rows[inrow].get('values', []) if inrow < len(source_rows) else []
        values = []
        for col in range(cols):
            fmt = deepcopy(old[col].get('userEnteredFormat', {})) if col < len(old) else {}
            val = cells.get(title, {}).get((outrow, col), '')
            values.append({'userEnteredFormat': fmt, 'userEnteredValue': _value(val)})
        rows.append({'values': values})
        props = raw.get('rowMetadata', [])
        height = props[inrow].get('pixelSize', 24) if inrow < len(props) else 24
        lines = max((str(cells.get(title, {}).get((outrow, c), '')).count('\n') + 1 for c in range(cols)), default=1)
        if lines > 1:
            height = max(height, min(1000, lines * 19 + 10))
        dimensions.append({'updateDimensionProperties': {'range': {'sheetId': sid, 'dimension': 'ROWS', 'startIndex': outrow, 'endIndex': outrow + 1}, 'properties': {'pixelSize': height}, 'fields': 'pixelSize'}})
    return rows, dimensions


def _merge_requests(source, existing, title, rowmap, layout, sid, sheet_start, snapshot, requests, cells):
    merges = []
    for old in source.get('merges', []):
        start, end = old.get('startRowIndex', 0), old['endRowIndex']
        for outrow, inrow in enumerate(rowmap):
            if inrow == start and rowmap[outrow:outrow + end - start] == list(range(start, end)):
                merges.append({**old, 'sheetId': sid, 'startRowIndex': outrow, 'endRowIndex': outrow + end - start})
    if title == 'Calendar':
        note = layout['calendar_sections']['supplement_row'] + 2
        merges.append({'sheetId': sid, 'startRowIndex': note, 'endRowIndex': note + 1, 'startColumnIndex': 0, 'endColumnIndex': 7})
    old_merges = existing.get('merges', [])
    for old in old_merges:
        if old not in merges:
            requests.insert(sheet_start + 1, {'unmergeCells': {'range': old}})
    for merged in merges:
        if merged not in old_merges:
            requests.append({'mergeCells': {'range': merged, 'mergeType': 'MERGE_ALL'}})
    if title == 'Grilă':
        ranges = [{'sheetId': sid, 'startRowIndex': 6, 'endRowIndex': 7, 'startColumnIndex': 10, 'endColumnIndex': 15}]
        for i, _ in enumerate(snapshot['agents']):
            rr, cc = 13 + (i // 2) * 24, 10 + (i % 2) * 13
            ranges.append({'sheetId': sid, 'startRowIndex': rr, 'endRowIndex': rr + 1, 'startColumnIndex': cc, 'endColumnIndex': cc + 2})
        for idx, (kind, threshold, bg, fg) in enumerate([
            ('NUMBER_GREATER_THAN_EQ', '99%', {'red': .86, 'green': .96, 'blue': .88}, {'red': .05, 'green': .4, 'blue': .13}),
            ('NUMBER_GREATER_THAN_EQ', '90%', {'red': 1, 'green': .96, 'blue': .75}, {'red': .6, 'green': .4, 'blue': 0}),
            ('NUMBER_LESS', '90%', {'red': 1, 'green': .88, 'blue': .88}, {'red': .8, 'green': 0, 'blue': 0}),
        ]):
            requests.append({'addConditionalFormatRule': {'index': idx, 'rule': {'ranges': ranges, 'booleanRule': {'condition': {'type': kind, 'values': [{'userEnteredValue': threshold}]}, 'format': {'backgroundColor': bg, 'textFormat': {'bold': True, 'foregroundColor': fg}}}}}})
    for merged in merges:
        top, left = merged.get('startRowIndex', 0), merged.get('startColumnIndex', 0)
        for r, c in cells.get(title, {}):
            if top <= r < merged['endRowIndex'] and left <= c < merged['endColumnIndex'] and (r, c) != (top, left):
                raise ValueError(f'Value inside non-anchor merged cell: {title} {r + 1},{c + 1}')


def render_requests(snapshot, template, current, synced_at):
    result = build_values(snapshot, synced_at)
    layout = result['layout']
    pairs = max(1, len(layout['agent_pairs']))
    weeks = len(layout['calendar_weeks'])
    cells = {}
    for entry in result['data']:
        match = re.fullmatch(r"'([^']+)'!([A-Z]+)(\d+)", entry['range'])
        title, letters, row = match.groups()
        col = 0
        for letter in letters:
            col = col * 26 + ord(letter) - 64
        cells.setdefault(title, {})[(int(row)-1, col-1)] = entry['values'][0][0]
    current_by_title = {
        _canonical_title(s['properties']['title']): s for s in current['sheets']
    }
    requests = []
    for source in template['sheets']:
        title = _canonical_title(source['properties']['title'])
        existing = current_by_title[title]
        sid = existing['properties']['sheetId']
        gp = source['properties']['gridProperties']
        cols = gp['columnCount']
        if title == 'Grilă':
            rowmap = list(range(8))
            for pair in range(pairs):
                rowmap += list(range(8, 30)) + [30, 30]
            rowmap = rowmap[:layout['supplement_row']-1] + list(range(31, 36))
        elif title == 'Calendar':
            rowmap = list(range(5)) + [5 + i % 3 for i in range(weeks * 3)] + list(range(20, 30))
        else:
            maxrow = max((r for r,c in cells[title]), default=29)
            count = max(8, (maxrow - 6)//3 + 1)
            rowmap = list(range(6)) + [6 + i % 6 for i in range(count * 3)] + list(range(30,34))
        size = len(rowmap)
        sheet_start = len(requests)
        requested = max(size, existing['properties']['gridProperties']['rowCount'])
        requests.append({'updateSheetProperties': {'properties': {'sheetId': sid, 'gridProperties': {'rowCount': requested, 'hideGridlines': True}}, 'fields': 'gridProperties.rowCount,gridProperties.hideGridlines'}})
        all_range = {'sheetId': sid}
        for i in reversed(range(len(existing.get('conditionalFormats', [])))):
            requests.append({'deleteConditionalFormatRule': {'sheetId': sid, 'index': i}})
        requests.append({'repeatCell': {'range': all_range, 'cell': {}, 'fields': 'userEnteredValue,userEnteredFormat,note,dataValidation'}})
        rows, dimensions = _sheet_rows(rowmap, source, cols, title, cells, sid)
        requests.extend(dimensions)
        requests.append({'updateCells': {'start': {'sheetId':sid,'rowIndex':0,'columnIndex':0}, 'rows':rows,'fields':'userEnteredValue,userEnteredFormat'}})
        _merge_requests(source, existing, title, rowmap, layout, sid, sheet_start, snapshot, requests, cells)
        # Wrap long names and notes throughout without exposing default grid lines.
        requests.append({'repeatCell': {'range':all_range,'cell':{'userEnteredFormat':{'wrapStrategy':'WRAP'}},'fields':'userEnteredFormat.wrapStrategy'}})
    return requests
