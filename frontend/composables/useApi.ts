/**
 * HTTP client wrapper with automatic JWT handling.
 *
 * Attaches the Bearer token to every request. On a 401 response,
 * attempts a silent token refresh before rejecting.
 */
export const useApi = () => {
  const config = useRuntimeConfig()
  const { getAccessToken, getRefreshToken, tryRefresh } = useAuth()

  const request = async (
    endpoint: string,
    options: RequestInit = {},
  ): Promise<Response> => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> || {}),
    }

    const token = getAccessToken()
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }

    let response = await fetch(`${config.public.apiBase}${endpoint}`, {
      ...options,
      headers,
    })

    // Silently attempt token refresh on 401
    if (response.status === 401 && getRefreshToken()) {
      const refreshed = await tryRefresh()
      if (refreshed) {
        headers['Authorization'] = `Bearer ${getAccessToken()}`
        response = await fetch(`${config.public.apiBase}${endpoint}`, {
          ...options,
          headers,
        })
      }
    }

    return response
  }

  return { request }
}
