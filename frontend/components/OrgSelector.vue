<template>
  <div class="org-selector" v-if="memberships.length > 0">
    <label for="org-select" class="org-selector-label">Organización</label>
    <select
      id="org-select"
      class="org-select"
      :value="activeOrg?.id ?? ''"
      @change="handleChange"
    >
      <option value="" disabled>Cambiar organización</option>
      <optgroup label="Organizaciones">
        <option
          v-for="m in memberships"
          :key="m.id"
          :value="m.organization.id"
          :selected="m.organization.id === activeOrg?.id"
        >
          {{ m.organization.name }}
        </option>
      </optgroup>
    </select>
    <span class="org-current" v-if="activeOrg">{{ activeOrg.name }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const { user, switchOrg } = useAuth()

const memberships = computed(() => user.value?.memberships ?? [])
const activeOrg = computed(() => user.value?.active_membership?.organization)

async function handleChange(event: Event) {
  const target = event.target as HTMLSelectElement
  const orgId = target.value
  if (!orgId) return
  try {
    await switchOrg(orgId)
    // Reload current page to refresh org-scoped data
    window.location.reload()
  } catch (e: any) {
    console.error('Failed to switch org:', e)
  }
}
</script>

<style scoped>
.org-selector {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.org-selector-label {
  font-size: 0.75rem;
  color: var(--color-muted);
  text-transform: uppercase;
  letter-spacing: 0.4px;
  font-weight: 600;
}

.org-select {
  appearance: none;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: var(--radius-sm);
  color: #fff;
  padding: 0.35rem 1.75rem 0.35rem 0.6rem;
  font-size: 0.8rem;
  font-family: var(--font-family);
  cursor: pointer;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%23ffffff' d='M5 7L0 2h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 0.5rem center;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.org-select:hover {
  background-color: rgba(255, 255, 255, 0.15);
  border-color: rgba(255, 255, 255, 0.35);
}

.org-select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.3);
}

.org-select option {
  background: var(--color-surface);
  color: var(--color-heading);
}

.org-select optgroup {
  font-weight: 600;
  font-style: normal;
  color: var(--color-muted);
  font-size: 0.75rem;
}

.org-current {
  display: none; /* hidden on desktop — the select shows it */
}
</style>
