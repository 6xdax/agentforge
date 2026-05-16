import { useRef, useCallback } from 'react'

export function useTypewriter(onUpdateChat, schedulePersist) {
  const typingTimerRef = useRef(null)
  const typingQueueRef = useRef([])
  const thinkingQueueRef = useRef([])
  const typingThinkingTimerRef = useRef(null)

  const stopTypewriter = useCallback(() => {
    if (typingTimerRef.current) {
      clearTimeout(typingTimerRef.current)
      typingTimerRef.current = null
    }
    typingQueueRef.current = []
  }, [])

  const stopThinkingTypewriter = useCallback(() => {
    if (typingThinkingTimerRef.current) {
      clearTimeout(typingThinkingTimerRef.current)
      typingThinkingTimerRef.current = null
    }
    thinkingQueueRef.current = []
  }, [])

  const stopAll = useCallback(() => {
    stopTypewriter()
    stopThinkingTypewriter()
  }, [stopTypewriter, stopThinkingTypewriter])

  const drainThinkingQueue = useCallback(() => {
    if (typingThinkingTimerRef.current) {
      clearTimeout(typingThinkingTimerRef.current)
      typingThinkingTimerRef.current = null
    }
    if (thinkingQueueRef.current.length === 0) return ''
    const pending = thinkingQueueRef.current.join('')
    thinkingQueueRef.current = []
    return pending
  }, [])

  const runThinkingTypewriter = useCallback((chatId) => {
    if (typingThinkingTimerRef.current || thinkingQueueRef.current.length === 0) return

    const tick = () => {
      const next = thinkingQueueRef.current.shift()
      if (next == null) {
        typingThinkingTimerRef.current = null
        return
      }

      onUpdateChat(chatId, (lastMsg) => {
        if (!lastMsg || lastMsg.role !== 'assistant') return lastMsg
        return { ...lastMsg, thinking: (lastMsg.thinking || '') + next }
      })

      if (thinkingQueueRef.current.length > 0) {
        typingThinkingTimerRef.current = setTimeout(tick, 20) // THINKING_TYPEWRITER_DELAY_MS
      } else {
        typingThinkingTimerRef.current = null
      }
    }
    typingThinkingTimerRef.current = setTimeout(tick, 20)
  }, [onUpdateChat])

  const enqueueThinking = useCallback((text, chatId) => {
    if (!text) return
    thinkingQueueRef.current.push(...Array.from(text))
    runThinkingTypewriter(chatId)
  }, [runThinkingTypewriter])

  const runContentTypewriter = useCallback((chatId) => {
    if (typingTimerRef.current || typingQueueRef.current.length === 0) return

    const tick = () => {
      const nextChar = typingQueueRef.current.shift()
      if (nextChar == null) {
        typingTimerRef.current = null
        return
      }

      const shouldPersistAfterTick = typingQueueRef.current.length === 0

      onUpdateChat(chatId, (lastMsg) => {
        if (!lastMsg || lastMsg.role !== 'assistant') return lastMsg
        return {
          ...lastMsg,
          content: (lastMsg.content || '') + nextChar
        }
      })

      if (shouldPersistAfterTick) {
        // We need to get current chats state to persist - this is a bit tricky
        // For now we'll skip per-tick persistence in the typewriter
      }

      if (typingQueueRef.current.length > 0) {
        typingTimerRef.current = setTimeout(tick, 15) // CONTENT_TYPEWRITER_DELAY_MS
      } else {
        typingTimerRef.current = null
      }
    }
    typingTimerRef.current = setTimeout(tick, 15)
  }, [onUpdateChat])

  const enqueueContent = useCallback((text, chatId) => {
    if (!text) return
    typingQueueRef.current.push(...Array.from(text))
    runContentTypewriter(chatId)
  }, [runContentTypewriter])

  const clearAll = useCallback(() => {
    stopAll()
    typingQueueRef.current = []
    thinkingQueueRef.current = []
  }, [stopAll])

  return {
    enqueueThinking,
    enqueueContent,
    drainThinkingQueue,
    stopTypewriter,
    stopThinkingTypewriter,
    stopAll,
    clearAll
  }
}