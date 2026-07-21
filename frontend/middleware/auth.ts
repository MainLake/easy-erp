/**
 * Authentication middleware — runs on every route navigation.
 *
 * Flow:
 *   1. Skip check on /login (avoids redirect loops)
 *   2. No token → redirect to /login
 *   3. Decode JWT, check exp → attempt refresh or redirect to /login
 *   4. No active_organization_id in JWT → redirect to /select-org
 */
import { decodeJWT } from '../composables/useAuth'

export default defineNuxtRouteMiddleware(async (to) => {
  // Skip auth guard on login and register pages
  if (to.path === '/login' || to.path === '/register') {
    return
  }

  const storedToken = import.meta.client
    ? localStorage.getItem('access_token')
    : null

  if (!storedToken) {
    return navigateTo('/login')
  }

  let payload = decodeJWT(storedToken)
  if (!payload?.exp) {
    return navigateTo('/login')
  }

  const now = Math.floor(Date.now() / 1000)
  if (payload.exp < now) {
    // Token expired — attempt silent refresh
    const { tryRefresh, getAccessToken } = useAuth()
    const refreshed = await tryRefresh()
    if (!refreshed) {
      // Clear state and redirect on failure
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('user')
      return navigateTo('/login')
    }
    // Re-decode the new token for the org check below
    const newToken = getAccessToken()
    if (!newToken) return navigateTo('/login')
    payload = decodeJWT(newToken)
    if (!payload?.exp) return navigateTo('/login')
  }

  // Guard: require active org selection (skip on select-org page itself)
  if (!payload.active_organization_id && to.path !== '/select-org') {
    return navigateTo('/select-org')
  }
})
