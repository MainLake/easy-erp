/**
 * Authentication state and actions.
 *
 * Singleton state is defined at module level so every component
 * that calls useAuth() shares the same reactive user and tokens.
 */

import { ref } from 'vue'

interface User {
  id: string
  email: string
  full_name: string
  role: string
}

// ---- module-level reactive state ----

const user = ref<User | null>(null)
const accessToken = ref<string | null>(null)
const refreshToken = ref<string | null>(null)

// ---- client-only hydration from localStorage ----

if (import.meta.client) {
  accessToken.value = localStorage.getItem('access_token')
  refreshToken.value = localStorage.getItem('refresh_token')
  const stored = localStorage.getItem('user')
  if (stored) {
    try { user.value = JSON.parse(stored) } catch { /* corrupted — ignore */ }
  }
}

// ---- composable ----

export const useAuth = () => {
  const config = useRuntimeConfig()

  const getAccessToken = () => accessToken.value
  const getRefreshToken = () => refreshToken.value

  async function login(email: string, password: string): Promise<void> {
    const response = await fetch(`${config.public.apiBase}/auth/login/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })

    if (!response.ok) {
      throw new Error('Login failed')
    }

    const data = await response.json()
    accessToken.value = data.access
    refreshToken.value = data.refresh
    localStorage.setItem('access_token', data.access)
    localStorage.setItem('refresh_token', data.refresh)

    // Fetch user profile after login
    await fetchUser()
  }

  async function fetchUser(): Promise<void> {
    const response = await fetch(`${config.public.apiBase}/users/me/`, {
      headers: { Authorization: `Bearer ${accessToken.value}` },
    })
    if (response.ok) {
      const data = await response.json()
      user.value = data
      localStorage.setItem('user', JSON.stringify(data))
    }
  }

  async function tryRefresh(): Promise<boolean> {
    if (!refreshToken.value) return false
    try {
      const response = await fetch(`${config.public.apiBase}/auth/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh: refreshToken.value }),
      })
      if (!response.ok) return false
      const data = await response.json()
      accessToken.value = data.access
      localStorage.setItem('access_token', data.access)
      return true
    } catch {
      return false
    }
  }

  function logout(): void {
    accessToken.value = null
    refreshToken.value = null
    user.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user')
    navigateTo('/login')
  }

  return {
    user,
    login,
    logout,
    fetchUser,
    getAccessToken,
    getRefreshToken,
    tryRefresh,
  }
}
