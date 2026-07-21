<template>
  <div class="page-container">
    <div class="page-header">
      <h1>Miembros</h1>
    </div>

    <DataTable
      :columns="columns"
      :data="members"
      :loading="loading"
      :searchable="false"
    >
      <template #cell-role_name="{ row }">
        <div class="role-select-cell">
          <select
            v-model="row._selectedRole"
            class="form-input form-input-sm role-select"
            :disabled="row._saving || isSelf(row)"
            @change="handleRoleChange(row)"
          >
            <option
              v-for="role in roles"
              :key="role.id"
              :value="role.id"
            >
              {{ role.name }}
            </option>
          </select>
          <span v-if="row._saving" class="spinner" />
          <span
            v-if="isSelf(row)"
            class="tooltip-wrapper"
            :title="'No podés cambiar tu propio rol'"
          >
            ⓘ
          </span>
        </div>
      </template>
    </DataTable>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

definePageMeta({ middleware: 'auth' })

const { request } = useApi()
const { user } = useAuth()

// ---- state ----
const members = ref<any[]>([])
const roles = ref<any[]>([])
const loading = ref(false)

const columns = [
  { key: 'user_name', label: 'Nombre' },
  { key: 'user_email', label: 'Email' },
  { key: 'role_name', label: 'Rol' },
]

// ---- computed ----
const isOwner = computed(() => user.value?.active_membership?.is_owner ?? false)
const currentUserId = computed(() => user.value?.id)

// ---- data fetching ----
async function fetchData() {
  loading.value = true
  try {
    const [membersRes, rolesRes] = await Promise.all([
      request('/memberships/?page_size=200'),
      request('/roles/?page_size=200'),
    ])

    const membersEnvelope = await membersRes.json()
    const rolesEnvelope = await rolesRes.json()

    const rolesData: any[] = rolesEnvelope.data ?? rolesEnvelope.results ?? []
    roles.value = rolesData

    const membersData: any[] = membersEnvelope.data ?? membersEnvelope.results ?? []

    // Enrich members with display fields and current role selection
    members.value = membersData.map((m: any) => ({
      ...m,
      user_name: m.user_name ?? m.user?.full_name ?? '—',
      user_email: m.user_email ?? m.user?.email ?? '—',
      role_name: m.role?.name ?? '—',
      _selectedRole: m.role?.id ?? '',
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

// ---- helpers ----
function isSelf(member: any): boolean {
  return member.user === currentUserId.value
}

// ---- role change ----
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
      // Revert selection on failure
      member._selectedRole = member.role?.id ?? ''
    } else {
      // Update local role name on success
      const newRole = roles.value.find(r => r.id === member._selectedRole)
      member.role_name = newRole?.name ?? member.role_name
      member.role = { id: member._selectedRole, name: member.role_name }
    }
  } catch (e: any) {
    alert(e.message || 'Error al cambiar el rol')
    member._selectedRole = member.role?.id ?? ''
  } finally {
    member._saving = false
  }
}
</script>

<style scoped>
.page-container {
  padding: 1.5rem 2rem;
  max-width: 1100px;
}

.role-select-cell {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.role-select {
  min-width: 160px;
}

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.5s linear infinite;
}

.tooltip-wrapper {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--color-muted);
  font-size: 0.8rem;
  cursor: help;
  width: 18px;
  height: 18px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
