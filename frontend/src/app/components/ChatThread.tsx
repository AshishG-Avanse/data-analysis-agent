import type { ChatTurn } from './types'
import { AnswerBubble } from './AnswerBubble'

export function ChatThread({ turns }: { turns: ChatTurn[] }) {
  if (turns.length === 0) {
    return (
      <p className="py-10 text-center text-sm text-gray-400">
        Ask a question about your file to get started.
      </p>
    )
  }

  return (
    <div className="space-y-6" data-testid="chat-thread">
      {turns.map(turn => (
        <AnswerBubble key={turn.id} turn={turn} />
      ))}
    </div>
  )
}
