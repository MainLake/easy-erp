/**
 * Authentication state and actions.
 *
 * Singleton state is defined at module level so every component
 * that calls useAuth() shares the same reactive user and tokens.
 */

import { ref, computed } from 'vue'

// ---- interfaces ----

export interface Organization {
  id: string
  name: string
  tax_id?: string
}

export interface OrganizationRole {
  id: string
  name: string
}

export interface OrganizationMembership {
  id: string
  is_default: boolean
  organization: Organization
  role: OrganizationRole
}

export interface User {
  id: string
  email: string
  full_name: string
  role: string
  memberships?: OrganizationMembership[]
  active_membership?: OrganizationMembership | null
}

export interface JwtPayload {
  exp: number
  active_organization_id?: string
  [key: string]: unknown
}

export interface RegisterPayload {
  email: string
  password: string
  full_name: string
  org_name: string
  org_tax_id?: string
}

// ---- utility functions ----

/**
 * Decode a JWT token payload without external libraries.
 * Uses atob (browser + Node 16+) with Buffer fallback for older Node.
 */
export function decodeJWT<T extends Record<string, unknown> = JwtPayload>(token: string): T | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    const payload = parts[1]
    // atob is available globally in browsers and Node 16+
    const decoded = typeof atob !== 'undefined'
      ? atob(payload)
      : Buffer.from(payload, 'base64').toString('utf-8')
    return JSON.parse(decoded) as T
  } catch {
    return null
  }
}

// ---- module-level reactive state ----

const user = ref<User | null>(null)
const accessToken = ref<string | null>(null)
const refreshToken = ref<string | null>(null)

// ---- computed ----

/**
 * Derive the active organization from user.active_membership.
 * Returns undefined when no org is selected (pre-selection state).
 */
export const activeOrg = computed(() => user.value?.active_membership?.organization)

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

  /**
   * Saves tokens to localStorage and updates module-level refs.
   */
  function persistTokens(access: string, refresh?: string): void {
    accessToken.value = access
    localStorage.setItem('access_token', access)
    if (refresh) {
      refreshToken.value = refresh
      localStorage.setItem('refresh_token', refresh)
    }
  }

  /**
   * Self-service registration: creates user + org + role, returns JWT.
   * Auto-login flow: persist tokens → fetch user → set active_membership
   * (exactly one org) → navigate to /.
   */
  async function register(payload: RegisterPayload): Promise<void> {
    const response = await fetch(`${config.public.apiBase}/auth/register/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })

    if (!response.ok) {
      const envelope = await response.json()
      const msg = envelope?.errors?.[0]?.message
        || envelope?.data?.detail
        || envelope?.detail
        || 'Registration failed'
      throw new Error(msg)
    }

    const envelope = await response.json()
    const tokens = envelope.data ?? envelope
    persistTokens(tokens.access, tokens.refresh)

    // Fetch user profile after registration
    await fetchUser()

    // After registration, exactly one org is created
    const memberships = user.value?.memberships ?? []
    if (memberships.length === 0) {
      throw new Error('La cuenta se creó pero no se encontró la organización. Contactá al administrador.')
    }

    user.value = { ...user.value!, active_membership: memberships[0] }
    localStorage.setItem('user', JSON.stringify(user.value))
    await navigateTo('/')
  }

  /**
   * Authenticate user with email/password.
   * Routes post-login based on memberships:
   *   0 orgs → throws error
   *   1 org  → auto-set active_membership, redirect to /
   *   2+     → redirect to /select-org
   */
  async function login(email: string, password: string): Promise<void> {
    const response = await fetch(`${config.public.apiBase}/auth/login/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })

    if (!response.ok) {
      const envelope = await response.json()
      const msg = envelope?.errors?.[0]?.message
        || envelope?.data?.detail
        || envelope?.detail
        || 'Login failed'
      throw new Error(msg)
    }

    const envelope = await response.json()
    const tokens = envelope.data ?? envelope
    persistTokens(tokens.access, tokens.refresh)

    // Fetch user profile after login
    await fetchUser()

    // Post-login routing based on memberships (spec A7, U3, U4)
    const memberships = user.value?.memberships ?? []
    if (memberships.length === 0) {
      throw new Error('No tenés organizaciones asignadas. Contactá al administrador.')
    }

    if (memberships.length === 1) {
      user.value = { ...user.value!, active_membership: memberships[0] }
      localStorage.setItem('user', JSON.stringify(user.value))
      await navigateTo('/')
    } else {
      const defaultMembership = memberships.find(m => m.is_default) ?? memberships[0]
      user.value = { ...user.value!, active_membership: defaultMembership }
      localStorage.setItem('user', JSON.stringify(user.value))
      await navigateTo('/select-org')
    }
  }

  /**
   * Fetch current user from /users/me/.
   * Parses the API envelope {data: {...}} and preserves
   * active_membership if it still exists in the fresh data.
   */
  async function fetchUser(): Promise<void> {
    const prevActiveMembership = user.value?.active_membership
    const response = await fetch(`${config.public.apiBase}/users/me/`, {
      headers: { Authorization: `Bearer ${accessToken.value}` },
    })

    if (response.ok) {
      const envelope = await response.json()
      const userData: User = envelope.data ?? envelope

      // Preserve active_membership if the org still exists in membership list
      if (prevActiveMembership && userData.memberships) {
        const stillValid = userData.memberships.find(
          (m) => m.organization.id === prevActiveMembership.organization.id,
        )
        userData.active_membership = stillValid ?? null
      } else if (userData.memberships && userData.memberships.length > 0) {
        // If no previous active, try is_default then first
        userData.active_membership =
          userData.memberships.find(m => m.is_default) ?? userData.memberships[0]
      }

      user.value = userData
      localStorage.setItem('user', JSON.stringify(userData))
    }
  }

  /**
   * Attempt silent token refresh.
   * Updates access token on success. Returns true if refresh succeeded.
   */
  async function tryRefresh(): Promise<boolean> {
    if (!refreshToken.value) return false
    try {
      const response = await fetch(`${config.public.apiBase}/auth/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh: refreshToken.value }),
      })
      if (!response.ok) return false
      const envelope = await response.json()
      const data = envelope.data ?? envelope
      if (data.access) {
        persistTokens(data.access, data.refresh)
      }
      return true
    } catch {
      return false
    }
  }

  /**
   * Switch the active organization.
   * Calls /auth/switch-org/, replaces tokens, re-fetches user,
   * and sets active_membership to the selected org.
   */
  async function switchOrg(orgId: string): Promise<void> {
    const response = await fetch(`${config.public.apiBase}/auth/switch-org/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${accessToken.value}`,
      },
      body: JSON.stringify({ organization_id: orgId }),
    })

    if (!response.ok) {
      const envelope = await response.json()
      const msg = envelope?.errors?.[0]?.message
        || envelope?.data?.detail
        || envelope?.detail
        || 'No se pudo cambiar de organización'
      throw new Error(msg)
    }

    const envelope = await response.json()
    const tokens = envelope.data ?? envelope
    persistTokens(tokens.access, tokens.refresh)

    await fetchUser()

    // Set active membership to switched org
    if (user.value?.memberships) {
      const match = user.value.memberships.find(m => m.organization.id === orgId)
      user.value = { ...user.value, active_membership: match ?? null }
      localStorage.setItem('user', JSON.stringify(user.value))
    }
  }

  /**
   * Hydrate auth state on app mount.
   * Decodes stored JWT, checks expiry, attempts refresh if expired,
   * fetches user profile if token is valid.
   * Returns true if auth state was successfully restored.
   *
   * Call this from your root layout/component's onMounted.
   */
  async function initAuth(): Promise<boolean> {
    const storedToken = import.meta.client ? localStorage.getItem('access_token') : null
    if (!storedToken) return false

    const payload = decodeJWT(storedToken)
    if (!payload?.exp) {
      // Token is malformed — clear and bail
      accessToken.value = null
      refreshToken.value = null
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      return false
    }

    const now = Math.floor(Date.now() / 1000)
    if (payload.exp < now) {
      const refreshed = await tryRefresh()
      if (!refreshed) {
        logout()
        return false
      }
    }

    await fetchUser()
    return user.value != null
  }

  /**
   * Clear all auth state and redirect to login.
   */
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
    register,
    logout,
    fetchUser,
    initAuth,
    switchOrg,
    getAccessToken,
    getRefreshToken,
    tryRefresh,
  }
}
