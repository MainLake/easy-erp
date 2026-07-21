import { describe, it, expect, beforeEach, vi } from 'vitest'

// Clear the module-level cache between tests
import { clearCustomFieldsCache } from '../composables/useCustomFields'

beforeEach(() => {
  vi.restoreAllMocks()
  clearCustomFieldsCache()
})

describe('useCustomFields', () => {
  it('fetches field definitions for a model', async () => {
    const mockDefinitions = [
      {
        id: 'cf-1',
        organization: 'org-1',
        model_name: 'product',
        name: 'SKU',
        field_type: 'text',
        required: true,
        options: null,
        order: 0,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 'cf-2',
        organization: 'org-1',
        model_name: 'product',
        name: 'Weight',
        field_type: 'number',
        required: false,
        options: null,
        order: 1,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ]

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: mockDefinitions }),
    })

    // Import dynamically so the composable uses our mocked useApi
    const { useCustomFields } = await import('../composables/useCustomFields')
    const { definitions, fetchDefinitions, loading } = useCustomFields()

    await fetchDefinitions('product')

    expect(definitions.value).toHaveLength(2)
    expect(definitions.value[0].name).toBe('SKU')
    expect(definitions.value[1].field_type).toBe('number')
  })

  it('returns cached definitions on second call', async () => {
    const mockDefinitions = [
      {
        id: 'cf-1',
        organization: 'org-1',
        model_name: 'customer',
        name: 'RFC',
        field_type: 'text',
        required: true,
        options: null,
        order: 0,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ]

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: mockDefinitions }),
    })

    const { useCustomFields } = await import('../composables/useCustomFields')
    const { definitions, fetchDefinitions } = useCustomFields()

    await fetchDefinitions('customer')
    expect(globalThis.fetch).toHaveBeenCalledTimes(1)
    expect(definitions.value).toHaveLength(1)

    // Second call — should use cache, no fetch
    await fetchDefinitions('customer')
    expect(globalThis.fetch).toHaveBeenCalledTimes(1)
    expect(definitions.value).toHaveLength(1)
  })

  it('handles API error gracefully', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({
        errors: [{ message: 'Not authorized' }],
      }),
    })

    const { useCustomFields } = await import('../composables/useCustomFields')
    const { definitions, error, fetchDefinitions } = useCustomFields()

    await fetchDefinitions('supplier')

    expect(definitions.value).toHaveLength(0)
    expect(error.value).toBe('Not authorized')
  })

  it('handles missing response data', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    })

    const { useCustomFields } = await import('../composables/useCustomFields')
    const { definitions, fetchDefinitions } = useCustomFields()

    await fetchDefinitions('organization')

    expect(definitions.value).toHaveLength(0)
  })

  it('isolates cache per model name', async () => {
    const productDefs = [
      {
        id: 'p-1',
        organization: 'org-1',
        model_name: 'product',
        name: 'SKU',
        field_type: 'text' as const,
        required: true,
        options: null,
        order: 0,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ]
    const customerDefs = [
      {
        id: 'c-1',
        organization: 'org-1',
        model_name: 'customer',
        name: 'RFC',
        field_type: 'text' as const,
        required: true,
        options: null,
        order: 0,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ]

    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ data: productDefs }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ data: customerDefs }),
      })

    const { useCustomFields } = await import('../composables/useCustomFields')
    const { definitions, fetchDefinitions } = useCustomFields()

    await fetchDefinitions('product')
    expect(definitions.value).toHaveLength(1)
    expect(definitions.value[0].name).toBe('SKU')

    await fetchDefinitions('customer')
    expect(definitions.value).toHaveLength(1)
    expect(definitions.value[0].name).toBe('RFC')

    // Verify both fetches happened (no cache collision)
    expect(globalThis.fetch).toHaveBeenCalledTimes(2)
  })
})
