<template>
  <div class="page-container">
    <div class="page-header">
      <h1>Facturas</h1>
      <button v-if="hasPermission('invoicing', 'write')" class="btn btn-primary" @click="openGenerate">+ Generar Factura</button>
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
      <template #cell-number="{ value }">{{ value || '—' }}</template>
      <template #cell-organization_name="{ value }">{{ value || '—' }}</template>
      <template #cell-customer_name="{ value }">{{ value || '—' }}</template>
      <template #cell-total="{ value }">${{ Number(value).toFixed(2) }}</template>
      <template #cell-status="{ value }">
        <span :class="`badge badge-${value}`">{{ (statusLabels as any)[value] || value }}</span>
      </template>
      <template #cell-issued_date="{ value }">{{ value ? new Date(value).toLocaleDateString() : '—' }}</template>
      <template #actions="{ row }">
        <button class="btn-sm" @click="openView(row)">Ver</button>
      </template>
    </DataTable>

    <!-- Generate Invoice Modal -->
    <Teleport to="body">
      <div v-if="genModalOpen" class="modal-overlay" @click.self="genModalOpen = false">
        <div class="modal-container">
          <div class="modal-header">
            <h3>Generar Factura</h3>
            <button class="modal-close" @click="genModalOpen = false">×</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>Orden de Venta Completada <span class="required">*</span></label>
              <select v-model="genForm.sales_order_id" class="form-input">
                <option value="">-- Seleccionar OV --</option>
                <option v-for="so in fulfilledOrders" :key="so.id" :value="so.id">
                  SO {{ so.id.slice(0, 8) }} — {{ so.customer_name }}
                </option>
              </select>
            </div>
            <p v-if="genError" class="form-error">{{ genError }}</p>
            <div class="modal-footer">
              <button class="btn-cancel" @click="genModalOpen = false">Cancelar</button>
              <button class="btn-save" @click="handleGenerate" :disabled="genSaving">
                {{ genSaving ? 'Generando…' : 'Generar' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- View Invoice Detail -->
    <Teleport to="body">
      <div v-if="viewModalOpen" class="modal-overlay" @click.self="viewModalOpen = false">
        <div class="modal-container modal-wide">
          <div class="modal-header">
            <h3>Factura {{ viewing?.number || `#${viewing?.id?.slice(0, 8)}` }}</h3>
            <button class="modal-close" @click="viewModalOpen = false">×</button>
          </div>
          <div class="modal-body">
            <div class="detail-grid">
              <div><strong>Organización:</strong> {{ viewing?.organization_name || '—' }}</div>
              <div><strong>Cliente:</strong> {{ viewing?.customer_name || '—' }}</div>
              <div><strong>Estado:</strong> <span :class="`badge badge-${viewing?.status}`">{{ (statusLabels as any)[viewing?.status] || viewing?.status }}</span></div>
              <div><strong>Total:</strong> ${{ Number(viewing?.total || 0).toFixed(2) }}</div>
              <div><strong>Emitido:</strong> {{ viewing?.issued_date ? new Date(viewing.issued_date).toLocaleDateString() : '—' }}</div>
              <div></div>
            </div>

            <h4 style="margin-top: 1.5rem;margin-bottom:0.5rem;font-weight:600;color:var(--color-heading);">Notas de Crédito / Débito</h4>
            <table v-if="(viewing?.notes ?? []).length" class="line-items-table">
              <thead><tr><th>Tipo</th><th>Monto</th><th>Motivo</th><th>Número</th></tr></thead>
              <tbody>
                <tr v-for="n in viewing?.notes" :key="n.id">
                  <td><span :class="`badge badge-${n.type}`">{{ n.type_display || n.type }}</span></td>
                  <td>${{ Number(n.amount).toFixed(2) }}</td>
                  <td>{{ n.reason || '—' }}</td>
                  <td>{{ n.number || '—' }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="text-muted">Sin notas de crédito/débito.</p>
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

const fulfilledOrders = ref<any[]>([])

const genModalOpen = ref(false)
const genSaving = ref(false)
const genError = ref('')
const genForm = reactive({ sales_order_id: '' })

const viewModalOpen = ref(false)
const viewing = ref<any>(null)

const columns = [
  { key: 'number', label: 'Factura #' },
  { key: 'organization_name', label: 'Organización' },
  { key: 'customer_name', label: 'Cliente' },
  { key: 'total', label: 'Total' },
  { key: 'status', label: 'Estado' },
  { key: 'issued_date', label: 'Emitido' },
]

const statusLabels = {
  draft: 'borrador',
  issued: 'emitido',
  cancelled: 'cancelado',
}

async function fetchData() {
  loading.value = true
  try {
    const params = new URLSearchParams({ page: String(page.value), page_size: String(pageSize.value) })
    if (searchQuery.value) params.set('search', searchQuery.value)

    const res = await request(`/invoicing/invoices/?${params}`)
    const envelope = await res.json()
    items.value = envelope.data ?? envelope.results ?? []
    total.value = envelope.meta?.total ?? envelope.count ?? items.value.length
  } catch (e: any) {
    console.error('Failed to fetch invoices:', e)
  } finally {
    loading.value = false
  }
}

async function loadFulfilledOrders() {
  try {
    const res = await request('/sales/orders/?status=fulfilled&page_size=500')
    const envelope = await res.json()
    fulfilledOrders.value = (envelope.data ?? envelope.results ?? []).filter((so: any) => so.status === 'fulfilled')
  } catch (e) { console.error('Failed to load fulfilled SOs:', e) }
}

onMounted(() => { fetchData() })

function changePage(p: number) { page.value = p; fetchData() }
function handleSearch(q: string) { searchQuery.value = q; page.value = 1; fetchData() }

function openGenerate() {
  genForm.sales_order_id = ''
  genError.value = ''
  loadFulfilledOrders()
  genModalOpen.value = true
}

async function handleGenerate() {
  genError.value = ''
  genSaving.value = true
  try {
    if (!genForm.sales_order_id) throw new Error('Seleccione una orden de venta completada.')
    const res = await request('/invoicing/invoices/generate/', {
      method: 'POST',
      body: JSON.stringify({ sales_order_id: genForm.sales_order_id }),
    })
    if (!res.ok) {
      const e = await res.json()
      throw new Error(e.errors?.[0]?.message || e.errors?.detail || 'Error al generar')
    }
    genModalOpen.value = false
    fetchData()
  } catch (e: any) {
    genError.value = e.message
  } finally {
    genSaving.value = false
  }
}

function openView(row: any) {
  viewing.value = row
  viewModalOpen.value = true
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
  max-width: 720px;
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
