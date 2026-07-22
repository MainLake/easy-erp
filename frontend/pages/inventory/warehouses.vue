<template>
  <div class="page-container">
    <div class="page-header">
      <h1>Almacenes</h1>
      <button class="btn btn-primary" @click="openCreate">+ Nuevo Almacén</button>
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
      <template #actions="{ row }">
        <button class="btn-sm" @click="openEdit(row)">Editar</button>
        <button class="btn-sm btn-sm-danger" @click="handleDelete(row)">Eliminar</button>
      </template>
    </DataTable>

    <CrudModal
      :title="editing ? 'Editar Almacén' : 'Nuevo Almacén'"
      :visible="modalOpen"
      :fields="formFields"
      :initial-data="editing ?? undefined"
      @save="handleSave"
      @close="modalOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

definePageMeta({ middleware: 'auth' })

const { request } = useApi()

const items = ref<any[]>([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const searchQuery = ref('')

const modalOpen = ref(false)
const editing = ref<any>(null)

const columns = [
  { key: 'name', label: 'Nombre' },
  { key: 'location', label: 'Ubicación' },
]

const formFields = [
  { name: 'name', label: 'Nombre', required: true },
  { name: 'location', label: 'Ubicación' },
]

async function fetchData() {
  loading.value = true
  try {
    const params = new URLSearchParams({ page: String(page.value), page_size: String(pageSize.value) })
    if (searchQuery.value) params.set('search', searchQuery.value)

    const res = await request(`/inventory/warehouses/?${params}`)
    const envelope = await res.json()
    items.value = envelope.data ?? envelope.results ?? []
    total.value = envelope.meta?.total ?? envelope.count ?? items.value.length
  } catch (e: any) {
    console.error('Failed to fetch warehouses:', e)
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)

function changePage(p: number) { page.value = p; fetchData() }
function handleSearch(q: string) { searchQuery.value = q; page.value = 1; fetchData() }

function openCreate() { editing.value = null; modalOpen.value = true }
function openEdit(row: any) { editing.value = { ...row }; modalOpen.value = true }

async function handleSave(payload: Record<string, any>) {
  if (editing.value?.id) {
    const res = await request(`/inventory/warehouses/${editing.value.id}/`, {
      method: 'PUT', body: JSON.stringify(payload),
    })
    if (!res.ok) { const e = await res.json(); throw new Error(e.errors?.[0]?.message || 'Error al actualizar') }
  } else {
    const res = await request('/inventory/warehouses/', {
      method: 'POST', body: JSON.stringify(payload),
    })
    if (!res.ok) { const e = await res.json(); throw new Error(e.errors?.[0]?.message || 'Error al crear') }
  }
  modalOpen.value = false
  fetchData()
}

async function handleDelete(row: any) {
  if (!confirm(`¿Eliminar almacén "${row.name}"?`)) return
  await request(`/inventory/warehouses/${row.id}/`, { method: 'DELETE' })
  fetchData()
}
</script>

<style scoped>
.page-container {
  padding: 1.5rem 2rem;
  max-width: 1280px;
}
</style>
