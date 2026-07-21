<template>
  <div v-if="definitions.length > 0" class="dynamic-fields">
    <h3 class="dynamic-fields-title">Campos Personalizados</h3>
    <div
      v-for="field in definitions"
      :key="field.id"
      class="form-group"
    >
      <label :for="`custom-field-${field.name}`">
        {{ field.name }}
        <span v-if="field.required" class="required">*</span>
      </label>

      <!-- Select -->
      <select
        v-if="field.field_type === 'select'"
        :id="`custom-field-${field.name}`"
        :value="modelValue[field.name] ?? ''"
        :required="field.required"
        class="form-input"
        @change="emitUpdate(field.name, ($event.target as HTMLSelectElement).value)"
      >
        <option value="">-- Seleccionar --</option>
        <option
          v-for="opt in (field.options ?? [])"
          :key="opt"
          :value="opt"
        >
          {{ opt }}
        </option>
      </select>

      <!-- Number -->
      <input
        v-else-if="field.field_type === 'number'"
        :id="`custom-field-${field.name}`"
        type="number"
        step="0.01"
        :value="modelValue[field.name] ?? ''"
        :required="field.required"
        class="form-input"
        @input="emitUpdate(field.name, ($event.target as HTMLInputElement).value)"
      />

      <!-- Date -->
      <input
        v-else-if="field.field_type === 'date'"
        :id="`custom-field-${field.name}`"
        type="date"
        :value="modelValue[field.name] ?? ''"
        :required="field.required"
        class="form-input"
        @input="emitUpdate(field.name, ($event.target as HTMLInputElement).value)"
      />

      <!-- Text (default) -->
      <input
        v-else
        :id="`custom-field-${field.name}`"
        type="text"
        :value="modelValue[field.name] ?? ''"
        :required="field.required"
        class="form-input"
        @input="emitUpdate(field.name, ($event.target as HTMLInputElement).value)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { useCustomFields } from '../composables/useCustomFields'

const props = defineProps({
  modelName: {
    type: String,
    required: true,
  },
  customFields: {
    type: Object as () => Record<string, string>,
    default: () => ({}),
  },
})

const emit = defineEmits<{
  (e: 'update:customFields', value: Record<string, string>): void
}>()

const { definitions, fetchDefinitions } = useCustomFields()

// On mount or modelName change, fetch definitions
watch(
  () => props.modelName,
  (name) => {
    if (name) {
      fetchDefinitions(name)
    }
  },
  { immediate: true },
)

const modelValue = computed(() => props.customFields)

function emitUpdate(name: string, value: string) {
  const updated = { ...props.customFields, [name]: value }
  emit('update:customFields', updated)
}
</script>

<style scoped>
.dynamic-fields {
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--color-border-light);
}

.dynamic-fields-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--color-heading);
  margin: 0 0 0.75rem 0;
}
</style>
