import type { ChatTurn } from './types'
import { CodeViewer } from './CodeViewer'
import { ChartPlaceholder } from './ChartPlaceholder'
import { TablePlaceholder } from './TablePlaceholder'
import { CostBadge } from './CostBadge'

export function AnswerBubble({ turn }: { turn: ChatTurn }) {
  return (
    <div className="space-y-3">
      {/* Question bubble */}
      <div className="ml-auto max-w-[85%] rounded-lg rounded-br-none bg-blue-600 px-4 py-2.5 text-sm text-white shadow-sm">
        {turn.question}
      </div>

      {/* Answer bubble */}
      <div className="mr-auto max-w-[85%] space-y-3 rounded-lg rounded-bl-none border border-gray-200 bg-white px-4 py-3 text-sm shadow-sm">
        {turn.state === 'loading' && (
          <div className="flex items-center gap-2 text-gray-500" data-testid="answer-spinner">
            <svg className="h-4 w-4 animate-spin text-gray-400" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
            </svg>
            <span>Thinking…</span>
          </div>
        )}

        {turn.state === 'error' && (
          <p className="text-red-700" data-testid="answer-error">
            {turn.errorMessage ?? 'Something went wrong answering that — try again.'}
          </p>
        )}

        {(turn.state === 'completed' || turn.state === 'gave_up') && (
          <>
            <p className="whitespace-pre-wrap text-gray-800" data-testid="answer-text">
              {turn.answer}
            </p>

            {turn.state === 'completed' && turn.code != null && <CodeViewer code={turn.code} />}

            <div className="space-y-2 border-t border-gray-100 pt-3">
              <ChartPlaceholder />
              <TablePlaceholder />
              <CostBadge />
            </div>
          </>
        )}
      </div>
    </div>
  )
}
