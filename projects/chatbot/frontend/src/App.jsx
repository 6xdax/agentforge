import { useState, useRef, useCallback } from 'react'
import AuthModal from './components/AuthModal'
import Sidebar from './components/Sidebar'
import MainContent from './components/MainContent'
import { apiUploadUserFile } from './api'
import { useAuth } from './hooks/useAuth'
import { useChats } from './hooks/useChats'
import { useTypewriter } from './hooks/useTypewriter'
import { useSSE } from './hooks/useSSE'

export default function App() {
  const [isGenerating, setIsGenerating] = useState(false)
  const [thinkingEnabled, setThinkingEnabled] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const hasStreamedContentRef = useRef(false)

  const {
    authToken,
    authUser,
    authLoading,
    authError,
    showAuthModal,
    authMode,
    login,
    register,
    logout,
    switchMode,
    openAuthModal,
    closeAuthModal
  } = useAuth()

  const handleAuthExpired = useCallback(() => {
    logout()
    openAuthModal('login')
  }, [logout, openAuthModal])

  const {
    chats,
    currentChatId,
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
  } = useChats(authToken, handleAuthExpired)

  const typewriter = useTypewriter(updateLastMessageInChat, schedulePersistChats)

  const { send, abort } = useSSE({
    onContent: (text, chatId) => {
      hasStreamedContentRef.current = true
      typewriter.enqueueContent(text, chatId)
    },
    onThinking: (text, chatId) => {
      typewriter.enqueueThinking(text, chatId)
    },
    onToolCall: (json, chatId) => {
      updateLastMessageInChat(chatId, (lastMsg) => {
        if (!lastMsg.tool_traces) lastMsg.tool_traces = []
        const toolArguments = json.arguments ?? json.args ?? null
        const callId = String(json.tool_call_id || `call_${Date.now()}_${lastMsg.tool_traces.length}`)
        return {
          ...lastMsg,
          tool_calls: [...(lastMsg.tool_calls || []), json.tool_name].filter(Boolean),
          tool_traces: [...lastMsg.tool_traces, {
            tool_call_id: callId,
            tool_name: json.tool_name || 'unknown_tool',
            arguments: toolArguments,
            result: null,
            status: 'running'
          }]
        }
      })
    },
    onToolResult: (json, chatId) => {
      updateLastMessageInChat(chatId, (lastMsg) => {
        if (!lastMsg.tool_traces) lastMsg.tool_traces = []
        const resultCallId = json.tool_call_id ? String(json.tool_call_id) : null
        let targetIndex = lastMsg.tool_traces.findIndex(item =>
          resultCallId && String(item.tool_call_id || '') === resultCallId
        )
        if (targetIndex < 0 && json.tool_name) {
          targetIndex = lastMsg.tool_traces.findIndex(item =>
            item.tool_name === json.tool_name && item.status !== 'completed'
          )
        }
        if (targetIndex >= 0) {
          const nextTraces = [...lastMsg.tool_traces]
          nextTraces[targetIndex] = {
            ...nextTraces[targetIndex],
            result: json.result,
            tool_name: json.tool_name || nextTraces[targetIndex].tool_name,
            status: 'completed'
          }
          return { ...lastMsg, tool_traces: nextTraces }
        }
        return lastMsg
      })
    },
    onDone: (json, chatId) => {
      const pendingThinking = typewriter.drainThinkingQueue()
      updateLastMessageInChat(chatId, (lastMsg) => {
        let updated = { ...lastMsg, thinkingCompleted: true }
        if (pendingThinking) {
          updated.thinking = (lastMsg.thinking || '') + pendingThinking
        }
        if (json.usage) {
          updated.usage = json.usage
        }
        return updated
      })
    },
    onError: (json, chatId) => {
      typewriter.stopAll()
      updateLastMessageInChat(chatId, (lastMsg) => ({
        ...lastMsg,
        content: `Error: ${json.message}`
      }))
    }
  })

  const handleCreateNewChat = useCallback(() => {
    createNewChat()
    setSidebarOpen(false)
  }, [createNewChat])

  const handleSwitchChat = useCallback((chatId) => {
    switchChat(chatId)
    if (authToken && chatId && chatId !== 'server_history') {
      loadHistoryForChat(chatId, authToken)
    }
  }, [switchChat, authToken, loadHistoryForChat])

  const handleDeleteChat = useCallback(async (chatId, e) => {
    e?.stopPropagation()
    await deleteChatById(chatId, authToken)
    if (currentChatId === chatId) {
      const remainingChats = Object.keys(chats).filter(k => k !== chatId)
      if (remainingChats.length > 0) {
        handleSwitchChat(remainingChats[0])
      } else {
        handleCreateNewChat()
      }
    }
  }, [currentChatId, chats, deleteChatById, authToken, handleSwitchChat, handleCreateNewChat])

  const handleLogout = useCallback(() => {
    logout()
    clearChatAndCreateNew()
  }, [logout, clearChatAndCreateNew])

  const sendMessage = useCallback(async (text, uploadedFiles = []) => {
    if (!text.trim() || isGenerating) return
    if (!authToken) {
      openAuthModal('login')
      return
    }

    typewriter.stopAll()
    hasStreamedContentRef.current = false

    const userMsg = {
      role: 'user',
      content: text,
      attachments: uploadedFiles.map((item) => ({
        fileName: item.fileName,
        savedPath: item.savedPath,
        size: item.size
      })),
      timestamp: new Date().toISOString()
    }

    addMessageToChat(currentChatId, userMsg)

    const currentChat = chats[currentChatId]
    if (currentChat && currentChat.messages.length === 0) {
      updateChatTitleById(currentChatId, text)
    }

    setIsGenerating(true)
    setSidebarOpen(false)

    const assistantMsg = {
      role: 'assistant',
      content: '',
      thinking: '',
      timestamp: new Date().toISOString(),
      tool_calls: [],
      tool_traces: [],
      thinkingCompleted: false
    }

    addMessageToChat(currentChatId, assistantMsg)

    try {
      const baseUrl = import.meta.env.BASE_URL || '/'
      const apiUrl = `${baseUrl}api/chat`

      await send({
        message: text,
        thinking: thinkingEnabled,
        chatId: currentChatId,
        authToken,
        apiUrl,
        filePaths: uploadedFiles.map((item) => item.savedPath),
        fileAttachments: uploadedFiles.map((item) => ({
          file_name: item.fileName,
          saved_path: item.savedPath,
          size: item.size
        }))
      })

      schedulePersistChats(chats)
    } catch (error) {
      if (error.name !== 'AbortError') {
        if (error.status === 401) {
          handleAuthExpired()
          return
        }
        typewriter.stopAll()
        console.error('Error:', error)
        updateLastMessageInChat(currentChatId, (lastMsg) => ({
          ...lastMsg,
          content: '错误: ' + error.message
        }))
        schedulePersistChats(chats)
      }
    } finally {
      flushPersistChats()
      setIsGenerating(false)
    }
  }, [
    authToken,
    isGenerating,
    thinkingEnabled,
    currentChatId,
    chats,
    typewriter,
    addMessageToChat,
    updateChatTitleById,
    updateLastMessageInChat,
    schedulePersistChats,
    flushPersistChats,
    handleAuthExpired,
    openAuthModal,
    send
  ])

  const stopGeneration = useCallback(() => {
    abort()
    typewriter.stopAll()
  }, [abort, typewriter])

  const uploadFile = useCallback(async (file) => {
    if (!authToken) {
      openAuthModal('login')
      throw new Error('请先登录')
    }

    let data
    try {
      data = await apiUploadUserFile(authToken, file)
    } catch (error) {
      if (error.status === 401) {
        handleAuthExpired()
      }
      throw error
    }

    return {
      fileName: data.file_name,
      savedPath: data.saved_path,
      size: data.size
    }
  }, [authToken, openAuthModal, handleAuthExpired])

  const currentChat = chats[currentChatId]

  return (
    <div className="app-container">
      <div
        className={`sidebar-overlay ${sidebarOpen ? 'active' : ''}`}
        onClick={() => setSidebarOpen(false)}
      />
      {showAuthModal && (
        <AuthModal
          mode={authMode}
          onModeSwitch={switchMode}
          onSubmit={authMode === 'login' ? login : register}
          loading={authLoading}
          error={authError}
        />
      )}
      <Sidebar
        chats={chats}
        currentChatId={currentChatId}
        onSwitchChat={handleSwitchChat}
        onDeleteChat={handleDeleteChat}
        onNewChat={handleCreateNewChat}
        isOpen={sidebarOpen}
        authUser={authUser}
        onLogout={handleLogout}
        onLoginClick={() => openAuthModal('login')}
        onRegisterClick={() => openAuthModal('register')}
      />
      <MainContent
        chat={currentChat}
        isGenerating={isGenerating}
        thinkingEnabled={thinkingEnabled}
        onSendMessage={sendMessage}
        onUploadFile={uploadFile}
        onStopGeneration={stopGeneration}
        onToggleThinking={() => setThinkingEnabled(!thinkingEnabled)}
        onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        isAuthenticated={!!authToken}
        onLoginClick={() => openAuthModal('login')}
      />
    </div>
  )
}