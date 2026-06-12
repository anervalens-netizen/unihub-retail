export type ExportColumn<T> = {
  header: string;
  value: (row: T) => string | number | null | undefined;
};

function escapeHtml(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '';
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function safeFilename(value: string): string {
  return value
    .trim()
    .replace(/[\\/:*?"<>|]+/g, '-')
    .replace(/\s+/g, '_')
    .slice(0, 120);
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
  const headerHtml = columns.map((column) => `<th>${escapeHtml(column.header)}</th>`).join('');
  const rowsHtml = rows
    .map((row) => (
      `<tr>${columns.map((column) => `<td>${escapeHtml(column.value(row))}</td>`).join('')}</tr>`
    ))
    .join('');

  const html = `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    table { border-collapse: collapse; }
    th, td { border: 1px solid #d9e2ec; padding: 4px 8px; font-family: Arial, sans-serif; font-size: 11px; }
    th { background: #eef2ff; font-weight: 700; }
  </style>
</head>
<body>
  <table>
    <caption>${escapeHtml(sheetName)}</caption>
    <thead><tr>${headerHtml}</tr></thead>
    <tbody>${rowsHtml}</tbody>
  </table>
</body>
</html>`;

  const blob = new Blob([html], { type: 'application/vnd.ms-excel;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${safeFilename(filename)}.xls`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
