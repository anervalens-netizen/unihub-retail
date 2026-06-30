import { describe, expect, it } from 'vitest';
import { buildExcelWorkbook } from './tableExport';

describe('buildExcelWorkbook', () => {
  it('builds a real xlsx zip with worksheet XML', () => {
    type Row = { agent: string; sales: number };
    const workbook = buildExcelWorkbook({
      sheetName: 'Focus Agenti',
      columns: [
        { header: 'Agent', value: (row: Row) => row.agent },
        { header: 'Vanzari', value: (row: Row) => row.sales },
      ],
      rows: [{ agent: 'Ana & Ion', sales: 123 }],
    });

    expect(workbook[0]).toBe(0x50);
    expect(workbook[1]).toBe(0x4b);

    const text = new TextDecoder().decode(workbook);
    expect(text).toContain('xl/worksheets/sheet1.xml');
    expect(text).toContain('Ana &amp; Ion');
    expect(text).toContain('<v>123</v>');
    expect(text).not.toContain('<html');
  });
});
