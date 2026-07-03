export function WarningsBanner({ warnings }: { warnings: string[] }) {
  if (warnings.length > 0) {
    return (
      <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
        <p className="mb-1 font-medium">File warnings</p>
        <ul className="list-inside list-disc space-y-0.5">
          {warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-3 text-xs text-gray-400">
      File warnings will appear here (Phase 2)
    </div>
  )
}
