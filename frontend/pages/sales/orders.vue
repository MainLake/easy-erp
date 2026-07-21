<template>
  <div class="page-container">
    <div class="page-header">
      <h1>Órdenes de Venta</h1>
      <button class="btn btn-primary" @click="openCreate">+ Nueva OV</button>
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
    >
      <template #cell-customer_name="{ value }">{{ value || '—' }}</template>
      <template #cell-status="{ value }">
        <span :class="`badge badge-${value}`">{{ (statusLabels as any)[value] || value }}</span>
      </template>
      <template #cell-order_date="{ value }">{{ new Date(value).toLocaleDateString() }}</template>
      <template #actions="{ row }">
        <button class="btn-sm" @click="openView(row)">Ver</button>
        <button v-if="row.status === 'draft'" class="btn-sm btn-sm-action" @click="handleConfirm(row)">Confirmar</button>
        <button v-if="row.status === 'confirmed'" class="btn-sm btn-sm-action" @click="handleFulfill(row)">Completar</button>
      </template>
    </DataTable>

    <!-- Create SO Modal -->
    <Teleport to="body">
      <div v-if="modalOpen" class="modal-overlay" @click.self="modalOpen = false">
        <div class="modal-container modal-wide">
          <div class="modal-header">
            <h3>Nueva Orden de Venta</h3>
            <button class="modal-close" @click="modalOpen = false">×</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>Cliente <span class="required">*</span></label>
              <select v-model="form.customer" class="form-input" required>
                <option value="">-- Seleccionar Cliente --</option>
                <option v-for="c in customers" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>Notas</label>
              <textarea v-model="form.notes" class="form-input" rows="2" />
            </div>

            <h4 style="margin: 1.25rem 0 0.5rem;font-weight:600;color:var(--color-heading);">Líneas</h4>
            <table class="line-items-table">
              <thead><tr><th>Producto</th><th>Almacén</th><th>Cantidad</th><th>Precio Unitario</th><th></th></tr></thead>
              <tbody>
                <tr v-for="(li, idx) in form.line_items" :key="idx">
                  <td>
                    <select v-model="li.product" class="form-input form-input-sm">
                      <option value="">-- Producto --</option>
                      <option v-for="p in products" :key="p.id" :value="p.id">{{ p.name }}</option>
                    </select>
                  </td>
                  <td>
                    <select v-model="li.warehouse" class="form-input form-input-sm">
                      <option value="">-- Almacén --</option>
                      <option v-for="w in warehouses" :key="w.id" :value="w.id">{{ w.name }}</option>
                    </select>
                  </td>
                  <td><input v-model.number="li.quantity" type="number" min="1" class="form-input form-input-sm" style="width:80px" /></td>
                  <td><input v-model.number="li.unit_price" type="number" min="0" step="0.01" class="form-input form-input-sm" style="width:110px" /></td>
                  <td><button class="btn-sm btn-sm-danger" @click="form.line_items.splice(idx, 1)">×</button></td>
                </tr>
              </tbody>
            </table>
            <button class="btn-sm" style="margin-top:0.65rem" @click="form.line_items.push({ product: '', warehouse: '', quantity: 1, unit_price: 0 })">+ Agregar Línea</button>

            <p v-if="saveError" class="form-error">{{ saveError }}</p>
            <div class="modal-footer">
              <button class="btn-cancel" @click="modalOpen = false">Cancelar</button>
              <button class="btn-save" @click="handleSave" :disabled="saving">{{ saving ? 'Guardando…' : 'Guardar' }}</button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- View SO Detail -->
    <Teleport to="body">
      <div v-if="viewModalOpen" class="modal-overlay" @click.self="viewModalOpen = false">
        <div class="modal-container modal-wide">
          <div class="modal-header">
            <h3>OV #{{ viewing?.id?.slice(0, 8) }} — <span :class="`badge badge-${viewing?.status}`">{{ viewing?.status }}</span></h3>
            <button class="modal-close" @click="viewModalOpen = false">×</button>
          </div>
          <div class="modal-body">
            <p><strong>Cliente:</strong> {{ viewing?.customer_name }}</p>
            <p><strong>Fecha:</strong> {{ viewing?.order_date ? new Date(viewing.order_date).toLocaleDateString() : '—' }}</p>
            <p><strong>Notas:</strong> {{ viewing?.notes || '—' }}</p>
            <h4 style="margin:1.25rem 0 0.5rem;font-weight:600;color:var(--color-heading);">Líneas</h4>
            <table class="line-items-table">
              <thead><tr><th>Producto</th><th>Almacén</th><th>Cant.</th><th>Precio Unitario</th><th>Subtotal</th></tr></thead>
              <tbody>
                <tr v-for="li in (viewing?.line_items ?? [])" :key="li.id">
                  <td>{{ li.product_name }}</td>
                  <td>{{ li.warehouse_name }}</td>
                  <td>{{ li.quantity }}</td>
                  <td>${{ Number(li.unit_price).toFixed(2) }}</td>
                  <td>${{ (li.quantity * li.unit_price).toFixed(2) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'

definePageMeta({ middleware: 'auth' })

const { request } = useApi()

const items = ref<any[]>([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const searchQuery = ref('')

const customers = ref<any[]>([])
const products = ref<any[]>([])
const warehouses = ref<any[]>([])

const modalOpen = ref(false)
const saving = ref(false)
const saveError = ref('')
const form = reactive({ customer: '', notes: '', line_items: [] as any[] })

const viewModalOpen = ref(false)
const viewing = ref<any>(null)

const columns = [
  { key: 'customer_name', label: 'Cliente' },
  { key: 'status', label: 'Estado' },
  { key: 'order_date', label: 'Fecha' },
  { key: 'notes', label: 'Notas' },
]

const statusLabels = {
  draft: 'borrador',
  confirmed: 'confirmado',
  fulfilled: 'completado',
  cancelled: 'cancelado',
}

async function fetchData() {
  loading.value = true
  try {
    const params = new URLSearchParams({ page: String(page.value), page_size: String(pageSize.value) })
    if (searchQuery.value) params.set('search', searchQuery.value)

    const res = await request(`/sales/orders/?${params}`)
    const envelope = await res.json()
    items.value = envelope.data ?? envelope.results ?? []
    total.value = envelope.meta?.total ?? envelope.count ?? items.value.length
  } catch (e: any) {
    console.error('Failed to fetch SOs:', e)
  } finally {
    loading.value = false
  }
}

async function loadRefs() {
  try {
    const [custRes, prodRes, whRes] = await Promise.all([
      request('/sales/customers/?page_size=500'),
      request('/inventory/products/?page_size=500'),
      request('/inventory/warehouses/?page_size=500'),
    ])
    customers.value = (await custRes.json()).data ?? (await custRes.json()).results ?? []
    products.value = (await prodRes.json()).data ?? (await prodRes.json()).results ?? []
    warehouses.value = (await whRes.json()).data ?? (await whRes.json()).results ?? []
  } catch (e) { console.error('Failed to load refs:', e) }
}

onMounted(() => { loadRefs(); fetchData() })

function changePage(p: number) { page.value = p; fetchData() }
function handleSearch(q: string) { searchQuery.value = q; page.value = 1; fetchData() }

function openCreate() {
  form.customer = ''
  form.notes = ''
  form.line_items = [{ product: '', warehouse: '', quantity: 1, unit_price: 0 }]
  saveError.value = ''
  modalOpen.value = true
}

function openView(row: any) {
  viewing.value = row
  viewModalOpen.value = true
}

async function handleSave() {
  saveError.value = ''
  saving.value = true
  try {
    const payload = {
      customer: form.customer,
      notes: form.notes,
      line_items_write: form.line_items
        .filter(li => li.product && li.warehouse)
        .map(li => ({ product: li.product, warehouse: li.warehouse, quantity: li.quantity, unit_price: li.unit_price })),
    }
    if (!payload.customer || payload.line_items_write.length === 0) {
      throw new Error('El cliente y al menos una línea con almacén son requeridos.')
    }
    const res = await request('/sales/orders/', { method: 'POST', body: JSON.stringify(payload) })
    if (!res.ok) { const e = await res.json(); throw new Error(e.errors?.[0]?.message || e.errors?.detail || 'Error al guardar') }
    modalOpen.value = false
    fetchData()
  } catch (e: any) {
    saveError.value = e.message
  } finally {
    saving.value = false
  }
}

async function handleConfirm(row: any) {
  if (!confirm(`¿Confirmar OV para "${row.customer_name}"?`)) return
  const res = await request(`/sales/orders/${row.id}/confirm/`, { method: 'POST' })
  if (!res.ok) {
    const e = await res.json()
    alert(e.errors?.detail || 'Error al confirmar')
  }
  fetchData()
}

async function handleFulfill(row: any) {
  if (!confirm(`¿Completar OV para "${row.customer_name}"? Se descontará la existencia.`)) return
  const res = await request(`/sales/orders/${row.id}/fulfill/`, { method: 'POST' })
  if (!res.ok) {
    const e = await res.json()
    alert(e.errors?.detail || 'Error al completar')
  }
  fetchData()
}
</script>

<style scoped>
.page-container {
  padding: 1.5rem 2rem;
  max-width: 1280px;
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
  display: flex;
  align-items: center;
  gap: 0.5rem;
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

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 1.25rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--color-border-light);
}

.btn-cancel {
  padding: 0.5rem 1.25rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  cursor: pointer;
  font-size: 0.875rem;
  font-family: var(--font-family);
  color: var(--color-body);
  transition: all 0.15s ease;
}

.btn-cancel:hover {
  background: var(--color-bg);
  border-color: #cbd5e1;
}

.btn-save {
  padding: 0.5rem 1.25rem;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--color-primary);
  color: #fff;
  cursor: pointer;
  font-size: 0.875rem;
  font-family: var(--font-family);
  font-weight: 500;
  transition: all 0.15s ease;
}

.btn-save:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn-save:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
