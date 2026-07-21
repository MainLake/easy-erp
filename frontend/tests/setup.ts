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

// Mock useAuth — simple stub for useApi dependency
// eslint-disable-next-line @typescript-eslint/no-explicit-any
;(globalThis as any).useAuth = () => ({
  user: { value: null },
  getAccessToken: () => null,
  getRefreshToken: () => null,
  tryRefresh: async () => false,
  login: async () => {},
  logout: () => {},
  fetchUser: async () => {},
  initAuth: async () => false,
  switchOrg: async () => {},
  register: async () => {},
})

// Mock useApi — thin wrapper that delegates to globalThis.fetch
// eslint-disable-next-line @typescript-eslint/no-explicit-any
;(globalThis as any).useApi = () => {
  const config = (globalThis as any).useRuntimeConfig()
  return {
    request: async (endpoint: string, options?: RequestInit) => {
      return fetch(`${config.public.apiBase}${endpoint}`, options || {})
    },
  }
}
