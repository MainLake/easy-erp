<template>
  <div class="login-page">
    <form class="login-form" @submit.prevent="handleLogin">
      <h2>Easy ERP — Login</h2>
      <label>
        Email
        <input v-model="email" type="email" required autocomplete="email" />
      </label>
      <label>
        Contraseña
        <input v-model="password" type="password" required autocomplete="current-password" />
      </label>
      <p v-if="error" class="error">{{ error }}</p>
      <button type="submit" :disabled="loading">
        {{ loading ? 'Ingresando…' : 'Ingresar' }}
      </button>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

const { login, user } = useAuth()

// If already authenticated, redirect away — middleware handles the right destination
if (user.value?.active_membership) {
  await navigateTo('/')
}

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await login(email.value, password.value)
    // login() now handles all post-login routing internally:
    //   0 orgs → throws error
    //   1 org  → redirects to /
    //   2+     → redirects to /select-org
  } catch (err: any) {
    error.value = err.message || 'Email o contraseña inválidos.'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: #f5f5f5;
}
.login-form {
  background: #fff;
  padding: 2rem;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  width: 100%;
  max-width: 400px;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.login-form h2 {
  margin: 0 0 0.5rem;
  text-align: center;
}
.login-form label {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.9rem;
  color: #555;
}
.login-form input {
  padding: 0.6rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 1rem;
}
.login-form button {
  padding: 0.7rem;
  background: #1a1a2e;
  color: #fff;
  border: none;
  border-radius: 4px;
  font-size: 1rem;
  cursor: pointer;
}
.login-form button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.login-form button:hover:not(:disabled) {
  background: #2d2d44;
}
.error {
  color: #d32f2f;
  font-size: 0.85rem;
  margin: 0;
}
</style>
