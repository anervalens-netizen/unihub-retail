import { describe, expect, it } from 'vitest';
import { buildExcelWorkbook } from './tableExport';

describe('buildExcelWorkbook', () => {
  it('builds a real xlsx zip with worksheet XML', () => {
    type Row = {
      agent: string;
      code: string;
      month: string;
      sales: string;
      achievement: string;
      score: number | null;
    };
    const workbook = buildExcelWorkbook({
      sheetName: 'Focus Agenti',
      columns: [
        { header: 'Agent', value: (row: Row) => row.agent },
        { header: 'Cod', value: (row: Row) => row.code },
        { header: 'Luna', value: (row: Row) => row.month, format: 'month' },
        { header: 'Vanzari', value: (row: Row) => row.sales, format: 'currency' },
        { header: '%Target', value: (row: Row) => row.achievement, format: 'percentPoints' },
        { header: 'Scor', value: (row: Row) => row.score, format: 'number' },
      ],
      rows: [{
        agent: 'Ana & Ion',
        code: '00123',
        month: '2026-07',
        sales: '123.45',
        achievement: '87.5',
        score: null,
      }],
    });

    expect(workbook[0]).toBe(0x50);
    expect(workbook[1]).toBe(0x4b);

    const text = new TextDecoder().decode(workbook);
    expect(text).toContain('xl/worksheets/sheet1.xml');
    expect(text).toContain('xl/styles.xml');
    expect(text).toContain('Ana &amp; Ion');
    expect(text).toContain('<c r="B2" t="inlineStr"><is><t>00123</t></is></c>');
    expect(text).toContain('<c r="C2" s="5"><v>46204</v></c>');
    expect(text).toContain('<c r="D2" s="4"><v>123.45</v></c>');
    expect(text).toContain('<c r="E2" s="3"><v>0.875</v></c>');
    expect(text).toContain('<c r="F2"/>');
    expect(text).toContain('formatCode="0.00%"');
    expect(text).toContain('formatCode="#,##0.00 &quot;RON&quot;"');
    expect(text).toContain('formatCode="yyyy-mm"');
    expect(text).not.toContain('<html');
  });
});
