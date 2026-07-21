<template>
  <div class="select-org-page">
    <div class="select-org-card">
      <!-- Brand header -->
      <div class="select-org-brand">
        <div class="select-org-logo">E</div>
        <h1>Easy ERP</h1>
      </div>

      <h2>Seleccioná tu organización</h2>
      <p class="text-muted">Elegí la organización con la que querés trabajar</p>

      <!-- Loading skeleton -->
      <div v-if="loading && memberships.length === 0" class="text-center mt-5">
        <p class="text-muted">Cargando organizaciones…</p>
      </div>

      <!-- Empty state: user has no memberships (A7) -->
      <div v-else-if="memberships.length === 0" class="select-org-empty">
        <div class="empty-icon">👤</div>
        <p>No tenés organizaciones asignadas.</p>
        <p class="text-muted">Contactá a un administrador para que te asigne una organización.</p>
        <button class="btn btn-secondary mt-4" @click="logout()">Cerrar sesión</button>
      </div>

      <!-- Organization list -->
      <div v-else class="org-list">
        <button
          v-for="m in memberships"
          :key="m.id"
          class="org-list-item"
          :disabled="loading"
          @click="selectOrg(m.organization.id)"
        >
          <div class="org-list-item-icon">{{ m.organization.name.charAt(0) }}</div>
          <div class="org-list-item-info">
            <div class="org-list-item-name">{{ m.organization.name }}</div>
            <div class="org-list-item-role">{{ m.role.name }}</div>
          </div>
          <span class="org-list-item-arrow">→</span>
        </button>
      </div>

      <!-- Error message -->
      <p v-if="error" class="form-error mt-3 text-center">{{ error }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ middleware: undefined, layout: 'auth' })

const { user, switchOrg, logout } = useAuth()

const memberships = computed(() => user.value?.memberships ?? [])
const loading = ref(false)
const error = ref('')

async function selectOrg(orgId: string): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    await switchOrg(orgId)
    await navigateTo('/')
  } catch (e: any) {
    error.value = e?.message ?? 'Error al seleccionar la organización'
    console.error('Failed to select org:', e)
  } finally {
    loading.value = false
  }
}

// Wait for user to be loaded, then auto-redirect single-org users (U4)
watch(() => user.value, (val) => {
  if (val && memberships.value.length === 1) {
    selectOrg(memberships.value[0].organization.id)
  }
}, { immediate: true })
</script>

<style scoped>
.select-org-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4338ca 100%);
  padding: 1.5rem;
}

.select-org-card {
  background: var(--color-surface);
  padding: 2.5rem 2rem;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  width: 100%;
  max-width: 480px;
}

.select-org-brand {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 2rem;
}

.select-org-logo {
  width: 40px;
  height: 40px;
  background: var(--color-primary);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 1.2rem;
  font-weight: 700;
  flex-shrink: 0;
}

.select-org-brand h1 {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-heading);
  margin: 0;
}

.select-org-card h2 {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--color-heading);
  margin-bottom: 0.35rem;
}

/* Empty state */
.select-org-empty {
  text-align: center;
  margin-top: 1.5rem;
  padding: 1.5rem 0;
}

.empty-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
  opacity: 0.5;
}

.select-org-empty p {
  margin-bottom: 0.5rem;
  font-size: 0.95rem;
  color: var(--color-body);
}

/* Organization list */
.org-list {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
  margin-top: 1.5rem;
}

.org-list-item {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  padding: 0.85rem 1rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: var(--font-family);
  font-size: 0.95rem;
  color: var(--color-body);
  width: 100%;
  text-align: left;
}

.org-list-item:hover:not(:disabled) {
  border-color: var(--color-primary);
  background: var(--color-primary-light);
  box-shadow: 0 1px 4px rgba(79, 70, 229, 0.15);
}

.org-list-item:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.org-list-item-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  background: var(--color-primary-light);
  color: var(--color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.9rem;
  font-weight: 700;
  flex-shrink: 0;
}

.org-list-item-info {
  flex: 1;
  min-width: 0;
}

.org-list-item-name {
  font-weight: 600;
  color: var(--color-heading);
  font-size: 0.95rem;
}

.org-list-item-role {
  font-size: 0.8rem;
  color: var(--color-muted);
  margin-top: 0.1rem;
}

.org-list-item-arrow {
  font-size: 1.1rem;
  color: var(--color-muted);
  flex-shrink: 0;
  transition: transform 0.15s ease;
}

.org-list-item:hover:not(:disabled) .org-list-item-arrow {
  transform: translateX(2px);
  color: var(--color-primary);
}
</style>
