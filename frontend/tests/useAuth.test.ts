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

describe('register', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('registers successfully, persists tokens, fetches user, navigates to /', async () => {
    const navigateToSpy = vi.fn(() => Promise.resolve())
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(globalThis as any).navigateTo = navigateToSpy

    // Mock: POST /auth/register/ → 201 with tokens
    // Mock: GET /users/me/ → 200 with user (one membership)
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: () => Promise.resolve({
          data: { access: 'access-reg-1', refresh: 'refresh-reg-1' },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          data: {
            id: 'user-2',
            email: 'new@test.com',
            full_name: 'New User',
            role: 'Admin',
            memberships: [
              {
                id: 'mem-2',
                is_default: true,
                is_owner: true,
                organization: { id: 'org-2', name: 'New Org' },
                role: { id: 'role-2', name: 'Admin' },
              },
            ],
          },
        }),
      })

    const { useAuth } = await import('../composables/useAuth')
    const auth = useAuth()

    await auth.register({
      email: 'new@test.com',
      password: 'Pass1234',
      full_name: 'New User',
      org_name: 'New Org',
    })

    // Tokens persisted
    expect(localStorage.getItem('access_token')).toBe('access-reg-1')
    expect(localStorage.getItem('refresh_token')).toBe('refresh-reg-1')

    // User state hydrated with active_membership
    expect(auth.user.value).not.toBeNull()
    expect(auth.user.value!.email).toBe('new@test.com')
    expect(auth.user.value!.active_membership).toBeTruthy()
    expect(auth.user.value!.active_membership!.organization.name).toBe('New Org')

    // Redirected to /
    expect(navigateToSpy).toHaveBeenCalledWith('/')
  })

  it('throws on 409 conflict (duplicate email or org)', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: () => Promise.resolve({
        errors: [{ code: 'conflict', field: 'email', message: 'A user with this email already exists' }],
      }),
    })

    const { useAuth } = await import('../composables/useAuth')
    const auth = useAuth()

    await expect(
      auth.register({
        email: 'existing@test.com',
        password: 'Pass1234',
        full_name: 'Existing',
        org_name: 'Existing Org',
      }),
    ).rejects.toThrow('A user with this email already exists')
  })

  it('throws on 400 validation error', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({
        errors: [{ code: 'invalid', field: 'password', message: 'Password must contain at least one letter and one digit' }],
      }),
    })

    const { useAuth } = await import('../composables/useAuth')
    const auth = useAuth()

    await expect(
      auth.register({
        email: 'weak@test.com',
        password: '12345678',
        full_name: 'Weak Pwd',
        org_name: 'Weak Org',
      }),
    ).rejects.toThrow('Password must contain at least one letter and one digit')
  })

  it('passes optional org_tax_id in the request payload', async () => {
    const fetchSpy = vi.fn()
      .mockResolvedValue({
        ok: true,
        status: 201,
        json: () => Promise.resolve({
          data: { access: 'access-tax', refresh: 'refresh-tax' },
        }),
      })
      .mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
          data: {
            id: 'user-3',
            email: 'tax@test.com',
            full_name: 'Tax User',
            role: 'Admin',
            memberships: [
              {
                id: 'mem-3',
                is_default: true,
                is_owner: true,
                organization: { id: 'org-3', name: 'Tax Org' },
                role: { id: 'role-3', name: 'Admin' },
              },
            ],
          },
        }),
      })

    globalThis.fetch = fetchSpy

    const { useAuth } = await import('../composables/useAuth')
    const auth = useAuth()

    await auth.register({
      email: 'tax@test.com',
      password: 'Pass1234',
      full_name: 'Tax User',
      org_name: 'Tax Org',
      org_tax_id: 'RFC-001',
    })

    // Verify the tax_id was sent in the request body
    const firstCallBody = JSON.parse(fetchSpy.mock.calls[0]![1]!.body as string)
    expect(firstCallBody.org_tax_id).toBe('RFC-001')
  })
})
