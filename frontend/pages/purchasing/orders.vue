<template>
  <div class="page-container">
    <div class="page-header">
      <h1>Órdenes de Compra</h1>
      <button v-if="hasPermission('purchasing', 'write')" class="btn btn-primary" @click="openCreate">+ Nueva OC</button>
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
      <template #cell-supplier_name="{ value }">{{ value || '—' }}</template>
      <template #cell-created_by_name="{ value }">{{ value || '—' }}</template>
      <template #cell-status="{ value }">
        <span :class="`badge badge-${value}`">{{ (statusLabels as any)[value] || value }}</span>
      </template>
      <template #cell-order_date="{ value }">{{ new Date(value).toLocaleDateString() }}</template>
      <template #cell-approval_status="{ value }">
        <span v-if="value && value !== 'none'" :class="`badge badge-${value}`">{{ (approvalStatusLabels as any)[value] || value }}</span>
      </template>
      <template #actions="{ row }">
        <button class="btn-sm" @click="openView(row)">Ver</button>
        <button v-if="row.status === 'draft' && hasPermission('purchasing', 'write')" class="btn-sm btn-sm-action" @click="handleSend(row)">Enviar</button>
        <button v-if="row.status === 'sent' && hasPermission('purchasing', 'write')" class="btn-sm btn-sm-action" @click="handleReceive(row)">Recibir</button>
        <button v-if="row.approval_status === 'pending'" class="btn-sm btn-sm-action" @click="handleApprove(row)">Aprobar</button>
        <button v-if="row.approval_status === 'pending'" class="btn-sm btn-sm-danger" @click="handleReject(row)">Rechazar</button>
      </template>
    </DataTable>

    <!-- Create/Edit PO Modal -->
    <Teleport to="body">
      <div v-if="modalOpen" class="modal-overlay" @click.self="modalOpen = false">
        <div class="modal-container modal-wide">
          <div class="modal-header">
            <h3>{{ editing?.id ? 'Editar OC' : 'Nueva Orden de Compra' }}</h3>
            <button class="modal-close" @click="modalOpen = false">×</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>Proveedor <span class="required">*</span></label>
              <select v-model="form.supplier" class="form-input" required>
                <option value="">-- Seleccionar Proveedor --</option>
                <option v-for="s in suppliers" :key="s.id" :value="s.id">{{ s.name }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>Notas</label>
              <textarea v-model="form.notes" class="form-input" rows="2" />
            </div>

            <h4 style="margin: 1.25rem 0 0.5rem;font-weight:600;color:var(--color-heading);">Líneas</h4>
            <table class="line-items-table">
              <thead><tr><th>Producto</th><th>Cantidad</th><th>Costo Unitario</th><th></th></tr></thead>
              <tbody>
                <tr v-for="(li, idx) in form.line_items" :key="idx">
                  <td>
                    <select v-model="li.product" class="form-input form-input-sm">
                      <option value="">-- Producto --</option>
                      <option v-for="p in products" :key="p.id" :value="p.id">{{ p.name }} ({{ p.sku }})</option>
                    </select>
                  </td>
                  <td><input v-model.number="li.quantity" type="number" min="1" class="form-input form-input-sm" style="width:80px" /></td>
                  <td><input v-model.number="li.unit_cost" type="number" min="0" step="0.01" class="form-input form-input-sm" style="width:110px" /></td>
                  <td><button class="btn-sm btn-sm-danger" @click="form.line_items.splice(idx, 1)">×</button></td>
                </tr>
              </tbody>
            </table>
            <button class="btn-sm" style="margin-top:0.65rem" @click="form.line_items.push({ product: '', quantity: 1, unit_cost: 0 })">+ Agregar Línea</button>

            <p v-if="saveError" class="form-error">{{ saveError }}</p>
            <div class="modal-footer">
              <button class="btn-cancel" @click="modalOpen = false">Cancelar</button>
              <button class="btn-save" @click="handleSave" :disabled="saving">{{ saving ? 'Guardando…' : 'Guardar' }}</button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- View PO Detail Modal -->
    <Teleport to="body">
      <div v-if="viewModalOpen" class="modal-overlay" @click.self="viewModalOpen = false">
        <div class="modal-container modal-wide">
          <div class="modal-header">
            <h3>
              OC #{{ viewing?.id?.slice(0, 8) }} — <span :class="`badge badge-${viewing?.status}`">{{ viewing?.status }}</span>
              <span v-if="viewing?.approval_status && viewing.approval_status !== 'none'" :class="`badge badge-${viewing.approval_status}`">{{ (approvalStatusLabels as any)[viewing.approval_status] || viewing.approval_status }}</span>
            </h3>
            <button class="modal-close" @click="viewModalOpen = false">×</button>
          </div>
          <div class="modal-body">
            <p><strong>Proveedor:</strong> {{ viewing?.supplier_name }}</p>
            <p><strong>Fecha:</strong> {{ viewing?.order_date ? new Date(viewing.order_date).toLocaleDateString() : '—' }}</p>
            <p><strong>Notas:</strong> {{ viewing?.notes || '—' }}</p>
            <p><strong>Creado por:</strong> {{ viewing?.created_by_name || '—' }}</p>
            <h4 style="margin:1.25rem 0 0.5rem;font-weight:600;color:var(--color-heading);">Líneas</h4>
            <table class="line-items-table">
              <thead><tr><th>Producto</th><th>Cantidad</th><th>Costo Unitario</th><th>Subtotal</th></tr></thead>
              <tbody>
                <tr v-for="li in (viewing?.line_items ?? [])" :key="li.id">
                  <td>{{ li.product_name }}</td>
                  <td>{{ li.quantity }}</td>
                  <td>${{ Number(li.unit_cost).toFixed(2) }}</td>
                  <td>${{ (li.quantity * li.unit_cost).toFixed(2) }}</td>
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
const { hasPermission } = usePermission()

const items = ref<any[]>([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const searchQuery = ref('')

const suppliers = ref<any[]>([])
const products = ref<any[]>([])

const modalOpen = ref(false)
const saving = ref(false)
const saveError = ref('')
const editing = ref<any>(null)
const form = reactive({ supplier: '', notes: '', line_items: [] as any[] })

const viewModalOpen = ref(false)
const viewing = ref<any>(null)

const columns = [
  { key: 'supplier_name', label: 'Proveedor' },
  { key: 'status', label: 'Estado' },
  { key: 'approval_status', label: 'Aprobación' },
  { key: 'order_date', label: 'Fecha' },
  { key: 'notes', label: 'Notas' },
  { key: 'created_by_name', label: 'Creado por' },
]

const statusLabels = {
  draft: 'borrador',
  sent: 'enviado',
  received: 'recibido',
  cancelled: 'cancelado',
}

const approvalStatusLabels = {
  pending: 'Pendiente de aprobación',
  approved: 'Aprobada',
  rejected: 'Rechazada',
}

async function fetchData() {
  loading.value = true
  try {
    const params = new URLSearchParams({ page: String(page.value), page_size: String(pageSize.value) })
    if (searchQuery.value) params.set('search', searchQuery.value)

    const res = await request(`/purchasing/orders/?${params}`)
    const envelope = await res.json()
    items.value = envelope.data ?? envelope.results ?? []
    total.value = envelope.meta?.total ?? envelope.count ?? items.value.length
  } catch (e: any) {
    console.error('Failed to fetch POs:', e)
  } finally {
    loading.value = false
  }
}

async function loadRefs() {
  try {
    const [supRes, prodRes] = await Promise.all([
      request('/purchasing/suppliers/?page_size=500'),
      request('/inventory/products/?page_size=500'),
    ])
    const supEnv = await supRes.json()
    const prodEnv = await prodRes.json()
    suppliers.value = supEnv.data ?? supEnv.results ?? []
    products.value = prodEnv.data ?? prodEnv.results ?? []
  } catch (e) { console.error('Failed to load refs:', e) }
}

onMounted(() => { loadRefs(); fetchData() })

function changePage(p: number) { page.value = p; fetchData() }
function handleSearch(q: string) { searchQuery.value = q; page.value = 1; fetchData() }

function openCreate() {
  editing.value = null
  form.supplier = ''
  form.notes = ''
  form.line_items = [{ product: '', quantity: 1, unit_cost: 0 }]
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
      supplier: form.supplier,
      notes: form.notes,
      line_items_write: form.line_items
        .filter(li => li.product)
        .map(li => ({ product: li.product, quantity: li.quantity, unit_cost: li.unit_cost })),
    }

    if (!payload.supplier || payload.line_items_write.length === 0) {
      throw new Error('El proveedor y al menos una línea son requeridos.')
    }

    const res = await request('/purchasing/orders/', {
      method: 'POST', body: JSON.stringify(payload),
    })
    if (!res.ok) {
      const e = await res.json()
      throw new Error(e.errors?.[0]?.message || e.errors?.detail || 'Error al guardar')
    }
    modalOpen.value = false
    fetchData()
  } catch (e: any) {
    saveError.value = e.message
  } finally {
    saving.value = false
  }
}

async function handleSend(row: any) {
  if (!confirm(`¿Enviar OC a "${row.supplier_name}"?`)) return
  const res = await request(`/purchasing/orders/${row.id}/send/`, { method: 'POST' })
  if (!res.ok) {
    const e = await res.json()
    alert(e.errors?.[0]?.message || 'Error al enviar la orden')
  }
  fetchData()
}

async function handleReceive(row: any) {
  if (!confirm(`¿Marcar OC como recibida? Se incrementará la existencia.`)) return
  const res = await request(`/purchasing/orders/${row.id}/receive/`, { method: 'POST' })
  if (!res.ok) {
    const e = await res.json()
    alert(e.errors?.[0]?.message || 'Error al recibir la orden')
  }
  fetchData()
}

async function handleApprove(row: any) {
  if (!confirm(`¿Aprobar OC para "${row.supplier_name}"?`)) return
  const res = await request(`/purchasing/orders/${row.id}/approve/`, { method: 'POST' })
  if (!res.ok) {
    const e = await res.json()
    alert(e.errors?.[0]?.message || 'Error al aprobar la orden')
  }
  fetchData()
}

async function handleReject(row: any) {
  if (!confirm(`¿Rechazar OC para "${row.supplier_name}"?`)) return
  const res = await request(`/purchasing/orders/${row.id}/reject/`, { method: 'POST' })
  if (!res.ok) {
    const e = await res.json()
    alert(e.errors?.[0]?.message || 'Error al rechazar la orden')
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
