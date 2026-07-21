export default defineNuxtRouteMiddleware(() => {
  // Guard: redirect to login if no access token stored
  const accessToken = import.meta.client
    ? localStorage.getItem('access_token')
    : null

  if (!accessToken) {
    return navigateTo('/login')
  }
})
