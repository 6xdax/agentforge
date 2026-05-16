import { useState, useCallback } from 'react'
import { apiLogin, apiRegister } from '../api'

const AUTH_TOKEN_KEY = 'agentforge_auth_token'
const AUTH_USER_KEY = 'agentforge_auth_user'

export function useAuth() {
  const [authToken, setAuthToken] = useState(() => localStorage.getItem(AUTH_TOKEN_KEY))
  const [authUser, setAuthUser] = useState(() => localStorage.getItem(AUTH_USER_KEY))
  const [authLoading, setAuthLoading] = useState(false)
  const [authError, setAuthError] = useState('')
  const [showAuthModal, setShowAuthModal] = useState(false)
  const [authMode, setAuthMode] = useState('login')

  const login = useCallback(async (username, password) => {
    setAuthError('')
    setAuthLoading(true)
    try {
      const data = await apiLogin(username, password)
      setAuthToken(data.token)
      setAuthUser(username)
      localStorage.setItem(AUTH_TOKEN_KEY, data.token)
      localStorage.setItem(AUTH_USER_KEY, username)
      setShowAuthModal(false)
      return { success: true }
    } catch (e) {
      setAuthError(e.message)
      return { success: false, error: e.message }
    } finally {
      setAuthLoading(false)
    }
  }, [])

  const register = useCallback(async (username, password) => {
    setAuthError('')
    setAuthLoading(true)
    try {
      await apiRegister(username, password)
      const data = await apiLogin(username, password)
      setAuthToken(data.token)
      setAuthUser(username)
      localStorage.setItem(AUTH_TOKEN_KEY, data.token)
      localStorage.setItem(AUTH_USER_KEY, username)
      setShowAuthModal(false)
      return { success: true }
    } catch (e) {
      setAuthError(e.message)
      return { success: false, error: e.message }
    } finally {
      setAuthLoading(false)
    }
  }, [])

  const logout = useCallback(() => {
    setAuthToken(null)
    setAuthUser(null)
    localStorage.removeItem(AUTH_TOKEN_KEY)
    localStorage.removeItem(AUTH_USER_KEY)
  }, [])

  const switchMode = useCallback(() => {
    setAuthMode(prev => prev === 'login' ? 'register' : 'login')
  }, [])

  const openAuthModal = useCallback((mode = 'login') => {
    setAuthMode(mode)
    setShowAuthModal(true)
  }, [])

  const closeAuthModal = useCallback(() => {
    setShowAuthModal(false)
    setAuthError('')
  }, [])

  return {
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
  }
}