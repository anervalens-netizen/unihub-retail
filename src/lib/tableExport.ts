import { downloadBlob } from './download';

export type ExportColumn<T> = {
  header: string;
  value: (row: T, index: number) => string | number | null | undefined;
  format?: 'integer' | 'number' | 'percent' | 'currency';
};

type WorkbookFile = {
  path: string;
  content: Uint8Array;
};

const encoder = new TextEncoder();
const CRC_TABLE = makeCrcTable();

function makeCrcTable(): Uint32Array {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i += 1) {
    let c = i;
    for (let j = 0; j < 8; j += 1) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[i] = c >>> 0;
  }
  return table;
}

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function writeUint16(view: DataView, offset: number, value: number): void {
  view.setUint16(offset, value, true);
}

function writeUint32(view: DataView, offset: number, value: number): void {
  view.setUint32(offset, value >>> 0, true);
}

function concatBytes(parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}

function zipStore(files: WorkbookFile[]): Uint8Array {
  const localParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  let offset = 0;

  for (const file of files) {
    const filename = encoder.encode(file.path);
    const checksum = crc32(file.content);

    const localHeader = new Uint8Array(30 + filename.length);
    const localView = new DataView(localHeader.buffer);
    writeUint32(localView, 0, 0x04034b50);
    writeUint16(localView, 4, 20);
    writeUint16(localView, 6, 0);
    writeUint16(localView, 8, 0);
    writeUint16(localView, 10, 0);
    writeUint16(localView, 12, 0);
    writeUint32(localView, 14, checksum);
    writeUint32(localView, 18, file.content.length);
    writeUint32(localView, 22, file.content.length);
    writeUint16(localView, 26, filename.length);
    writeUint16(localView, 28, 0);
    localHeader.set(filename, 30);
    localParts.push(localHeader, file.content);

    const centralHeader = new Uint8Array(46 + filename.length);
    const centralView = new DataView(centralHeader.buffer);
    writeUint32(centralView, 0, 0x02014b50);
    writeUint16(centralView, 4, 20);
    writeUint16(centralView, 6, 20);
    writeUint16(centralView, 8, 0);
    writeUint16(centralView, 10, 0);
    writeUint16(centralView, 12, 0);
    writeUint16(centralView, 14, 0);
    writeUint32(centralView, 16, checksum);
    writeUint32(centralView, 20, file.content.length);
    writeUint32(centralView, 24, file.content.length);
    writeUint16(centralView, 28, filename.length);
    writeUint16(centralView, 30, 0);
    writeUint16(centralView, 32, 0);
    writeUint16(centralView, 34, 0);
    writeUint16(centralView, 36, 0);
    writeUint32(centralView, 38, 0);
    writeUint32(centralView, 42, offset);
    centralHeader.set(filename, 46);
    centralParts.push(centralHeader);

    offset += localHeader.length + file.content.length;
  }

  const centralDirectory = concatBytes(centralParts);
  const end = new Uint8Array(22);
  const endView = new DataView(end.buffer);
  writeUint32(endView, 0, 0x06054b50);
  writeUint16(endView, 4, 0);
  writeUint16(endView, 6, 0);
  writeUint16(endView, 8, files.length);
  writeUint16(endView, 10, files.length);
  writeUint32(endView, 12, centralDirectory.length);
  writeUint32(endView, 16, offset);
  writeUint16(endView, 20, 0);

  return concatBytes([...localParts, centralDirectory, end]);
}

function escapeXml(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '';
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
}

function safeFilename(value: string): string {
  return value
    .trim()
    .replace(/[\\/:*?"<>|]+/g, '-')
    .replace(/\s+/g, '_')
    .slice(0, 120) || 'export';
}

function safeSheetName(value: string): string {
  return value
    .replace(/[\][:*?/\\]/g, ' ')
    .trim()
    .slice(0, 31) || 'Export';
}

function columnName(index: number): string {
  let n = index + 1;
  let name = '';
  while (n > 0) {
    const mod = (n - 1) % 26;
    name = String.fromCharCode(65 + mod) + name;
    n = Math.floor((n - mod) / 26);
  }
  return name;
}

function styleId(format: ExportColumn<unknown>['format']): number | null {
  if (format === 'integer') return 1;
  if (format === 'number') return 2;
  if (format === 'percent') return 3;
  if (format === 'currency') return 4;
  return null;
}

function cellXml(
  ref: string,
  value: string | number | null | undefined,
  format?: ExportColumn<unknown>['format'],
): string {
  if (typeof value === 'number' && Number.isFinite(value)) {
    const style = styleId(format);
    return `<c r="${ref}"${style !== null ? ` s="${style}"` : ''}><v>${value}</v></c>`;
  }
  return `<c r="${ref}" t="inlineStr"><is><t>${escapeXml(value)}</t></is></c>`;
}

function worksheetXml<T>(columns: ExportColumn<T>[], rows: T[]): string {
  const headerCells = columns
    .map((column, index) => cellXml(`${columnName(index)}1`, column.header))
    .join('');
  const dataRows = rows
    .map((row, rowIndex) => {
      const rowNumber = rowIndex + 2;
      const cells = columns
        .map((column, columnIndex) => (
          cellXml(
            `${columnName(columnIndex)}${rowNumber}`,
            column.value(row, rowIndex),
            column.format,
          )
        ))
        .join('');
      return `<row r="${rowNumber}">${cells}</row>`;
    })
    .join('');

  const maxColumn = columnName(Math.max(columns.length - 1, 0));
  const maxRow = Math.max(rows.length + 1, 1);

  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <dimension ref="A1:${maxColumn}${maxRow}"/>
  <sheetViews><sheetView workbookViewId="0"/></sheetViews>
  <sheetFormatPr defaultRowHeight="15"/>
  <sheetData><row r="1">${headerCells}</row>${dataRows}</sheetData>
</worksheet>`;
}

export function buildExcelWorkbook<T>({
  sheetName,
  columns,
  rows,
}: {
  sheetName: string;
  columns: ExportColumn<T>[];
  rows: T[];
}): Uint8Array {
  const files: WorkbookFile[] = [
    {
      path: '[Content_Types].xml',
      content: encoder.encode(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>`),
    },
    {
      path: '_rels/.rels',
      content: encoder.encode(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`),
    },
    {
      path: 'xl/workbook.xml',
      content: encoder.encode(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="${escapeXml(safeSheetName(sheetName))}" sheetId="1" r:id="rId1"/></sheets>
</workbook>`),
    },
    {
      path: 'xl/_rels/workbook.xml.rels',
      content: encoder.encode(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`),
    },
    {
      path: 'xl/styles.xml',
      content: encoder.encode(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <numFmts count="4">
    <numFmt numFmtId="164" formatCode="0"/>
    <numFmt numFmtId="165" formatCode="0.00"/>
    <numFmt numFmtId="166" formatCode="0%"/>
    <numFmt numFmtId="167" formatCode="#,##0 &quot;RON&quot;"/>
  </numFmts>
  <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="5">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
    <xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
    <xf numFmtId="166" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
    <xf numFmtId="167" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>`),
    },
    {
      path: 'xl/worksheets/sheet1.xml',
      content: encoder.encode(worksheetXml(columns, rows)),
    },
  ];

  return zipStore(files);
}

export function downloadExcelTable<T>({
  filename,
  sheetName,
  columns,
  rows,
}: {
  filename: string;
  sheetName: string;
  columns: ExportColumn<T>[];
  rows: T[];
}) {
  const workbook = buildExcelWorkbook({ sheetName, columns, rows });
  const blob = new Blob(
    [workbook],
    { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
  );
  downloadBlob(blob, `${safeFilename(filename)}.xlsx`);
}
