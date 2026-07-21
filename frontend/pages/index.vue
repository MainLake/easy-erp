<template>
  <div class="page-container">
    <!-- Welcome section with org name -->
    <div class="welcome-section">
      <h1 v-if="activeOrg">{{ activeOrg.name }}</h1>
      <h1 v-else>Easy ERP</h1>
      <p v-if="user">Bienvenido, {{ user.full_name }}</p>
      <p v-else class="text-muted">Cargando…</p>
    </div>

    <!-- Stats grid (N3) -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon">📦</div>
        <div class="stat-value">{{ stats.products }}</div>
        <div class="stat-label">Productos</div>
      </div>

      <div class="stat-card">
        <div class="stat-icon">📋</div>
        <div class="stat-value">{{ stats.pendingOrders }}</div>
        <div class="stat-label">Órdenes pendientes</div>
      </div>

      <div class="stat-card">
        <div class="stat-icon">👥</div>
        <div class="stat-value">{{ stats.customers }}</div>
        <div class="stat-label">Clientes</div>
      </div>

      <div class="stat-card">
        <div class="stat-icon">🧾</div>
        <div class="stat-value">{{ stats.invoices }}</div>
        <div class="stat-label">Facturas del mes</div>
      </div>
    </div>

    <!-- Quick actions -->
    <div class="quick-actions">
      <NuxtLink to="/inventory/products" class="btn btn-primary">
        Nuevo producto
      </NuxtLink>
      <NuxtLink to="/sales/orders" class="btn btn-secondary">
        Nueva orden de venta
      </NuxtLink>
      <NuxtLink to="/sales/customers" class="btn btn-secondary">
        Nuevo cliente
      </NuxtLink>
    </div>

    <!-- Recent section placeholder -->
    <div class="card mt-4">
      <div class="card-header">
        <h3>Actividad reciente</h3>
      </div>
      <div class="card-body">
        <p class="text-muted">No hay actividad reciente para mostrar.</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { activeOrg } from '~/composables/useAuth'

definePageMeta({ middleware: 'auth' })

const { user } = useAuth()
const { request } = useApi()

const stats = reactive({
  products: '—' as string | number,
  pendingOrders: '—' as string | number,
  customers: '—' as string | number,
  invoices: '—' as string | number,
})

/**
 * Extract the total count from an API envelope response.
 * Handles { meta: { total } }, { meta: { count } }, or missing meta.
 */
function extractTotal(envelope: any): number | null {
  if (envelope?.meta?.total !== undefined) return envelope.meta.total
  if (envelope?.meta?.count !== undefined) return envelope.meta.count
  return null
}

async function fetchStats(): Promise<void> {
  // Fetch product count
  try {
    const res = await request('/products/?limit=1')
    if (res.ok) {
      const env = await res.json()
      const total = extractTotal(env)
      stats.products = total !== null ? total : '—'
    }
  } catch {
    stats.products = '—'
  }

  // Fetch pending orders (draft status)
  try {
    const res = await request('/sales/orders/?status=draft&limit=1')
    if (res.ok) {
      const env = await res.json()
      const total = extractTotal(env)
      stats.pendingOrders = total !== null ? total : '—'
    }
  } catch {
    stats.pendingOrders = '—'
  }

  // Fetch customer count
  try {
    const res = await request('/sales/customers/?limit=1')
    if (res.ok) {
      const env = await res.json()
      const total = extractTotal(env)
      stats.customers = total !== null ? total : '—'
    }
  } catch {
    stats.customers = '—'
  }

  // Fetch invoice count (current month via limit=1 — total reflects scoped data)
  try {
    const res = await request('/invoicing/invoices/?limit=1')
    if (res.ok) {
      const env = await res.json()
      const total = extractTotal(env)
      stats.invoices = total !== null ? total : '—'
    }
  } catch {
    stats.invoices = '—'
  }
}

onMounted(() => {
  fetchStats()
})
</script>
