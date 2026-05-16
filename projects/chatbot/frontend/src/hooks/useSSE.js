import { useRef, useCallback } from 'react'

export function useSSE({
  onContent,
  onThinking,
  onToolCall,
  onToolResult,
  onDone,
  onError
}) {
  const abortControllerRef = useRef(null)

  const send = useCallback(async ({ message, thinking, chatId, authToken, apiUrl }) => {
    abortControllerRef.current = new AbortController()

    const response = await fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({ message, thinking, chat_id: chatId }),
      signal: abortControllerRef.current.signal
    })

    if (!response.ok) {
      throw new Error('HTTP ' + response.status)
    }

    if (response.body) {
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = null

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.substring(7).trim()
          } else if (line.startsWith('data: ')) {
            const data = line.substring(6).trim()
            if (!data) continue

            try {
              const json = JSON.parse(data)

              if (currentEvent === 'content') {
                onContent?.(json.content, chatId)
              } else if (currentEvent === 'thinking') {
                onThinking?.(json.content, chatId)
              } else if (currentEvent === 'tool_call') {
                onToolCall?.(json, chatId)
              } else if (currentEvent === 'tool_result') {
                onToolResult?.(json, chatId)
              } else if (currentEvent === 'done') {
                onDone?.(json, chatId)
              } else if (currentEvent === 'error') {
                onError?.(json, chatId)
              }
            } catch (e) {
              console.error('SSE parse error:', e)
            }
          }
        }
      }
    } else {
      const data = await response.json()
      if (data.response) {
        onContent?.(data.response, chatId)
      }
      onDone?.({ content: data.response }, chatId)
    }
  }, [onContent, onThinking, onToolCall, onToolResult, onDone, onError])

  const abort = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
  }, [])

  return { send, abort }
}