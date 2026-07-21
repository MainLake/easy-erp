<template>
  <div class="card">
    <div class="table-toolbar">
      <input
        v-if="searchable"
        v-model="searchQuery"
        type="text"
        placeholder="Buscar..."
        class="form-input search-input"
        @input="debouncedSearch"
      />
      <slot name="toolbar-actions" />
    </div>

    <div v-if="loading" class="table-loading">Cargando…</div>

    <div v-else class="table-responsive">
      <table class="data-table">
        <thead>
          <tr>
            <th
              v-for="col in columns"
              :key="col.key"
              :class="{ sortable: col.sortable !== false }"
              @click="col.sortable !== false && toggleSort(col.key)"
            >
              {{ col.label }}
              <span v-if="sortKey === col.key" class="sort-arrow">
                {{ sortDir === 'asc' ? '▲' : '▼' }}
              </span>
            </th>
            <th v-if="$slots.actions" class="actions-col">Acciones</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in data" :key="row.id ?? idx">
            <td v-for="col in columns" :key="col.key">
              <slot :name="`cell-${col.key}`" :row="row" :value="row[col.key]">
                {{ row[col.key] }}
              </slot>
            </td>
            <td v-if="$slots.actions" class="actions-col">
              <slot name="actions" :row="row" />
            </td>
          </tr>
          <tr v-if="data.length === 0">
            <td :colspan="columns.length + ($slots.actions ? 1 : 0)" class="empty-row">
              No se encontraron registros.
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="total > 0" class="table-pagination">
      <span class="page-info">
        Página {{ page }} de {{ totalPages }} ({{ total }} registros)
      </span>
      <div class="page-buttons">
        <button class="btn btn-secondary" :disabled="page <= 1" @click="$emit('page-change', page - 1)">← Anterior</button>
        <button class="btn btn-secondary" :disabled="page >= totalPages" @click="$emit('page-change', page + 1)">Siguiente →</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

export interface Column {
  key: string
  label: string
  sortable?: boolean
}

const props = withDefaults(defineProps<{
  columns: Column[]
  data: any[]
  loading?: boolean
  total?: number
  page?: number
  pageSize?: number
  searchable?: boolean
}>(), {
  loading: false,
  total: 0,
  page: 1,
  pageSize: 20,
  searchable: true,
})

const emit = defineEmits<{
  (e: 'page-change', page: number): void
  (e: 'sort', key: string, dir: 'asc' | 'desc'): void
  (e: 'search', query: string): void
}>()

const sortKey = ref('')
const sortDir = ref<'asc' | 'desc'>('asc')
const searchQuery = ref('')
let searchTimer: ReturnType<typeof setTimeout> | null = null

const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))

function toggleSort(key: string) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'asc'
  }
  emit('sort', sortKey.value, sortDir.value)
}

function debouncedSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    emit('search', searchQuery.value)
  }, 300)
}

watch(() => props.data, () => {
  // Reset local sort state when data changes externally
}, { deep: true })
</script>

<style scoped>
.card {
  background: var(--color-surface);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.85rem 1.25rem;
  border-bottom: 1px solid var(--color-border-light);
  gap: 1rem;
}

.search-input {
  width: 240px;
}

.table-responsive {
  overflow-x: auto;
}

.table-loading {
  padding: 3rem;
  text-align: center;
  color: var(--color-muted);
  font-size: 0.9rem;
}

.sort-arrow {
  font-size: 0.65rem;
  margin-left: 4px;
  color: var(--color-primary);
}

.actions-col {
  width: 130px;
  text-align: right;
}

.empty-row {
  text-align: center;
  padding: 3rem 1rem;
  color: var(--color-muted);
  font-size: 0.9rem;
}

.table-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.85rem 1.25rem;
  border-top: 1px solid var(--color-border-light);
  background: #fafbfc;
}

.page-info {
  font-size: 0.8rem;
  color: var(--color-muted);
}

.page-buttons {
  display: flex;
  gap: 0.5rem;
}

.page-buttons .btn {
  padding: 0.35rem 0.75rem;
  font-size: 0.8rem;
}
</style>
