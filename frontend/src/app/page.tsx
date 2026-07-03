'use client'

import { useState } from 'react'
import type { ApiEnvelope, ChatTurn, QuestionResponseData, SessionData } from './components/types'
import { UploadArea } from './components/UploadArea'
import { SchemaSummary } from './components/SchemaSummary'
import { ChatThread } from './components/ChatThread'
import { QuestionInput } from './components/QuestionInput'

export default function Home() {
  const [session, setSession] = useState<SessionData | null>(null)
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [networkError, setNetworkError] = useState<string | null>(null)
  const [questionInFlight, setQuestionInFlight] = useState(false)

  function handleReset() {
    setSession(null)
    setTurns([])
  }

  function handleNetworkError() {
    setNetworkError("Can't reach the server — is it running?")
  }

  async function handleAskQuestion(question: string) {
    if (!session) return
    setNetworkError(null)
    setQuestionInFlight(true)

    const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`
    setTurns(prev => [...prev, { id, question, state: 'loading' }])

    try {
      const res = await fetch(`/api/sessions/${session.session_id}/questions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })
      const body: ApiEnvelope<QuestionResponseData> = await res
        .json()
        .catch(() => ({ data: null, error: 'Malformed server response' }))

      if (!res.ok || body.error || !body.data) {
        setTurns(prev =>
          prev.map(t =>
            t.id === id
              ? {
                  ...t,
                  state: 'error',
                  errorMessage: body.error ?? 'Something went wrong answering that — try again.',
                }
              : t
          )
        )
        return
      }

      const data = body.data
      setTurns(prev =>
        prev.map(t =>
          t.id === id
            ? {
                ...t,
                state: data.status,
                answer: data.answer,
                code: data.code,
              }
            : t
        )
      )
    } catch {
      // Network failure: surface the top-level banner and drop the pending turn.
      setTurns(prev => prev.filter(t => t.id !== id))
      handleNetworkError()
    } finally {
      setQuestionInFlight(false)
    }
  }

  return (
    <main className="min-h-screen">
      {networkError && (
        <div
          className="border-b border-red-200 bg-red-50 px-4 py-2 text-center text-sm text-red-700"
          data-testid="network-error-banner"
        >
          {networkError}
        </div>
      )}

      {!session ? (
        <UploadArea onUploaded={setSession} onNetworkError={handleNetworkError} />
      ) : (
        <div className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10">
          <SchemaSummary session={session} onReset={handleReset} />
          <ChatThread turns={turns} />
          <QuestionInput disabled={questionInFlight} onSubmit={handleAskQuestion} />
        </div>
      )}
    </main>
  )
}
