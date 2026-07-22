/**
 * Client-side auth initialization plugin.
 *
 * Runs once when the app starts in the browser:
 * 1. Reads stored tokens from localStorage
 * 2. Decodes JWT to check expiry
 * 3. If valid, restores user + memberships by calling /users/me/
 * 4. If expired, attempts silent refresh
 * 5. Sets user.value so layouts/components can react
 */
export default defineNuxtPlugin(async () => {
  const { initAuth, user } = useAuth()

  // Only run on client side
  if (!import.meta.client) return

  const storedToken = localStorage.getItem('access_token')

  if (storedToken) {
    await initAuth()
  }
  // If no token, user stays null — middleware/auth.ts handles redirects
})
