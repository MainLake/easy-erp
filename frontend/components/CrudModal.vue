<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="$emit('close')">
      <div class="modal-container">
        <div class="modal-header">
          <h3>{{ title }}</h3>
          <button class="modal-close" @click="$emit('close')">×</button>
        </div>
        <form class="modal-body" @submit.prevent="handleSubmit">
          <div v-for="field in fields" :key="field.name" class="form-group">
            <label :for="`field-${field.name}`">
              {{ field.label }}
              <span v-if="field.required" class="required">*</span>
            </label>
            <select
              v-if="field.type === 'select' && field.options"
              :id="`field-${field.name}`"
              v-model="formData[field.name]"
              :required="field.required"
              class="form-input"
            >
              <option value="">-- Seleccionar --</option>
              <option
                v-for="opt in field.options"
                :key="opt.value"
                :value="opt.value"
              >
                {{ opt.label }}
              </option>
            </select>
            <textarea
              v-else-if="field.type === 'textarea'"
              :id="`field-${field.name}`"
              v-model="formData[field.name]"
              :required="field.required"
              class="form-input"
              rows="3"
            />
            <input
              v-else
              :id="`field-${field.name}`"
              v-model="formData[field.name]"
              :type="field.type || 'text'"
              :step="field.type === 'number' ? '0.01' : undefined"
              :required="field.required"
              class="form-input"
            />
          </div>
          <slot name="below-fields" />
          <p v-if="error" class="form-error">{{ error }}</p>
          <div class="modal-footer">
            <button type="button" class="btn-cancel" @click="$emit('close')">Cancelar</button>
            <button type="submit" class="btn-save" :disabled="saving">
              {{ saving ? 'Guardando…' : 'Guardar' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, reactive } from 'vue'

export interface FieldDef {
  name: string
  label: string
  type?: 'text' | 'email' | 'number' | 'select' | 'textarea'
  required?: boolean
  options?: { value: string; label: string }[]
}

const props = defineProps<{
  title: string
  visible: boolean
  fields: FieldDef[]
  initialData?: Record<string, any>
}>()

const emit = defineEmits<{
  (e: 'save', data: Record<string, any>): void
  (e: 'close'): void
}>()

const formData = reactive<Record<string, any>>({})
const saving = ref(false)
const error = ref('')

watch(() => props.visible, (val) => {
  if (val) {
    // Initialize form data
    for (const f of props.fields) {
      formData[f.name] = props.initialData?.[f.name] ?? ''
    }
    saving.value = false
    error.value = ''
  }
})

async function handleSubmit() {
  error.value = ''
  saving.value = true
  try {
    // Build clean payload (convert empty strings to null for optional fields)
    const payload: Record<string, any> = {}
    for (const f of props.fields) {
      const val = formData[f.name]
      if (f.type === 'number' && val !== '') {
        payload[f.name] = Number(val)
      } else if (val === '' && !f.required) {
        payload[f.name] = null
      } else {
        payload[f.name] = val
      }
    }
    emit('save', payload)
  } catch (e: any) {
    error.value = e.message || 'Error al guardar'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.5);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.15s ease;
}

.modal-container {
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  width: 90%;
  max-width: 540px;
  max-height: 85vh;
  overflow-y: auto;
  box-shadow: var(--shadow-lg);
  animation: slideUp 0.2s ease;
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

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
