import * as XLSX from 'xlsx'
import { s } from './helpers'

export function buildExportRows(
  posts: Record<string, any>[],
  headers: string[],
  edits: Record<string, Record<string, string>>,
): Record<string, string>[] {
  return posts.map(post => {
    const rowId = s(post['Row #'])
    const row: Record<string, string> = {}
    for (const h of headers) {
      row[h] = edits[rowId]?.[h] !== undefined ? edits[rowId][h] : s(post[h])
    }
    return row
  })
}

export function exportExcel(
  posts: Record<string, any>[],
  headers: string[],
  edits: Record<string, Record<string, string>>,
  filename: string,
) {
  const rows = buildExportRows(posts, headers, edits)
  const ws = XLSX.utils.json_to_sheet(rows, { header: headers })
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, 'Posts')
  XLSX.writeFile(wb, `${filename}.xlsx`)
}
