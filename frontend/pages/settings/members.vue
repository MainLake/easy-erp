<template>
  <div class="page-container">
    <div class="page-header">
      <h1>Miembros</h1>
      <button class="btn btn-primary" @click="openInvite">+ Agregar Miembro</button>
    </div>

    <div class="card">
      <div v-if="loading" class="table-loading">Cargando…</div>

      <div v-else class="table-responsive">
        <table class="data-table">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Email</th>
              <th>Rol</th>
              <th>Dueño</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in members" :key="m.id">
              <td>{{ m.user_name }}</td>
              <td>{{ m.user_email }}</td>
              <td>
                <select
                  v-model="m._selectedRole"
                  class="form-input form-input-sm role-select"
                  :disabled="m._saving || m.user === currentUserId"
                  @change="handleRoleChange(m)"
                >
                  <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.name }}</option>
                </select>
                <span v-if="m._saving" class="spinner" />
              </td>
              <td>
                <span v-if="m.is_owner" class="badge badge-sent">Owner</span>
                <span v-else class="text-muted">—</span>
              </td>
            </tr>
            <tr v-if="members.length === 0">
              <td colspan="4" class="empty-row">No se encontraron miembros.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Invite Modal -->
    <div v-if="showInvite" class="modal-overlay" @click.self="showInvite = false">
      <div class="modal-container">
        <div class="modal-header">
          <h3>Agregar Miembro</h3>
          <button class="modal-close" @click="showInvite = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>Email del usuario</label>
            <input v-model="inviteEmail" type="email" class="form-input" placeholder="usuario@ejemplo.com" />
          </div>
          <div class="form-group">
            <label>Rol</label>
            <select v-model="inviteRole" class="form-input">
              <option value="" disabled>Seleccionar rol</option>
              <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.name }}</option>
            </select>
          </div>
          <p v-if="inviteError" class="form-error">{{ inviteError }}</p>
        </div>
        <div class="modal-footer">
          <button class="btn-cancel" @click="showInvite = false">Cancelar</button>
          <button class="btn-save" :disabled="inviteSaving" @click="handleInvite">
            {{ inviteSaving ? 'Agregando…' : 'Agregar' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

definePageMeta({ middleware: 'auth' })

const { request } = useApi()
const { user } = useAuth()

const members = ref<any[]>([])
const roles = ref<any[]>([])
const loading = ref(false)

const showInvite = ref(false)
const inviteEmail = ref('')
const inviteRole = ref('')
const inviteError = ref('')
const inviteSaving = ref(false)

const isOwner = computed(() => user.value?.active_membership?.is_owner ?? false)
const currentUserId = computed(() => user.value?.id)

async function fetchData() {
  loading.value = true
  try {
    const [membersRes, rolesRes] = await Promise.all([
      request('/memberships/?page_size=200'),
      request('/roles/?page_size=200'),
    ])
    const membersEnvelope = await membersRes.json()
    const rolesEnvelope = await rolesRes.json()

    roles.value = rolesEnvelope.data ?? rolesEnvelope.results ?? []

    const membersData = membersEnvelope.data ?? membersEnvelope.results ?? []
    members.value = membersData.map((m: any) => ({
      ...m,
      user_name: m.user_name || '—',
      user_email: m.user_email || '—',
      _selectedRole: m.role || '',
      _saving: false,
    }))
  } catch (e: any) {
    console.error('Failed to fetch members or roles:', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (!isOwner.value) {
    navigateTo('/')
    return
  }
  fetchData()
})

async function handleRoleChange(member: any) {
  if (!member._selectedRole || member._saving) return
  member._saving = true
  try {
    const res = await request(`/memberships/${member.id}/`, {
      method: 'PATCH',
      body: JSON.stringify({ role: member._selectedRole }),
    })
    if (!res.ok) {
      const e = await res.json()
      alert(e.errors?.[0]?.message || 'Error al cambiar el rol')
      member._selectedRole = member.role
    }
  } catch (e: any) {
    alert(e.message || 'Error al cambiar el rol')
    member._selectedRole = member.role
  } finally {
    member._saving = false
  }
}

function openInvite() {
  inviteEmail.value = ''
  inviteRole.value = roles.value[0]?.id || ''
  inviteError.value = ''
  showInvite.value = true
}

async function handleInvite() {
  inviteError.value = ''
  if (!inviteEmail.value || !inviteRole.value) {
    inviteError.value = 'Completá todos los campos.'
    return
  }
  inviteSaving.value = true
  try {
    const res = await request('/memberships/', {
      method: 'POST',
      body: JSON.stringify({
        user_email: inviteEmail.value,
        role: inviteRole.value,
      }),
    })
    if (!res.ok) {
      const e = await res.json()
      throw new Error(e.errors?.[0]?.message || e.detail || 'Error al agregar miembro')
    }
    showInvite.value = false
    await fetchData()
  } catch (e: any) {
    inviteError.value = e.message
  } finally {
    inviteSaving.value = false
  }
}
</script>

<style scoped>
.page-container {
  padding: 1.5rem 2rem;
  max-width: 1100px;
}

.table-loading {
  padding: 2rem;
  text-align: center;
  color: var(--color-muted);
}

.table-responsive {
  overflow-x: auto;
}

.role-select {
  min-width: 150px;
}

.empty-row {
  text-align: center;
  color: var(--color-muted);
  padding: 2rem;
}

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.5s linear infinite;
  margin-left: 0.5rem;
  vertical-align: middle;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
