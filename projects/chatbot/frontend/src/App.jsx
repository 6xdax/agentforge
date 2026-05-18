import { useState, useRef, useCallback } from 'react'
import AuthModal from './components/AuthModal'
import ConfigModal from './components/ConfigModal'
import Sidebar from './components/Sidebar'
import MainContent from './components/MainContent'
import { apiGetConfig, apiUpdateConfig, apiUploadUserFile } from './api'
import { useAuth } from './hooks/useAuth'
import { useChats } from './hooks/useChats'
import { useTypewriter } from './hooks/useTypewriter'
import { useSSE } from './hooks/useSSE'

export default function App() {
  const [isGenerating, setIsGenerating] = useState(false)
  const [thinkingEnabled, setThinkingEnabled] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [activeView, setActiveView] = useState('chat')
  const [configModalVisible, setConfigModalVisible] = useState(false)
  const [activeConfigTab, setActiveConfigTab] = useState('tools')
  const [configState, setConfigState] = useState({
    tools: { items: [], loading: false, saving: false, loaded: false },
    mcp: { items: [], loading: false, saving: false, loaded: false },
    skills: { items: [], loading: false, saving: false, loaded: false }
  })

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
    setActiveView('chat')
    setSidebarOpen(false)
  }, [createNewChat])

  const handleSwitchChat = useCallback((chatId) => {
    setActiveView('chat')
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

  const loadConfigTab = useCallback(async (tab) => {
    if (!authToken) {
      openAuthModal('login')
      return
    }

    setConfigState((prev) => ({
      ...prev,
      [tab]: { ...prev[tab], loading: true }
    }))

    try {
      const data = await apiGetConfig(authToken, tab)
      const items = (data.items || []).map((item) => ({
        name: item.name,
        description: item.description || item.path || '',
        enabled: item.enabled !== false
      }))
      setConfigState((prev) => ({
        ...prev,
        [tab]: { ...prev[tab], items, loaded: true, loading: false }
      }))
    } catch (error) {
      setConfigState((prev) => ({
        ...prev,
        [tab]: { ...prev[tab], loading: false }
      }))
      if (error.status === 401) {
        handleAuthExpired()
      }
      throw error
    }
  }, [authToken, openAuthModal, handleAuthExpired])

  const openConfigModal = useCallback(async (tab) => {
    if (!authToken) {
      openAuthModal('login')
      return
    }
    setActiveConfigTab(tab)
    setConfigModalVisible(true)
    try {
      if (!configState[tab]?.loaded) {
        await loadConfigTab(tab)
      }
    } catch (error) {
      console.error('Load config failed:', error)
    }
  }, [authToken, openAuthModal, configState, loadConfigTab])

  const switchConfigTab = useCallback(async (tab) => {
    setActiveConfigTab(tab)
    if (!configState[tab]?.loaded) {
      await loadConfigTab(tab)
    }
  }, [configState, loadConfigTab])

  const toggleConfigItem = useCallback((tab, name, enabled) => {
    setConfigState((prev) => ({
      ...prev,
      [tab]: {
        ...prev[tab],
        items: prev[tab].items.map((item) => (
          item.name === name ? { ...item, enabled } : item
        ))
      }
    }))
  }, [])

  const saveConfigTab = useCallback(async (tab) => {
    if (!authToken) {
      openAuthModal('login')
      return
    }

    const payload = {}
    for (const item of configState[tab].items) {
      payload[item.name] = !!item.enabled
    }

    setConfigState((prev) => ({
      ...prev,
      [tab]: { ...prev[tab], saving: true }
    }))

    try {
      await apiUpdateConfig(authToken, tab, payload)
      setConfigState((prev) => ({
        ...prev,
        [tab]: { ...prev[tab], saving: false }
      }))
    } catch (error) {
      setConfigState((prev) => ({
        ...prev,
        [tab]: { ...prev[tab], saving: false }
      }))
      if (error.status === 401) {
        handleAuthExpired()
      }
      throw error
    }
  }, [authToken, configState, openAuthModal, handleAuthExpired])

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
      <ConfigModal
        visible={configModalVisible}
        activeTab={activeConfigTab}
        onClose={() => setConfigModalVisible(false)}
        onSwitchTab={switchConfigTab}
        state={configState}
        onToggle={toggleConfigItem}
        onSave={saveConfigTab}
      />
      <Sidebar
        chats={chats}
        currentChatId={currentChatId}
        onSwitchChat={handleSwitchChat}
        onDeleteChat={handleDeleteChat}
        onNewChat={handleCreateNewChat}
        onOpenSquare={() => {
          setActiveView('square')
          setSidebarOpen(false)
        }}
        onOpenAiNews={() => {
          setActiveView('ai-news')
          setSidebarOpen(false)
        }}
        isOpen={sidebarOpen}
        authUser={authUser}
        onLogout={handleLogout}
        onLoginClick={() => openAuthModal('login')}
        onRegisterClick={() => openAuthModal('register')}
      />
      <MainContent
        chat={currentChat}
        activeView={activeView}
        isGenerating={isGenerating}
        thinkingEnabled={thinkingEnabled}
        onSendMessage={sendMessage}
        onUploadFile={uploadFile}
        onStopGeneration={stopGeneration}
        onToggleThinking={() => setThinkingEnabled(!thinkingEnabled)}
        onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        isAuthenticated={!!authToken}
        authToken={authToken}
        authUser={authUser}
        onLoginClick={() => openAuthModal('login')}
        onOpenToolConfig={() => openConfigModal('tools')}
        onOpenMcpConfig={() => openConfigModal('mcp')}
        onOpenSkillConfig={() => openConfigModal('skills')}
      />
    </div>
  )
}