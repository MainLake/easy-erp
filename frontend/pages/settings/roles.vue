<template>
  <div class="page-container">
    <div class="page-header">
      <h1>Roles y Permisos</h1>
      <button class="btn btn-primary" @click="openCreate">+ Nuevo Rol</button>
    </div>

    <DataTable
      :columns="columns"
      :data="roles"
      :loading="loading"
      :searchable="false"
    >
      <template #cell-permissionCount="{ row }">{{ row._count ?? 0 }}</template>
      <template #actions="{ row }">
        <button class="btn-sm" @click="openEdit(row)">Editar</button>
        <button class="btn-sm btn-sm-danger" @click="handleDelete(row)">Eliminar</button>
      </template>
    </DataTable>

    <!-- Role Create/Edit Modal with Permission Matrix -->
    <Teleport to="body">
      <div v-if="modalOpen" class="modal-overlay" @click.self="modalOpen = false">
        <div class="modal-container modal-wide">
          <div class="modal-header">
            <h3>{{ editing ? 'Editar Rol' : 'Nuevo Rol' }}</h3>
            <button class="modal-close" @click="modalOpen = false">&times;</button>
          </div>
          <div class="modal-body">
            <!-- Name -->
            <div class="form-group">
              <label for="role-name">Nombre <span class="required">*</span></label>
              <input
                id="role-name"
                v-model="form.name"
                class="form-input"
                required
                placeholder="Ej. Vendedor"
                @blur="validateName"
              />
              <p v-if="nameError" class="form-error-inline">{{ nameError }}</p>
            </div>

            <!-- Permission Matrix -->
            <h4 class="matrix-title">Permisos</h4>
            <div class="permission-matrix">
              <table class="matrix-table">
                <thead>
                  <tr>
                    <th class="module-col">Módulo</th>
                    <th v-for="action in ACTIONS" :key="action" class="action-col">
                      {{ actionLabels[action] }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="mod in MODULES" :key="mod">
                    <td class="module-label">{{ moduleLabels[mod] }}</td>
                    <td v-for="action in ACTIONS" :key="action" class="checkbox-col">
                      <label class="checkbox-cell" :class="{ 'checkbox-disabled': isActionDisabled(mod, action) }">
                        <input
                          type="checkbox"
                          :checked="hasChecked(mod, action)"
                          :disabled="isActionDisabled(mod, action)"
                          @change="togglePermission(mod, action)"
                        />
                      </label>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <p v-if="saveError" class="form-error">{{ saveError }}</p>
            <div class="modal-footer">
              <button type="button" class="btn-cancel" @click="modalOpen = false">Cancelar</button>
              <button type="button" class="btn-save" @click="handleSave" :disabled="saving">
                {{ saving ? 'Guardando…' : 'Guardar' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Delete Confirmation Modal -->
    <Teleport to="body">
      <div v-if="deleteModalOpen" class="modal-overlay" @click.self="deleteModalOpen = false">
        <div class="modal-container">
          <div class="modal-header">
            <h3>Eliminar Rol</h3>
            <button class="modal-close" @click="deleteModalOpen = false">&times;</button>
          </div>
          <div class="modal-body">
            <p v-if="deleteBlocked" class="warning-message">
              {{ deleteWarning }}
            </p>
            <p v-else>
              ¿Estás seguro de eliminar el rol <strong>{{ deletingRole?.name }}</strong>?
            </p>
            <div class="modal-footer">
              <button type="button" class="btn-cancel" @click="deleteModalOpen = false">Cancelar</button>
              <button
                v-if="!deleteBlocked"
                type="button"
                class="btn-save btn-danger"
                @click="confirmDelete"
                :disabled="deleteSaving"
              >
                {{ deleteSaving ? 'Eliminando…' : 'Eliminar' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'

definePageMeta({ middleware: 'auth' })

const { request } = useApi()
const { user } = useAuth()
const { MODULES, ACTIONS, moduleLabels, permissionCount } = usePermission()

// ---- static state ----
const actionLabels: Record<string, string> = {
  read: 'Ver',
  write: 'Editar',
  admin: 'Administrar',
}

const columns = [
  { key: 'name', label: 'Nombre' },
  { key: 'permissionCount', label: 'Permisos' },
]

// ---- reactive state ----
const roles = ref<any[]>([])
const loading = ref(false)

const modalOpen = ref(false)
const editing = ref<any>(null)
const saving = ref(false)
const saveError = ref('')
const nameError = ref('')

const form = reactive({
  name: '',
  permissions: {} as Record<string, string[]>,
})

const deleteModalOpen = ref(false)
const deletingRole = ref<any>(null)
const deleteSaving = ref(false)
const deleteBlocked = ref(false)
const deleteWarning = ref('')

// ---- computed ----
const isOwner = computed(() => user.value?.active_membership?.is_owner ?? false)

// ---- data fetching ----
async function fetchRoles() {
  loading.value = true
  try {
    const res = await request('/roles/?page_size=200')
    const envelope = await res.json()
    const raw = envelope.data ?? envelope.results ?? []
    roles.value = raw.map((r: any) => ({
      ...r,
      _count: permissionCount(r.permissions ?? {}),
    }))
  } catch (e: any) {
    console.error('Failed to fetch roles:', e)
  } finally {
    loading.value = false
  }
}

// Wait for user to be loaded, then check ownership
watch(() => user.value, (val) => {
  if (val) {
    if (!isOwner.value) {
      navigateTo('/')
    } else {
      fetchRoles()
    }
  }
}, { immediate: true })

// ---- permission matrix helpers ----
function hasChecked(mod: string, action: string): boolean {
  return form.permissions[mod]?.includes(action) ?? false
}

function isActionDisabled(mod: string, action: string): boolean {
  // Never disable — let users click freely.
  // The togglePermission() function handles cascading (auto-check/uncheck).
  return false
}

function togglePermission(mod: string, action: string) {
  if (!form.permissions[mod]) {
    form.permissions[mod] = []
  }

  const current = new Set(form.permissions[mod])

  if (current.has(action)) {
    // Uncheck: also remove higher actions that depend on this one
    if (action === 'read') {
      current.delete('read')
      current.delete('write')
      current.delete('admin')
    } else if (action === 'write') {
      current.delete('write')
      current.delete('admin')
    } else {
      current.delete('admin')
    }
  } else {
    // Check: also add lower actions implied by this one
    if (action === 'admin') {
      current.add('admin')
      current.add('write')
      current.add('read')
    } else if (action === 'write') {
      current.add('write')
      current.add('read')
    } else {
      current.add('read')
    }
  }

  form.permissions[mod] = [...current]

  // Remove module key if empty
  if (form.permissions[mod].length === 0) {
    delete form.permissions[mod]
  }
}

// ---- name validation ----
async function validateName() {
  nameError.value = ''
  if (!form.name.trim()) {
    nameError.value = 'El nombre es requerido.'
    return
  }
  // Check uniqueness against loaded roles (excluding current editing role)
  const duplicate = roles.value.find(r =>
    r.name.toLowerCase() === form.name.trim().toLowerCase() &&
    r.id !== editing.value?.id
  )
  if (duplicate) {
    nameError.value = 'Ya existe un rol con ese nombre.'
  }
}

// ---- CRUD ----
function resetForm() {
  form.name = ''
  form.permissions = {}
}

function openCreate() {
  editing.value = null
  resetForm()
  saveError.value = ''
  nameError.value = ''
  modalOpen.value = true
}

function openEdit(role: any) {
  editing.value = role
  form.name = role.name
  form.permissions = { ...(role.permissions ?? {}) }
  saveError.value = ''
  nameError.value = ''
  modalOpen.value = true
}

async function handleSave() {
  saveError.value = ''

  // Validate name
  if (!form.name.trim()) {
    saveError.value = 'El nombre es requerido.'
    return
  }
  await validateName()
  if (nameError.value) {
    saveError.value = nameError.value
    return
  }

  saving.value = true

  // Clean empty arrays from permissions
  const cleanPermissions: Record<string, string[]> = {}
  for (const [mod, actions] of Object.entries(form.permissions)) {
    if (actions.length > 0) cleanPermissions[mod] = [...actions]
  }

  const payload = {
    name: form.name.trim(),
    permissions: cleanPermissions,
  }

  try {
    if (editing.value?.id) {
      const res = await request(`/roles/${editing.value.id}/`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const e = await res.json()
        throw new Error(e.errors?.[0]?.message || 'Error al actualizar')
      }
    } else {
      const res = await request('/roles/', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const e = await res.json()
        throw new Error(e.errors?.[0]?.message || 'Error al crear')
      }
    }
    modalOpen.value = false
    fetchRoles()
  } catch (e: any) {
    saveError.value = e.message || 'Error al guardar'
  } finally {
    saving.value = false
  }
}

// ---- Delete with guard ----
function handleDelete(role: any) {
  deletingRole.value = role
  deleteBlocked.value = false
  deleteWarning.value = ''

  // Check if this is the last role with core:admin
  const otherAdminRoles = roles.value.filter(r =>
    r.id !== role.id &&
    r.permissions?.core?.includes('admin')
  )

  if (role.permissions?.core?.includes('admin') && otherAdminRoles.length === 0) {
    deleteBlocked.value = true
    deleteWarning.value = 'Este es el único rol administrador. No se puede eliminar.'
  }

  deleteSaving.value = false
  deleteModalOpen.value = true
}

async function confirmDelete() {
  if (!deletingRole.value) return
  deleteSaving.value = true
  try {
    const res = await request(`/roles/${deletingRole.value.id}/`, { method: 'DELETE' })
    if (!res.ok) {
      const e = await res.json()
      throw new Error(e.errors?.[0]?.message || 'Error al eliminar')
    }
    deleteModalOpen.value = false
    fetchRoles()
  } catch (e: any) {
    alert(e.message || 'Error al eliminar')
  } finally {
    deleteSaving.value = false
  }
}
</script>

<style scoped>
.page-container {
  padding: 1.5rem 2rem;
  max-width: 1100px;
}

.matrix-title {
  margin: 1.25rem 0 0.5rem;
  font-weight: 600;
  color: var(--color-heading);
  font-size: 0.95rem;
}

.permission-matrix {
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.matrix-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.matrix-table th,
.matrix-table td {
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--color-border-light);
  text-align: center;
}

.matrix-table thead th {
  background: #f8fafc;
  color: var(--color-muted);
  font-weight: 600;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.module-col {
  text-align: left !important;
  width: 40%;
}

.action-col {
  width: 20%;
}

.module-label {
  text-align: left !important;
  font-weight: 500;
  color: var(--color-heading);
}

.checkbox-col {
  padding: 0.35rem 0.5rem !important;
}

.checkbox-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  padding: 0.25rem;
  border-radius: var(--radius-sm);
  transition: background 0.12s;
}

.checkbox-cell:hover:not(.checkbox-disabled) {
  background: var(--color-primary-light);
}

.checkbox-disabled {
  cursor: default;
  opacity: 0.5;
}

.checkbox-cell input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.checkbox-disabled input[type="checkbox"] {
  cursor: default;
}

.form-error-inline {
  color: var(--color-error);
  font-size: 0.78rem;
  margin-top: 0.25rem;
}

.warning-message {
  color: var(--color-error);
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: var(--radius-sm);
  padding: 0.75rem 1rem;
  font-size: 0.88rem;
  line-height: 1.5;
}

.btn-danger {
  background: var(--color-error) !important;
}

.btn-danger:hover:not(:disabled) {
  background: #dc2626 !important;
}

/* Modal styles */
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
  max-width: 620px;
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
