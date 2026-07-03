'use client'

import { useRef, useState } from 'react'
import type { ApiEnvelope, SessionData } from './types'

interface UploadAreaProps {
  onUploaded: (session: SessionData) => void
  onNetworkError: () => void
}

export function UploadArea({ onUploaded, onNetworkError }: UploadAreaProps) {
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragActive, setDragActive] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  async function uploadFile(file: File) {
    setUploading(true)
    setError(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch('/api/sessions', { method: 'POST', body: formData })
      const body: ApiEnvelope<SessionData> = await res.json().catch(() => ({ data: null, error: 'Malformed server response' }))
      if (!res.ok || !body.data) {
        setError(body.error ?? describeUploadError(res.status))
        return
      }
      onUploaded(body.data)
    } catch {
      onNetworkError()
    } finally {
      setUploading(false)
    }
  }

  function describeUploadError(status: number): string {
    if (status === 400) return 'Unsupported file type — please upload a CSV or Excel file.'
    if (status === 413) return 'File is too large — please upload a smaller file.'
    return 'Something went wrong reading that file — please try again.'
  }

  function handleFiles(files: FileList | null) {
    const file = files?.[0]
    if (file) void uploadFile(file)
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-16">
      <h1 className="mb-2 text-3xl font-bold tracking-tight">Data Analysis Agent</h1>
      <p className="mb-8 text-sm text-gray-500">
        Upload a CSV or Excel file, then ask plain-English questions about it.
      </p>

      <div
        data-testid="upload-area"
        onDragOver={e => {
          e.preventDefault()
          setDragActive(true)
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={e => {
          e.preventDefault()
          setDragActive(false)
          handleFiles(e.dataTransfer.files)
        }}
        className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-10 text-center transition-colors ${
          dragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300 bg-white'
        }`}
      >
        <p className="mb-4 text-sm text-gray-600">Drag and drop your CSV or Excel file here</p>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
        >
          {uploading ? 'Uploading…' : 'Browse files'}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx,.xls"
          data-testid="file-input"
          className="hidden"
          onChange={e => handleFiles(e.target.files)}
        />
      </div>

      {error && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700" data-testid="upload-error">
          {error}
        </div>
      )}
    </div>
  )
}
