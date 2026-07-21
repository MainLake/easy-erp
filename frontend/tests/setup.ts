// Mock localStorage for jsdom test environment
const store = new Map<string, string>()

globalThis.localStorage = {
  getItem: (key: string) => store.get(key) ?? null,
  setItem: (key: string, value: string) => { store.set(key, value) },
  removeItem: (key: string) => { store.delete(key) },
  clear: () => { store.clear() },
  get length() { return store.size },
  key: (index: number) => [...store.keys()][index] ?? null,
} as Storage

// Mock Nuxt auto-imported composables (resolved by unplugin at build time)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
;(globalThis as any).useRuntimeConfig = () => ({
  public: { apiBase: 'http://localhost:8000/api/v1' },
})
// eslint-disable-next-line @typescript-eslint/no-explicit-any
;(globalThis as any).navigateTo = () => Promise.resolve()
