<template>
  <div class="page-container">
    <div class="page-header">
      <h1>Campos Personalizados</h1>
    </div>

    <!-- Model type tabs -->
    <div class="tabs">
      <button
        v-for="m in models"
        :key="m.value"
        class="tab"
        :class="{ active: selectedModel === m.value }"
        @click="selectModel(m.value)"
      >
        {{ m.label }}
      </button>
    </div>

    <!-- Add new field button -->
    <div class="toolbar">
      <button class="btn btn-primary" @click="openCreate">+ Nuevo Campo</button>
    </div>

    <!-- Fields table -->
    <table class="fields-table" v-if="fields.length > 0">
      <thead>
        <tr>
          <th>Nombre</th>
          <th>Tipo</th>
          <th>Requerido</th>
          <th>Opciones</th>
          <th>Orden</th>
          <th class="th-actions">Acciones</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="f in fields" :key="f.id">
          <td>{{ f.name }}</td>
          <td><span class="badge">{{ typeLabel(f.field_type) }}</span></td>
          <td>{{ f.required ? 'Sí' : 'No' }}</td>
          <td>{{ f.field_type === 'select' ? (f.options ?? []).join(', ') : '—' }}</td>
          <td>{{ f.order }}</td>
          <td class="td-actions">
            <button class="btn-sm" @click="openEdit(f)">Editar</button>
            <button class="btn-sm btn-sm-danger" @click="handleDelete(f)">Eliminar</button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else-if="!loading" class="text-muted">No hay campos personalizados definidos para este modelo.</p>

    <!-- Add / Edit Modal -->
    <Teleport to="body">
      <div v-if="modalOpen" class="modal-overlay" @click.self="modalOpen = false">
        <div class="modal-container">
          <div class="modal-header">
            <h3>{{ editing ? 'Editar Campo' : 'Nuevo Campo' }}</h3>
            <button class="modal-close" @click="modalOpen = false">×</button>
          </div>
          <form class="modal-body" @submit.prevent="handleSave">
            <div class="form-group">
              <label for="field-name">Nombre <span class="required">*</span></label>
              <input id="field-name" v-model="form.name" class="form-input" required placeholder="Ej. SKU" />
            </div>
            <div class="form-group">
              <label for="field-type">Tipo <span class="required">*</span></label>
              <select id="field-type" v-model="form.field_type" class="form-input" required>
                <option value="">-- Seleccionar --</option>
                <option value="text">Texto</option>
                <option value="number">Número</option>
                <option value="date">Fecha</option>
                <option value="select">Lista</option>
              </select>
            </div>
            <div class="form-group" v-if="form.field_type === 'select'">
              <label for="field-options">Opciones <span class="required">*</span></label>
              <input
                id="field-options"
                v-model="form.optionsText"
                class="form-input"
                required
                placeholder="Opción 1, Opción 2, Opción 3"
              />
              <small class="form-hint">Separar opciones con coma (,).</small>
            </div>
            <div class="form-group">
              <label for="field-order">Orden</label>
              <input id="field-order" v-model.number="form.order" type="number" min="0" class="form-input" />
            </div>
            <div class="form-group">
              <label class="checkbox-label">
                <input type="checkbox" v-model="form.required" />
                Requerido
              </label>
            </div>
            <p v-if="saveError" class="form-error">{{ saveError }}</p>
            <div class="modal-footer">
              <button type="button" class="btn-cancel" @click="modalOpen = false">Cancelar</button>
              <button type="submit" class="btn-save" :disabled="saving">
                {{ saving ? 'Guardando…' : 'Guardar' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'

definePageMeta({ middleware: 'auth' })

const { request } = useApi()
const { user } = useAuth()

const models = [
  { value: 'product', label: 'Productos' },
  { value: 'customer', label: 'Clientes' },
  { value: 'supplier', label: 'Proveedores' },
  { value: 'organization', label: 'Organización' },
]

const selectedModel = ref('product')
const fields = ref<any[]>([])
const loading = ref(false)

const modalOpen = ref(false)
const editing = ref<any>(null)
const saving = ref(false)
const saveError = ref('')

const emptyForm = () => ({
  name: '',
  field_type: '',
  required: false,
  optionsText: '',
  order: 0,
})

const form = reactive(emptyForm())

const isOwner = computed(() => {
  return user.value?.active_membership?.is_owner ?? false
})

function typeLabel(type: string): string {
  const map: Record<string, string> = {
    text: 'Texto',
    number: 'Número',
    date: 'Fecha',
    select: 'Lista',
  }
  return map[type] ?? type
}

async function fetchFields() {
  loading.value = true
  try {
    const res = await request(`/custom-fields/?model_name=${selectedModel.value}&page_size=200`)
    const envelope = await res.json()
    fields.value = envelope.data ?? envelope.results ?? []
  } catch (e: any) {
    console.error('Failed to fetch custom fields:', e)
  } finally {
    loading.value = false
  }
}

function selectModel(model: string) {
  selectedModel.value = model
  fetchFields()
}

onMounted(fetchFields)

// --- CRUD ---

function openCreate() {
  editing.value = null
  Object.assign(form, emptyForm())
  saveError.value = ''
  modalOpen.value = true
}

function openEdit(f: any) {
  editing.value = f
  Object.assign(form, {
    name: f.name,
    field_type: f.field_type,
    required: f.required,
    optionsText: (f.options ?? []).join(', '),
    order: f.order,
  })
  saveError.value = ''
  modalOpen.value = true
}

async function handleSave() {
  saveError.value = ''
  saving.value = true

  const payload: Record<string, any> = {
    model_name: selectedModel.value,
    name: form.name,
    field_type: form.field_type,
    required: form.required,
    order: form.order,
  }

  if (form.field_type === 'select') {
    payload.options = form.optionsText
      .split(',')
      .map((s: string) => s.trim())
      .filter((s: string) => s.length > 0)
    if (payload.options.length === 0) {
      saveError.value = 'Las opciones son requeridas para campos de tipo Lista.'
      saving.value = false
      return
    }
  } else {
    payload.options = null
  }

  try {
    if (editing.value?.id) {
      const res = await request(`/custom-fields/${editing.value.id}/`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const e = await res.json()
        throw new Error(e.errors?.[0]?.message || 'Error al actualizar')
      }
    } else {
      const res = await request('/custom-fields/', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const e = await res.json()
        throw new Error(e.errors?.[0]?.message || 'Error al crear')
      }
    }
    modalOpen.value = false
    fetchFields()
  } catch (e: any) {
    saveError.value = e.message || 'Error al guardar'
  } finally {
    saving.value = false
  }
}

async function handleDelete(f: any) {
  if (!confirm(`¿Eliminar el campo "${f.name}"? Se perderán todos los valores asociados.`)) return
  try {
    const res = await request(`/custom-fields/${f.id}/`, { method: 'DELETE' })
    if (!res.ok) {
      const e = await res.json()
      alert(e.errors?.[0]?.message || 'Error al eliminar')
    }
    fetchFields()
  } catch (e: any) {
    alert(e.message || 'Error al eliminar')
  }
}
</script>

<style scoped>
.page-container {
  padding: 1.5rem 2rem;
  max-width: 1100px;
}

.tabs {
  display: flex;
  gap: 0;
  border-bottom: 2px solid var(--color-border);
  margin-bottom: 1.25rem;
}

.tab {
  padding: 0.6rem 1.2rem;
  border: none;
  background: none;
  cursor: pointer;
  font-family: var(--font-family);
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--color-muted);
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: color 0.15s, border-color 0.15s;
}

.tab:hover {
  color: var(--color-body);
}

.tab.active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
  font-weight: 600;
}

.toolbar {
  margin-bottom: 1rem;
}

.fields-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
}

.fields-table th {
  text-align: left;
  padding: 0.6rem 0.75rem;
  font-weight: 600;
  color: var(--color-muted);
  border-bottom: 1px solid var(--color-border);
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.fields-table td {
  padding: 0.6rem 0.75rem;
  border-bottom: 1px solid var(--color-border-light);
}

.th-actions, .td-actions {
  text-align: right;
}

.badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 10px;
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-size: 0.75rem;
  font-weight: 500;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
}

.form-hint {
  font-size: 0.75rem;
  color: var(--color-muted);
  margin-top: 0.2rem;
  display: block;
}

.btn-sm-danger {
  background: #fff;
  border: 1px solid var(--color-error);
  color: var(--color-error);
}
.btn-sm-danger:hover {
  background: var(--color-error);
  color: #fff;
}

/* Modal styles (same as CrudModal) */
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
  max-width: 500px;
  max-height: 85vh;
  overflow-y: auto;
  box-shadow: var(--shadow-lg);
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
