/**
 * RBAC permission check composable.
 *
 * Mirrors the backend OrgRolePermission.has_permission logic exactly,
 * using user.active_membership.role.permissions from /users/me/.
 *
 * Hierarchy (same as backend):
 *   *:admin    → grants everything on every module
 *   *:write    → grants read on every module
 *   module:admin  → all actions on module
 *   module:write  → write + read on module
 *   module:read   → read only
 */

import type { User } from './useAuth'
import { useAuth } from './useAuth'

export const usePermission = () => {
  /**
   * Returns the raw permissions dict from the active membership's role,
   * or an empty object when no membership/role is available.
   */
  function _getPermissions(user: User | null): Record<string, string[]> {
    return user?.active_membership?.role?.permissions ?? {}
  }

  /**
   * Check whether the current user can perform *action* on *module*.
   *
   * Mirrors OrgRolePermission.has_permission perfectly:
   * 1. Wildcard "*" module: admin→everything, write→read
   * 2. Module-level: admin→everything, write→read, read→read
   * 3. Exact match on action
   */
  function hasPermission(module: string, action: string): boolean {
    const { user } = useAuth()
    const perms = _getPermissions(user.value)
    if (!perms) return false

    // 1. Wildcard "*" module check
    const wildcard = perms['*']
    if (wildcard) {
      if (wildcard.includes('admin')) return true
      if (action === 'read' && wildcard.includes('write')) return true
      if (wildcard.includes(action)) return true
    }

    // 2. Module-specific check
    const allowed = perms[module]
    if (!allowed || allowed.length === 0) return false

    if (allowed.includes('admin')) return true
    if (action === 'read' && allowed.includes('write')) return true

    return allowed.includes(action)
  }

  /**
   * Count how many total permission entries exist across all modules.
   * Useful for displaying "N permissions" in the role list.
   */
  function permissionCount(permissions: Record<string, string[]>): number {
    let count = 0
    for (const actions of Object.values(permissions)) {
      count += actions.length
    }
    return count
  }

  /**
   * All modules recognized by the permission system.
   */
  const MODULES = ['inventory', 'purchasing', 'sales', 'invoicing', 'core'] as const

  /**
   * All action levels (from least to most powerful).
   */
  const ACTIONS = ['read', 'write', 'admin'] as const

  // Module-to-sidebar-section mapping
  const moduleLabels: Record<string, string> = {
    inventory: 'Inventario',
    purchasing: 'Compras',
    sales: 'Ventas',
    invoicing: 'Facturación',
    core: 'Configuración',
  }

  return {
    hasPermission,
    permissionCount,
    MODULES,
    ACTIONS,
    moduleLabels,
  }
}
