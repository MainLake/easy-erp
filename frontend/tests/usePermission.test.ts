import { describe, it, expect, beforeEach } from 'vitest'
import type { User } from '../composables/useAuth'

describe('usePermission', () => {
  let hasPermission: (module: string, action: string) => boolean
  let permissionCount: (permissions: Record<string, string[]>) => number
  let MODULES: readonly string[]
  let ACTIONS: readonly string[]
  let moduleLabels: Record<string, string>

  beforeEach(async () => {
    localStorage.clear()
    const mod = await import('../composables/usePermission')
    const inst = mod.usePermission()
    hasPermission = inst.hasPermission
    permissionCount = inst.permissionCount
    MODULES = inst.MODULES
    ACTIONS = inst.ACTIONS
    moduleLabels = inst.moduleLabels
  })

  /**
   * Helper: set the mocked useAuth user ref with given permissions.
   */
  async function setUser(permissions: Record<string, string[]> | null | undefined) {
    const { useAuth } = await import('../composables/useAuth')
    const auth = useAuth()
    auth.user.value = {
      id: 'user-1',
      email: 'test@test.com',
      full_name: 'Test User',
      role: 'user',
      active_membership: {
        id: 'mem-1',
        is_default: true,
        is_owner: false,
        organization: { id: 'org-1', name: 'Acme' },
        role: {
          id: 'role-1',
          name: 'Custom',
          permissions: permissions ?? undefined,
        },
      },
    } as User
  }

  describe('hasPermission', () => {
    it('returns false when no user is set', () => {
      expect(hasPermission('inventory', 'read')).toBe(false)
    })

    it('returns false when no active_membership', async () => {
      const { useAuth } = await import('../composables/useAuth')
      const auth = useAuth()
      auth.user.value = {
        id: 'user-1',
        email: 'test@test.com',
        full_name: 'Test',
        role: 'user',
        active_membership: null,
      } as User
      expect(hasPermission('inventory', 'read')).toBe(false)
    })

    it('returns false for empty permissions', async () => {
      await setUser({})
      expect(hasPermission('inventory', 'read')).toBe(false)
    })

    // --- Wildcard "*" module tests ---

    it('grants everything when wildcard * has admin', async () => {
      await setUser({ '*': ['admin'] })
      expect(hasPermission('inventory', 'read')).toBe(true)
      expect(hasPermission('inventory', 'write')).toBe(true)
      expect(hasPermission('inventory', 'admin')).toBe(true)
      expect(hasPermission('sales', 'read')).toBe(true)
      expect(hasPermission('core', 'admin')).toBe(true)
    })

    it('grants read on any module when wildcard * has write', async () => {
      await setUser({ '*': ['write'] })
      expect(hasPermission('inventory', 'read')).toBe(true)
      expect(hasPermission('inventory', 'write')).toBe(true)
      expect(hasPermission('inventory', 'admin')).toBe(false)
      expect(hasPermission('sales', 'read')).toBe(true)
      expect(hasPermission('core', 'write')).toBe(true)
    })

    it('grants exact match when wildcard * has read only', async () => {
      await setUser({ '*': ['read'] })
      expect(hasPermission('inventory', 'read')).toBe(true)
      expect(hasPermission('inventory', 'write')).toBe(false)
      expect(hasPermission('inventory', 'admin')).toBe(false)
    })

    // --- Hierarchy tests ---

    it('admin implies read and write', async () => {
      await setUser({ inventory: ['admin'] })
      expect(hasPermission('inventory', 'read')).toBe(true)
      expect(hasPermission('inventory', 'write')).toBe(true)
      expect(hasPermission('inventory', 'admin')).toBe(true)
    })

    it('write implies read but not admin', async () => {
      await setUser({ inventory: ['write'] })
      expect(hasPermission('inventory', 'read')).toBe(true)
      expect(hasPermission('inventory', 'write')).toBe(true)
      expect(hasPermission('inventory', 'admin')).toBe(false)
    })

    it('read grants read only', async () => {
      await setUser({ inventory: ['read'] })
      expect(hasPermission('inventory', 'read')).toBe(true)
      expect(hasPermission('inventory', 'write')).toBe(false)
      expect(hasPermission('inventory', 'admin')).toBe(false)
    })

    it('write does not grant admin', async () => {
      await setUser({ sales: ['write'] })
      expect(hasPermission('sales', 'read')).toBe(true)
      expect(hasPermission('sales', 'write')).toBe(true)
      expect(hasPermission('sales', 'admin')).toBe(false)
    })

    // --- Multi-module ---

    it('correctly checks different modules independently', async () => {
      await setUser({ inventory: ['write'], sales: ['read'] })
      expect(hasPermission('inventory', 'read')).toBe(true)
      expect(hasPermission('inventory', 'write')).toBe(true)
      expect(hasPermission('inventory', 'admin')).toBe(false)
      expect(hasPermission('sales', 'read')).toBe(true)
      expect(hasPermission('sales', 'write')).toBe(false)
      expect(hasPermission('purchasing', 'read')).toBe(false)
    })

    // --- Edge cases ---

    it('returns false when permissions is undefined in role', async () => {
      const { useAuth } = await import('../composables/useAuth')
      const auth = useAuth()
      auth.user.value = {
        id: 'user-1',
        email: 'test@test.com',
        full_name: 'Test',
        role: 'user',
        active_membership: {
          id: 'mem-1',
          is_default: true,
          is_owner: false,
          organization: { id: 'org-1', name: 'Acme' },
          role: { id: 'role-1', name: 'Custom' } as any,
        },
      } as User
      expect(hasPermission('inventory', 'read')).toBe(false)
    })

    it('handles unknown module gracefully', async () => {
      await setUser({ inventory: ['admin'] })
      expect(hasPermission('unknown_module', 'read')).toBe(false)
    })

    it('handles unknown action gracefully', async () => {
      await setUser({ inventory: ['read'] })
      expect(hasPermission('inventory', 'delete')).toBe(false)
    })

    // --- Wildcard + module override ---

    it('module-specific permissions take effect alongside wildcard', async () => {
      await setUser({ '*': ['read'], inventory: ['write'] })
      expect(hasPermission('sales', 'read')).toBe(true)
      expect(hasPermission('sales', 'write')).toBe(false)
      expect(hasPermission('inventory', 'read')).toBe(true)
      expect(hasPermission('inventory', 'write')).toBe(true)
    })

    it('wildcard admin dominates even with conflicting module permissions', async () => {
      await setUser({ '*': ['admin'], inventory: [] })
      expect(hasPermission('inventory', 'read')).toBe(true)
      expect(hasPermission('inventory', 'write')).toBe(true)
      expect(hasPermission('inventory', 'admin')).toBe(true)
    })
  })

  describe('permissionCount', () => {
    it('counts total actions across all modules', () => {
      expect(permissionCount({ inventory: ['read', 'write'], sales: ['read'] })).toBe(3)
    })

    it('returns 0 for empty permissions', () => {
      expect(permissionCount({})).toBe(0)
    })

    it('counts wildcard correctly', () => {
      expect(permissionCount({ '*': ['admin'] })).toBe(1)
    })
  })

  describe('MODULES and ACTIONS', () => {
    it('exposes the five business modules', () => {
      expect(MODULES).toEqual(['inventory', 'purchasing', 'sales', 'invoicing', 'core'])
    })

    it('exposes the three action levels in ascending order', () => {
      expect(ACTIONS).toEqual(['read', 'write', 'admin'])
    })
  })

  describe('moduleLabels', () => {
    it('maps modules to Spanish sidebar labels', () => {
      expect(moduleLabels.inventory).toBe('Inventario')
      expect(moduleLabels.purchasing).toBe('Compras')
      expect(moduleLabels.sales).toBe('Ventas')
      expect(moduleLabels.invoicing).toBe('Facturación')
      expect(moduleLabels.core).toBe('Configuración')
    })
  })
})
