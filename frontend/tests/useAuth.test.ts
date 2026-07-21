import { describe, it, expect, beforeEach } from 'vitest'

describe('useAuth', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('starts with no authenticated user', async () => {
    const { useAuth } = await import('../composables/useAuth')
    const auth = useAuth()
    expect(auth.user.value).toBeNull()
    expect(auth.getAccessToken()).toBeNull()
    expect(auth.getRefreshToken()).toBeNull()
  })

  it('logout clears all state', async () => {
    const { useAuth } = await import('../composables/useAuth')
    const auth = useAuth()
    auth.logout()
    expect(auth.user.value).toBeNull()
    expect(auth.getAccessToken()).toBeNull()
    expect(auth.getRefreshToken()).toBeNull()
  })
})
