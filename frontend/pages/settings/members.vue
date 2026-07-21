<template>
  <div class="page-container">
    <div class="page-header">
      <h1>Miembros</h1>
      <button class="btn btn-primary" @click="showInvite = true">+ Agregar Miembro</button>
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
                  class="form-input form-input-sm"
                  style="min-width:140px"
                  :disabled="m._saving || m.user === currentUserId"
                  @change="handleRoleChange(m)"
                >
                  <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.name }}</option>
                </select>
                <span v-if="m._saving">…</span>
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

    <!-- Simple Invite -->
    <div v-if="showInvite" class="modal-overlay" @click.self="showInvite = false">
      <div class="modal-container">
        <div class="modal-header">
          <h3>Agregar Miembro</h3>
          <button class="modal-close" @click="showInvite = false">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>Email</label>
            <input v-model="inviteEmail" class="form-input" placeholder="usuario@email.com" autocomplete="off" />
          </div>
          <div class="form-group">
            <label>Rol</label>
            <select v-model="inviteRole" class="form-input">
              <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.name }}</option>
            </select>
          </div>
          <p v-if="inviteError" class="form-error">{{ inviteError }}</p>
          <div class="modal-footer">
            <button class="btn-cancel" @click="showInvite = false">Cancelar</button>
            <button class="btn-save" :disabled="saving" @click="doInvite">{{ saving ? 'Agregando…' : 'Agregar' }}</button>
          </div>
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
const saving = ref(false)

const isOwner = computed(() => user.value?.active_membership?.is_owner ?? false)
const currentUserId = computed(() => user.value?.id)

async function fetchData() {
  loading.value = true
  try {
    const [mRes, rRes] = await Promise.all([
      request('/memberships/?page_size=200'),
      request('/roles/?page_size=200'),
    ])
    const mEnv = await mRes.json()
    const rEnv = await rRes.json()
    roles.value = rEnv.data ?? rEnv.results ?? []
    const data = mEnv.data ?? mEnv.results ?? []
    members.value = data.map((m: any) => ({
      ...m,
      _selectedRole: m.role || '',
      _saving: false,
    }))
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (!isOwner.value) { navigateTo('/'); return }
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
      alert(e.errors?.[0]?.message || 'Error')
      member._selectedRole = member.role
    }
  } catch (e: any) {
    alert(e.message)
    member._selectedRole = member.role
  } finally {
    member._saving = false
  }
}

async function doInvite() {
  inviteError.value = ''
  if (!inviteEmail.value || !inviteRole.value) {
    inviteError.value = 'Completá todos los campos.'
    return
  }
  saving.value = true
  try {
    const res = await request('/memberships/', {
      method: 'POST',
      body: JSON.stringify({
        invite_email: inviteEmail.value,
        role: inviteRole.value,
      }),
    })
    if (!res.ok) {
      const e = await res.json()
      throw new Error(e.errors?.[0]?.message || 'Error')
    }
    showInvite.value = false
    inviteEmail.value = ''
    inviteRole.value = ''
    await fetchData()
  } catch (e: any) {
    inviteError.value = e.message
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.page-container { padding: 1.5rem 2rem; max-width: 1100px; }
.table-loading { padding: 2rem; text-align: center; color: var(--color-muted); }
.table-responsive { overflow-x: auto; }
.empty-row { text-align: center; color: var(--color-muted); padding: 2rem; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-container { background: #fff; border-radius: 8px; width: 90%; max-width: 450px; }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 1rem 1.5rem; border-bottom: 1px solid #eee; }
.modal-header h3 { margin: 0; }
.modal-close { background: none; border: none; font-size: 1.5rem; cursor: pointer; }
.modal-body { padding: 1.5rem; }
.modal-footer { display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #eee; }
.form-group { margin-bottom: 1rem; }
.form-group label { display: block; margin-bottom: 0.25rem; font-weight: 500; }
.form-input { width: 100%; padding: 0.5rem; border: 1px solid #ccc; border-radius: 4px; font-size: 0.9rem; box-sizing: border-box; }
.form-error { color: #d32f2f; font-size: 0.85rem; margin-top: 0.5rem; }
.btn-cancel { padding: 0.5rem 1rem; border: 1px solid #ccc; border-radius: 4px; background: #fff; cursor: pointer; }
.btn-save { padding: 0.5rem 1.25rem; border: none; border-radius: 4px; background: #4F46E5; color: #fff; cursor: pointer; }
.btn-save:disabled { opacity: 0.6; }
.badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 10px; font-size: 0.7rem; font-weight: 600; }
.badge-sent { background: #dbeafe; color: #1d4ed8; }
.text-muted { color: #999; }
</style>
