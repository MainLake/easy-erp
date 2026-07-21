/**
 * Fetch and cache custom field definitions per model type.
 *
 * Fetches field definitions from `/api/v1/custom-fields/?model_name=X`,
 * caches them by model_name, and exposes a reactive list.
 */
import { ref, type Ref } from 'vue'

export interface FieldDefinition {
  id: string
  organization: string
  model_name: string
  name: string
  field_type: 'text' | 'number' | 'date' | 'select'
  required: boolean
  options: string[] | null
  order: number
  created_at: string
  updated_at: string
}

export const useCustomFields = () => {
  const { request } = useApi()

  const definitions: Ref<FieldDefinition[]> = ref([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchDefinitions(modelName: string): Promise<FieldDefinition[]> {
    loading.value = true
    error.value = null

    try {
      const res = await request(`/custom-fields/?model_name=${modelName}&page_size=200`)
      if (!res.ok) {
        const envelope = await res.json()
        throw new Error(
          envelope?.errors?.[0]?.message
          || envelope?.data?.detail
          || envelope?.detail
          || 'Error al cargar campos personalizados',
        )
      }
      const envelope = await res.json()
      const data: FieldDefinition[] = envelope.data ?? envelope.results ?? []
      definitions.value = data
      return data
    } catch (e: any) {
      error.value = e.message || 'Error desconocido'
      definitions.value = []
      return []
    } finally {
      loading.value = false
    }
  }

  return { definitions, loading, error, fetchDefinitions }
}
