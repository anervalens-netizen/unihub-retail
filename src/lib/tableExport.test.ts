import { describe, expect, it } from 'vitest';
import { buildExcelWorkbook } from './tableExport';

describe('buildExcelWorkbook', () => {
  it('builds a real xlsx zip with worksheet XML', () => {
    type Row = { agent: string; sales: number; achievement: number };
    const workbook = buildExcelWorkbook({
      sheetName: 'Focus Agenti',
      columns: [
        { header: 'Agent', value: (row: Row) => row.agent },
        { header: 'Vanzari', value: (row: Row) => row.sales, format: 'currency' },
        { header: '%Prev.', value: (row: Row) => row.achievement, format: 'percent' },
      ],
      rows: [{ agent: 'Ana & Ion', sales: 123, achievement: 1.1 }],
    });

    expect(workbook[0]).toBe(0x50);
    expect(workbook[1]).toBe(0x4b);

    const text = new TextDecoder().decode(workbook);
    expect(text).toContain('xl/worksheets/sheet1.xml');
    expect(text).toContain('xl/styles.xml');
    expect(text).toContain('Ana &amp; Ion');
    expect(text).toContain('<c r="B2" s="4"><v>123</v></c>');
    expect(text).toContain('<c r="C2" s="3"><v>1.1</v></c>');
    expect(text).toContain('formatCode="0%"');
    expect(text).toContain('formatCode="#,##0 &quot;RON&quot;"');
    expect(text).not.toContain('<html');
  });
});
