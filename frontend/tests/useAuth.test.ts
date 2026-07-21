import { describe, it, expect, beforeEach, vi } from 'vitest'

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

describe('decodeJWT', () => {
  it('decodes a valid JWT payload', async () => {
    const { decodeJWT } = await import('../composables/useAuth')
    // Header: {"alg":"HS256","typ":"JWT"}
    // Payload: {"exp":9999999999,"active_organization_id":"org-1","sub":"user-1"}
    const token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.' +
      'eyJleHAiOjk5OTk5OTk5OTksImFjdGl2ZV9vcmdhbml6YXRpb25faWQiOiJvcmctMSIsInN1YiI6InVzZXItMSJ9.' +
      'fake-signature'
    const payload = decodeJWT(token)
    expect(payload).not.toBeNull()
    expect(payload!.exp).toBe(9999999999)
    expect(payload!.active_organization_id).toBe('org-1')
    expect(payload!.sub).toBe('user-1')
  })

  it('returns null for malformed token', async () => {
    const { decodeJWT } = await import('../composables/useAuth')
    expect(decodeJWT('not-a-jwt')).toBeNull()
    expect(decodeJWT('')).toBeNull()
    expect(decodeJWT('a.b.c.d')).toBeNull()
  })

  it('returns null for invalid base64 payload', async () => {
    const { decodeJWT } = await import('../composables/useAuth')
    // Payload is not valid base64
    const token = 'header.!!not-valid!!.signature'
    expect(decodeJWT(token)).toBeNull()
  })
})

describe('activeOrg', () => {
  it('derives from user.active_membership.organization', async () => {
    const { useAuth, activeOrg } = await import('../composables/useAuth')
    const auth = useAuth()

    // Simulate a user with active_membership set
    auth.user.value = {
      id: 'user-1',
      email: 'test@test.com',
      full_name: 'Test User',
      role: 'Admin',
      active_membership: {
        id: 'mem-1',
        is_default: true,
        organization: { id: 'org-1', name: 'Acme Corp' },
        role: { id: 'role-1', name: 'Admin' },
      },
      memberships: [
        {
          id: 'mem-1',
          is_default: true,
          organization: { id: 'org-1', name: 'Acme Corp' },
          role: { id: 'role-1', name: 'Admin' },
        },
      ],
    } as any

    expect(activeOrg.value).toEqual({ id: 'org-1', name: 'Acme Corp' })
  })

  it('returns undefined when no user', async () => {
    const { useAuth, activeOrg } = await import('../composables/useAuth')
    const auth = useAuth()
    auth.user.value = null
    expect(activeOrg.value).toBeUndefined()
  })
})

describe('initAuth', () => {
  it('returns false when no token stored', async () => {
    const { useAuth } = await import('../composables/useAuth')
    const auth = useAuth()
    const result = await auth.initAuth()
    expect(result).toBe(false)
  })

  it('clears state for malformed token', async () => {
    localStorage.setItem('access_token', 'malformed.jwt.token')
    const { useAuth } = await import('../composables/useAuth')
    const auth = useAuth()
    const result = await auth.initAuth()
    expect(result).toBe(false)
    expect(auth.getAccessToken()).toBeNull()
  })
})

describe('switchOrg', () => {
  it('throws on failed switch-org request', async () => {
    // Mock fetch to return a 403
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({
        errors: [{ message: 'No pertenecés a esta organización' }],
      }),
    })

    // Set a token so the request is made
    localStorage.setItem('access_token', 'valid-token')
    localStorage.setItem('refresh_token', 'valid-refresh')

    const { useAuth } = await import('../composables/useAuth')
    const auth = useAuth()

    await expect(auth.switchOrg('org-99')).rejects.toThrow('No pertenecés a esta organización')
  })
})

describe('login: post-login routing', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('throws error when user has zero memberships', async () => {
    // Mock fetch to return success for login + empty memberships for /users/me/
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          data: { access: 'access-1', refresh: 'refresh-1' },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          data: {
            id: 'user-1',
            email: 'test@test.com',
            full_name: 'Test',
            role: 'user',
            memberships: [],
          },
        }),
      })

    const { useAuth } = await import('../composables/useAuth')
    const auth = useAuth()

    await expect(auth.login('test@test.com', 'password'))
      .rejects.toThrow('No tenés organizaciones asignadas')
  })
})
