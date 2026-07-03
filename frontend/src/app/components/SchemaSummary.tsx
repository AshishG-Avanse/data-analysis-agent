import type { SessionData } from './types'
import { WarningsBanner } from './WarningsBanner'

export function SchemaSummary({ session, onReset }: { session: SessionData; onReset: () => void }) {
  return (
    <div className="space-y-4 rounded-lg border border-gray-200 bg-white p-4 shadow-sm" data-testid="schema-summary">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-gray-900">{session.filename}</p>
          <p className="text-xs text-gray-500" data-testid="schema-counts">
            {session.row_count.toLocaleString()} rows &middot; {session.column_count} columns
          </p>
        </div>
        <button
          type="button"
          onClick={onReset}
          className="shrink-0 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
        >
          Upload a new file
        </button>
      </div>

      <div className="max-h-40 overflow-y-auto rounded-lg border border-gray-100">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-gray-50 text-gray-500">
            <tr>
              <th className="px-3 py-1.5 font-medium">Column</th>
              <th className="px-3 py-1.5 font-medium">Type</th>
            </tr>
          </thead>
          <tbody>
            {session.schema_profile.columns.map(col => (
              <tr key={col.name} className="border-t border-gray-100">
                <td className="px-3 py-1.5 text-gray-800">{col.name}</td>
                <td className="px-3 py-1.5 text-gray-500">{col.dtype}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <WarningsBanner warnings={session.warnings} />
    </div>
  )
}
