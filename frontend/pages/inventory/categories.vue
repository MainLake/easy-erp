<template>
  <div class="page-container">
    <div class="page-header">
      <h1>Categorías</h1>
      <button v-if="hasPermission('inventory', 'write')" class="btn btn-primary" @click="openCreate">+ Nueva Categoría</button>
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
      <template #cell-parent="{ value }">{{ value ? parentMap[value] : '—' }}</template>
      <template #actions="{ row }">
        <button v-if="hasPermission('inventory', 'write')" class="btn-sm" @click="openEdit(row)">Editar</button>
        <button v-if="hasPermission('inventory', 'admin')" class="btn-sm btn-sm-danger" @click="handleDelete(row)">Eliminar</button>
      </template>
    </DataTable>

    <CrudModal
      :title="editing ? 'Editar Categoría' : 'Nueva Categoría'"
      :visible="modalOpen"
      :fields="formFields"
      :initial-data="editing ?? undefined"
      @save="handleSave"
      @close="modalOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

definePageMeta({ middleware: 'auth' })

const { request } = useApi()
const { hasPermission } = usePermission()

const items = ref<any[]>([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const searchQuery = ref('')

const modalOpen = ref(false)
const editing = ref<any>(null)

const allCategories = ref<any[]>([])

const columns = [
  { key: 'name', label: 'Nombre' },
  { key: 'parent', label: 'Categoría Padre' },
]

const parentMap = computed(() => {
  const map: Record<string, string> = {}
  for (const c of allCategories.value) map[c.id] = c.name
  return map
})

const formFields = computed(() => [
  { name: 'name', label: 'Nombre', required: true },
  {
    name: 'parent',
    label: 'Categoría Padre',
    type: 'select' as const,
    options: allCategories.value
      .filter((c: any) => c.id !== editing.value?.id)
      .map((c: any) => ({ value: c.id, label: c.name })),
  },
])

async function fetchData() {
  loading.value = true
  try {
    const params = new URLSearchParams({ page: String(page.value), page_size: String(pageSize.value) })
    if (searchQuery.value) params.set('search', searchQuery.value)

    const res = await request(`/inventory/categories/?${params}`)
    const envelope = await res.json()
    items.value = envelope.data ?? envelope.results ?? []
    total.value = envelope.meta?.total ?? envelope.count ?? items.value.length
  } catch (e: any) {
    console.error('Failed to fetch categories:', e)
  } finally {
    loading.value = false
  }
}

async function loadAll() {
  try {
    const res = await request('/inventory/categories/?page_size=500')
    const envelope = await res.json()
    allCategories.value = envelope.data ?? envelope.results ?? []
  } catch { /* non-critical */ }
}

onMounted(() => {
  loadAll()
  fetchData()
})

function changePage(p: number) { page.value = p; fetchData() }
function handleSearch(q: string) { searchQuery.value = q; page.value = 1; fetchData() }

function openCreate() { editing.value = null; modalOpen.value = true }
function openEdit(row: any) { editing.value = { ...row }; modalOpen.value = true }

async function handleSave(payload: Record<string, any>) {
  if (editing.value?.id) {
    const res = await request(`/inventory/categories/${editing.value.id}/`, {
      method: 'PUT', body: JSON.stringify(payload),
    })
    if (!res.ok) { const e = await res.json(); throw new Error(e.errors?.[0]?.message || 'Error al actualizar') }
  } else {
    const res = await request('/inventory/categories/', {
      method: 'POST', body: JSON.stringify(payload),
    })
    if (!res.ok) { const e = await res.json(); throw new Error(e.errors?.[0]?.message || 'Error al crear') }
  }
  modalOpen.value = false
  loadAll()
  fetchData()
}

async function handleDelete(row: any) {
  if (!confirm(`¿Eliminar categoría "${row.name}"?`)) return
  const res = await request(`/inventory/categories/${row.id}/`, { method: 'DELETE' })
  if (!res.ok) {
    const e = await res.json()
    alert(e.errors?.[0]?.message || 'Error al eliminar')
  }
  fetchData()
}
</script>

<style scoped>
.page-container {
  padding: 1.5rem 2rem;
  max-width: 1280px;
}
</style>
