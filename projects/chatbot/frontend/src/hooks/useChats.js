import { useState, useEffect, useCallback, useRef } from 'react'
import { apiListSessions, apiDeleteSession, apiGetHistory, parseHistoryToMessages } from '../api'

const STORAGE_KEY = 'agentforge_chats_v3'
const PERSIST_DEBOUNCE_MS = 500

function loadChatsFromStorage() {
  const stored = localStorage.getItem(STORAGE_KEY)
  let initialChats = {}
  let initialChatId = null

  if (stored) {
    try {
      const parsed = JSON.parse(stored)
      const lastActive = localStorage.getItem('lastActiveChat')
      if (lastActive && parsed[lastActive]) {
        initialChats = parsed
        initialChatId = lastActive
      } else {
        const firstKey = Object.keys(parsed)[0]
        if (firstKey) {
          initialChats = parsed
          initialChatId = firstKey
        }
      }
    } catch { /* ignore */ }
  }

  return { initialChats, initialChatId }
}

export function useChats(authToken, onAuthExpired) {
  const [chats, setChats] = useState({})
  const [currentChatId, setCurrentChatId] = useState(null)

  const persistTimerRef = useRef(null)
  const persistSnapshotRef = useRef(null)
  const historyMergedRef = useRef(false)

  // Load chats from localStorage on mount
  useEffect(() => {
    const { initialChats, initialChatId } = loadChatsFromStorage()
    setChats(initialChats)
    setCurrentChatId(initialChatId)

    if (Object.keys(initialChats).length === 0) {
      const chatId = Date.now().toString()
      setChats({ [chatId]: { id: chatId, title: '新对话', createdAt: new Date().toISOString(), messages: [] } })
      setCurrentChatId(chatId)
    }
  }, [])

  // Merge server sessions when auth changes
  useEffect(() => {
    if (!authToken || historyMergedRef.current) return
    historyMergedRef.current = true

    apiListSessions(authToken).then(data => {
      if (data.sessions && data.sessions.length > 0) {
        setChats(prev => {
          const updated = { ...prev }
          data.sessions.forEach(session => {
            const chatId = session.chat_id
            if (updated[chatId]) {
              updated[chatId] = { ...updated[chatId], title: session.title }
            } else {
              updated[chatId] = {
                id: chatId,
                title: session.title,
                createdAt: new Date().toISOString(),
                messages: []
              }
            }
          })
          return updated
        })
      }
    }).catch(e => {
      if (e?.status === 401) {
        onAuthExpired?.()
        return
      }
      console.error('Failed to load session list:', e)
    })
  }, [authToken, onAuthExpired])

  const persistChatsNow = useCallback((newChats) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(newChats))
  }, [])

  const schedulePersistChats = useCallback((newChats) => {
    persistSnapshotRef.current = newChats
    if (persistTimerRef.current) return

    persistTimerRef.current = setTimeout(() => {
      persistTimerRef.current = null
      if (persistSnapshotRef.current) {
        persistChatsNow(persistSnapshotRef.current)
        persistSnapshotRef.current = null
      }
    }, PERSIST_DEBOUNCE_MS)
  }, [persistChatsNow])

  const flushPersistChats = useCallback(() => {
    if (persistTimerRef.current) {
      clearTimeout(persistTimerRef.current)
      persistTimerRef.current = null
    }
    if (persistSnapshotRef.current) {
      persistChatsNow(persistSnapshotRef.current)
      persistSnapshotRef.current = null
    }
  }, [persistChatsNow])

  const createNewChat = useCallback(() => {
    const chatId = Date.now().toString()
    const newChat = {
      id: chatId,
      title: '新对话',
      createdAt: new Date().toISOString(),
      messages: []
    }
    setChats(prev => {
      const updated = { ...prev, [chatId]: newChat }
      schedulePersistChats(updated)
      return updated
    })
    setCurrentChatId(chatId)
    return chatId
  }, [schedulePersistChats])

  const switchChat = useCallback((chatId) => {
    setCurrentChatId(chatId)
    localStorage.setItem('lastActiveChat', chatId)
  }, [])

  const loadHistoryForChat = useCallback((chatId, token) => {
    setChats(prev => {
      const chat = prev[chatId]
      if (chat && chat.messages.length === 0) {
        apiGetHistory(token, 100, chatId).then(data => {
          const newMessages = parseHistoryToMessages(data)
          if (newMessages.length > 0) {
            setChats(currentChats => {
              const currentChat = currentChats[chatId]
              if (!currentChat || currentChat.messages.length > 0) return currentChats
              return {
                ...currentChats,
                [chatId]: { ...currentChat, messages: newMessages }
              }
            })
          }
        }).catch(e => {
          if (e?.status === 401) {
            onAuthExpired?.()
            return
          }
          console.error(`Failed to load history for ${chatId}:`, e)
        })
      }
      return prev
    })
  }, [onAuthExpired])

  const deleteChatById = useCallback(async (chatId, token) => {
    if (token && chatId !== 'server_history') {
      try {
        await apiDeleteSession(token, chatId)
      } catch (err) {
        console.error('Failed to delete session on server:', err)
      }
    }
    setChats(prev => {
      const updated = { ...prev }
      delete updated[chatId]
      schedulePersistChats(updated)
      return updated
    })
    return chatId
  }, [schedulePersistChats])

  const updateChatTitleById = useCallback((chatId, firstMessage) => {
    const title = firstMessage.substring(0, 30) + (firstMessage.length > 30 ? '...' : '')
    setChats(prev => {
      const updated = {
        ...prev,
        [chatId]: { ...prev[chatId], title }
      }
      schedulePersistChats(updated)
      return updated
    })
  }, [schedulePersistChats])

  const addMessageToChat = useCallback((chatId, message) => {
    setChats(prev => {
      const chat = prev[chatId]
      if (!chat) return prev
      const updated = {
        ...prev,
        [chatId]: {
          ...chat,
          messages: [...chat.messages, message]
        }
      }
      schedulePersistChats(updated)
      return updated
    })
  }, [schedulePersistChats])

  const updateLastMessageInChat = useCallback((chatId, updateFn) => {
    setChats(prev => {
      const chat = prev[chatId]
      if (!chat || chat.messages.length === 0) return prev
      const messages = [...chat.messages]
      const lastIndex = messages.length - 1
      messages[lastIndex] = updateFn(messages[lastIndex])
      return {
        ...prev,
        [chatId]: { ...chat, messages }
      }
    })
  }, [])

  const clearChatAndCreateNew = useCallback(() => {
    const chatId = Date.now().toString()
    setChats({ [chatId]: { id: chatId, title: '新对话', createdAt: new Date().toISOString(), messages: [] } })
    setCurrentChatId(chatId)
    // Clear server_history from localStorage
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      try {
        const chats = JSON.parse(stored)
        delete chats['server_history']
        localStorage.setItem(STORAGE_KEY, JSON.stringify(chats))
      } catch { /* ignore */ }
    }
    return chatId
  }, [])

  return {
    chats,
    currentChatId,
    setCurrentChatId,
    createNewChat,
    switchChat,
    loadHistoryForChat,
    deleteChatById,
    updateChatTitleById,
    addMessageToChat,
    updateLastMessageInChat,
    clearChatAndCreateNew,
    schedulePersistChats,
    flushPersistChats
  }
}