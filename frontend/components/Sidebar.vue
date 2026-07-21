<template>
  <aside class="sidebar">
    <nav class="sidebar-nav">
      <ul class="sidebar-list">
        <li>
          <NuxtLink to="/" class="sidebar-link" :class="{ active: isActive('/') }">
            <span class="sidebar-icon">🏠</span>
            <span class="sidebar-text">Dashboard</span>
          </NuxtLink>
        </li>
      </ul>

      <div class="sidebar-section" v-for="section in sections" :key="section.label">
        <h3 class="sidebar-section-title">{{ section.label }}</h3>
        <ul class="sidebar-list">
          <li v-for="item in section.items" :key="item.to">
            <NuxtLink
              :to="item.to"
              class="sidebar-link"
              :class="{ active: isActive(item.to) }"
            >
              <span class="sidebar-icon">{{ item.icon }}</span>
              <span class="sidebar-text">{{ item.label }}</span>
            </NuxtLink>
          </li>
        </ul>
      </div>
    </nav>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const route = useRoute()
const { user } = useAuth()

interface SidebarItem {
  to: string
  label: string
  icon: string
}

interface SidebarSection {
  label: string
  items: SidebarItem[]
}

const isOwner = computed(() => user.value?.active_membership?.is_owner ?? false)

const settingsSection = computed<SidebarSection | null>(() => {
  if (!isOwner.value) return null
  return {
    label: 'Configuración',
    items: [
      { to: '/settings/custom-fields', label: 'Campos personalizados', icon: '⚙️' },
    ],
  }
})

const sections = computed<SidebarSection[]>(() => {
  const base: SidebarSection[] = [
    {
      label: 'Inventario',
      items: [
        { to: '/inventory/products', label: 'Productos', icon: '📦' },
        { to: '/inventory/categories', label: 'Categorías', icon: '🏷️' },
        { to: '/inventory/warehouses', label: 'Almacenes', icon: '🏭' },
      ],
    },
    {
      label: 'Compras',
      items: [
        { to: '/purchasing/suppliers', label: 'Proveedores', icon: '🚚' },
        { to: '/purchasing/orders', label: 'Órdenes', icon: '📋' },
      ],
    },
    {
      label: 'Ventas',
      items: [
        { to: '/sales/customers', label: 'Clientes', icon: '👥' },
        { to: '/sales/orders', label: 'Órdenes', icon: '📋' },
      ],
    },
    {
      label: 'Facturación',
      items: [
        { to: '/invoicing/invoices', label: 'Facturas', icon: '🧾' },
      ],
    },
  ]
  if (settingsSection.value) {
    base.push(settingsSection.value)
  }
  return base
})

function isActive(path: string): boolean {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}
</script>

<style scoped>
.sidebar {
  width: var(--sidebar-width);
  min-width: var(--sidebar-width);
  height: calc(100vh - var(--topbar-height));
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  overflow-y: auto;
  position: sticky;
  top: var(--topbar-height);
}

.sidebar-nav {
  padding: 1rem 0.75rem;
}

.sidebar-section {
  margin-top: 1.25rem;
}

.sidebar-section-title {
  font-size: 0.7rem;
  font-weight: 700;
  color: var(--color-muted);
  text-transform: uppercase;
  letter-spacing: 0.6px;
  padding: 0 0.75rem;
  margin-bottom: 0.4rem;
}

.sidebar-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.sidebar-link {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-sm);
  color: var(--color-body);
  font-size: 0.85rem;
  font-weight: 500;
  text-decoration: none;
  transition: background 0.12s ease, color 0.12s ease;
}

.sidebar-link:hover {
  background: var(--color-primary-light);
  color: var(--color-primary);
}

.sidebar-link.active {
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-weight: 600;
}

.sidebar-icon {
  font-size: 1rem;
  width: 1.25rem;
  text-align: center;
  flex-shrink: 0;
}

.sidebar-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Hamburger toggle for mobile — hidden by default */
.sidebar-toggle {
  display: none;
}

@media (max-width: 768px) {
  .sidebar {
    display: none; /* collapsed by default on mobile */
  }
}
</style>
