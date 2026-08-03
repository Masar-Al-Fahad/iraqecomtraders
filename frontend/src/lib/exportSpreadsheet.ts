/** Client-side Excel-compatible export (SpreadsheetML) — no backend change. */
export function downloadSpreadsheetMl(
  filename: string,
  title: string,
  headers: string[],
  rows: (string | number)[][],
  metaLines: string[] = []
) {
  const esc = (v: any) =>
    String(v ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');

  const metaXml = metaLines
    .map(
      (line) =>
        `<Row><Cell ss:MergeAcross="${Math.max(headers.length - 1, 0)}"><Data ss:Type="String">${esc(line)}</Data></Cell></Row>`
    )
    .join('');

  const headerXml = `<Row>${headers
    .map((h) => `<Cell><Data ss:Type="String">${esc(h)}</Data></Cell>`)
    .join('')}</Row>`;

  const bodyXml = rows
    .map(
      (row) =>
        `<Row>${row
          .map((cell) => {
            const isNum = typeof cell === 'number';
            return `<Cell><Data ss:Type="${isNum ? 'Number' : 'String'}">${esc(cell)}</Data></Cell>`;
          })
          .join('')}</Row>`
    )
    .join('');

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="Report">
  <Table>
   <Row><Cell ss:MergeAcross="${Math.max(headers.length - 1, 0)}"><Data ss:Type="String">${esc(title)}</Data></Cell></Row>
   ${metaXml}
   ${headerXml}
   ${bodyXml}
  </Table>
 </Worksheet>
</Workbook>`;

  const blob = new Blob([xml], { type: 'application/vnd.ms-excel;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename.endsWith('.xls') ? filename : `${filename}.xls`;
  a.click();
  URL.revokeObjectURL(url);
}
