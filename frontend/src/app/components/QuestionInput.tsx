'use client'

import { useState } from 'react'

interface QuestionInputProps {
  disabled: boolean
  onSubmit: (question: string) => void
}

export function QuestionInput({ disabled, onSubmit }: QuestionInputProps) {
  const [value, setValue] = useState('')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const question = value.trim()
    if (!question) return
    onSubmit(question)
    setValue('')
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={value}
        onChange={e => setValue(e.target.value)}
        disabled={disabled}
        placeholder="Ask a question about your file…"
        data-testid="question-input"
        className="flex-1 rounded-lg border border-gray-300 px-3 py-2.5 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        data-testid="question-submit"
        className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
      >
        Ask
      </button>
    </form>
  )
}
