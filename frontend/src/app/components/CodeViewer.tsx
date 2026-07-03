'use client'

import { useState } from 'react'

export function CodeViewer({ code }: { code: string }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded(e => !e)}
        className="text-xs font-medium text-blue-600 hover:text-blue-800 hover:underline"
      >
        {expanded ? 'Hide code' : 'View code'}
      </button>
      {expanded && (
        <pre className="mt-2 overflow-x-auto rounded-lg border border-gray-200 bg-gray-900 p-3 text-xs text-gray-100">
          <code>{code}</code>
        </pre>
      )}
    </div>
  )
}
