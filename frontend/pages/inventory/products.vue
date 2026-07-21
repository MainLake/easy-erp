<template>
  <div class="page-container">
    <div class="page-header">
      <h1>Productos</h1>
      <button class="btn btn-primary" @click="openCreate">+ Nuevo Producto</button>
    </div>

    <DataTable
      :columns="columns"
      :data="items"
      :loading="loading"
      :total="total"
      :page="page"
      :page-size="pageSize"
      @page-change="changePage"
      @search="handleSearch"
      @sort="handleSort"
    >
      <template #cell-cost="{ value }">${{ Number(value).toFixed(2) }}</template>
      <template #cell-price="{ value }">${{ Number(value).toFixed(2) }}</template>
      <template #cell-category="{ value }">{{ categoryMap[value] || value }}</template>
      <template #actions="{ row }">
        <button class="btn-sm" @click="openEdit(row)">Editar</button>
        <button class="btn-sm btn-sm-action" @click="openStock(row)">Existencia</button>
      </template>
    </DataTable>

    <!-- CRUD Modal -->
    <CrudModal
      :title="editing ? 'Editar Producto' : 'Nuevo Producto'"
      :visible="modalOpen"
      :fields="formFields"
      :initial-data="editing ?? undefined"
      @save="handleSave"
      @close="modalOpen = false"
    >
      <template #below-fields>
        <DynamicFields
          model-name="product"
          :custom-fields="customFields"
          @update:custom-fields="customFields = $event"
        />
      </template>
    </CrudModal>

    <!-- Stock Management Modal -->
    <Teleport to="body">
      <div v-if="stockModalOpen" class="modal-overlay" @click.self="stockModalOpen = false">
        <div class="modal-container modal-wide">
          <div class="modal-header">
            <h3>Existencia — {{ stockProduct?.name }}</h3>
            <button class="modal-close" @click="stockModalOpen = false">×</button>
          </div>
          <div class="modal-body">
            <h4 style="font-weight:600;color:var(--color-heading);font-size:0.95rem;">Niveles de Existencia Actuales</h4>
            <table class="stock-table" v-if="stockLevels.length">
              <thead><tr><th>Almacén</th><th>Cantidad</th></tr></thead>
              <tbody>
                <tr v-for="sl in stockLevels" :key="sl.id">
                  <td>{{ sl.warehouse_name }}</td>
                  <td>{{ sl.quantity }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="text-muted">Sin niveles de existencia aún.</p>

            <h4 style="margin-top: 1.5rem;font-weight:600;color:var(--color-heading);font-size:0.95rem;">Agregar / Quitar Existencia</h4>
            <div class="stock-form">
              <select v-model="stockAction.warehouse_id" class="form-input" style="flex:2">
                <option value="">-- Almacén --</option>
                <option v-for="w in warehouses" :key="w.id" :value="w.id">{{ w.name }}</option>
              </select>
              <input v-model.number="stockAction.quantity" type="number" min="1" placeholder="Cant." class="form-input" style="flex:1" />
              <input v-model="stockAction.reason" placeholder="Motivo" class="form-input" style="flex:2" />
              <button class="btn btn-success btn-sm-custom" @click="doAddStock" :disabled="stockSaving">Agregar</button>
              <button class="btn btn-danger btn-sm-custom" @click="doRemoveStock" :disabled="stockSaving">Quitar</button>
            </div>
            <p v-if="stockError" class="form-error">{{ stockError }}</p>

            <h4 style="margin-top: 1.5rem;font-weight:600;color:var(--color-heading);font-size:0.95rem;">Movimientos Recientes</h4>
            <table class="stock-table" v-if="movements.length">
              <thead><tr><th>Tipo</th><th>Almacén</th><th>Cant.</th><th>Motivo</th><th>Fecha</th></tr></thead>
              <tbody>
                <tr v-for="m in movements" :key="m.id">
                  <td><span :class="`badge badge-${m.movement_type}`">{{ m.movement_type }}</span></td>
                  <td>{{ m.warehouse_name }}</td>
                  <td>{{ m.quantity }}</td>
                  <td>{{ m.reason }}</td>
                  <td>{{ new Date(m.timestamp).toLocaleDateString() }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="text-muted">Sin movimientos registrados.</p>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

definePageMeta({ middleware: 'auth' })

const { request } = useApi()

// ---- state ----
const items = ref<any[]>([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const searchQuery = ref('')
const sortKey = ref('')
const sortDir = ref<'asc' | 'desc'>('asc')

// Modal state
const modalOpen = ref(false)
const editing = ref<any>(null)

// Custom fields state
const customFields = ref<Record<string, string>>({})

// References for category select
const categories = ref<any[]>([])
const warehouses = ref<any[]>([])

// Stock management
const stockModalOpen = ref(false)
const stockProduct = ref<any>(null)
const stockLevels = ref<any[]>([])
const movements = ref<any[]>([])
const stockAction = ref({ warehouse_id: '', quantity: 1, reason: '' })
const stockSaving = ref(false)
const stockError = ref('')

// ---- computed ----
const columns = [
  { key: 'sku', label: 'SKU' },
  { key: 'name', label: 'Nombre' },
  { key: 'description', label: 'Descripción' },
  { key: 'cost', label: 'Costo' },
  { key: 'price', label: 'Precio' },
  { key: 'category', label: 'Categoría' },
]

const categoryMap = computed(() => {
  const map: Record<string, string> = {}
  for (const c of categories.value) map[c.id] = c.name
  return map
})

const formFields = computed(() => [
  { name: 'sku', label: 'SKU', required: true },
  { name: 'name', label: 'Nombre', required: true },
  { name: 'description', label: 'Descripción', type: 'textarea' as const },
  { name: 'cost', label: 'Costo', type: 'number' as const, required: true },
  { name: 'price', label: 'Precio', type: 'number' as const, required: true },
  { name: 'category', label: 'Categoría', type: 'select' as const, options: categories.value.map((c: any) => ({ value: c.id, label: c.name })) },
])

// ---- data fetching ----
async function fetchData() {
  loading.value = true
  try {
    const params = new URLSearchParams({ page: String(page.value), page_size: String(pageSize.value) })
    if (searchQuery.value) params.set('search', searchQuery.value)
    if (sortKey.value) params.set('ordering', sortDir.value === 'desc' ? `-${sortKey.value}` : sortKey.value)

    const res = await request(`/inventory/products/?${params}`)
    const envelope = await res.json()
    items.value = envelope.data ?? envelope.results ?? []
    total.value = envelope.meta?.total ?? envelope.count ?? items.value.length
  } catch (e: any) {
    console.error('Failed to fetch products:', e)
  } finally {
    loading.value = false
  }
}

async function loadCategories() {
  try {
    const res = await request('/inventory/categories/?page_size=200')
    const envelope = await res.json()
    categories.value = envelope.data ?? envelope.results ?? []
  } catch { /* non-critical */ }
}

async function loadWarehouses() {
  try {
    const res = await request('/inventory/warehouses/?page_size=200')
    const envelope = await res.json()
    warehouses.value = envelope.data ?? envelope.results ?? []
  } catch { /* non-critical */ }
}

onMounted(() => {
  loadCategories()
  loadWarehouses()
  fetchData()
})

// ---- event handlers ----
function changePage(p: number) { page.value = p; fetchData() }
function handleSearch(q: string) { searchQuery.value = q; page.value = 1; fetchData() }
function handleSort(key: string, dir: 'asc' | 'desc') { sortKey.value = key; sortDir.value = dir; fetchData() }

function openCreate() { editing.value = null; customFields.value = {}; modalOpen.value = true }
function openEdit(row: any) { editing.value = { ...row }; customFields.value = { ...(row.custom_fields ?? {}) }; modalOpen.value = true }

async function handleSave(payload: Record<string, any>) {
  // Merge custom_fields into the payload
  if (Object.keys(customFields.value).length > 0) {
    payload.custom_fields = { ...customFields.value }
  }

  if (editing.value?.id) {
    const res = await request(`/inventory/products/${editing.value.id}/`, {
      method: 'PUT', body: JSON.stringify(payload),
    })
    if (!res.ok) { const e = await res.json(); throw new Error(e.errors?.[0]?.message || 'Error al actualizar') }
  } else {
    const res = await request('/inventory/products/', {
      method: 'POST', body: JSON.stringify(payload),
    })
    if (!res.ok) { const e = await res.json(); throw new Error(e.errors?.[0]?.message || 'Error al crear') }
  }
  modalOpen.value = false
  fetchData()
}

// ---- stock management ----
async function openStock(product: any) {
  stockProduct.value = product
  stockModalOpen.value = true
  stockError.value = ''
  stockAction.value = { warehouse_id: '', quantity: 1, reason: '' }
  await loadWarehouses()
  // Fetch stock levels for this product
  try {
    const res = await request(`/inventory/products/stock/?product=${product.id}`)
    const envelope = await res.json()
    const all: any[] = envelope.data ?? envelope.results ?? []
    stockLevels.value = all.filter((s: any) => s.product === product.id)
  } catch { stockLevels.value = [] }
  // Fetch movements
  try {
    const res = await request(`/inventory/movements/?product=${product.id}&page_size=20`)
    const envelope = await res.json()
    movements.value = envelope.data ?? envelope.results ?? []
  } catch { movements.value = [] }
}

async function doAddStock() {
  stockError.value = ''
  stockSaving.value = true
  try {
    const res = await request(`/inventory/products/${stockProduct.value!.id}/add-stock/`, {
      method: 'POST', body: JSON.stringify(stockAction.value),
    })
    if (!res.ok) { const e = await res.json(); throw new Error(e.errors?.detail || 'Error al agregar existencia') }
    openStock(stockProduct.value) // refresh
  } catch (e: any) {
    stockError.value = e.message
  } finally {
    stockSaving.value = false
  }
}

async function doRemoveStock() {
  stockError.value = ''
  stockSaving.value = true
  try {
    const res = await request(`/inventory/products/${stockProduct.value!.id}/remove-stock/`, {
      method: 'POST', body: JSON.stringify(stockAction.value),
    })
    if (!res.ok) { const e = await res.json(); throw new Error(e.errors?.detail || 'Error al quitar existencia') }
    openStock(stockProduct.value)
  } catch (e: any) {
    stockError.value = e.message
  } finally {
    stockSaving.value = false
  }
}
</script>

<style scoped>
.page-container {
  padding: 1.5rem 2rem;
  max-width: 1280px;
}

.stock-form {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 0.5rem;
}

.btn-sm-custom {
  padding: 0.45rem 0.8rem;
  font-size: 0.8rem;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.5);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-container {
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  width: 90%;
  max-width: 540px;
  max-height: 85vh;
  overflow-y: auto;
  box-shadow: var(--shadow-lg);
}

.modal-wide {
  max-width: 740px;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.1rem 1.5rem;
  border-bottom: 1px solid var(--color-border-light);
}

.modal-header h3 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--color-heading);
}

.modal-close {
  background: none;
  border: none;
  font-size: 1.4rem;
  cursor: pointer;
  color: var(--color-muted);
  line-height: 1;
  padding: 0.25rem;
  border-radius: var(--radius-sm);
  transition: all 0.15s ease;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-close:hover {
  background: var(--color-bg);
  color: var(--color-heading);
}

.modal-body {
  padding: 1.5rem;
}
</style>
