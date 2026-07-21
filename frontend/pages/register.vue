<template>
  <div class="register-page">
    <form class="register-form" @submit.prevent="handleRegister">
      <h2>Easy ERP — Registro</h2>

      <label>
        Nombre completo
        <input v-model="fullName" type="text" required autocomplete="name" />
      </label>

      <label>
        Email
        <input v-model="email" type="email" required autocomplete="email" />
      </label>

      <label>
        Contraseña
        <input v-model="password" type="password" required autocomplete="new-password" />
        <span class="hint">Mínimo 8 caracteres, al menos una letra y un número</span>
      </label>

      <label>
        Nombre de la empresa
        <input v-model="orgName" type="text" required />
      </label>

      <label>
        RFC (opcional)
        <input v-model="orgTaxId" type="text" autocomplete="off" />
      </label>

      <p v-if="error" class="error">{{ error }}</p>

      <button type="submit" :disabled="loading">
        {{ loading ? 'Creando cuenta…' : 'Registrarse' }}
      </button>

      <p class="login-link">
        ¿Ya tenés cuenta? <NuxtLink to="/login">Iniciá sesión</NuxtLink>
      </p>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

definePageMeta({ layout: 'auth' })

const fullName = ref('')
const email = ref('')
const password = ref('')
const orgName = ref('')
const orgTaxId = ref('')
const error = ref('')
const loading = ref(false)

const { register, user } = useAuth()

onMounted(async () => {
  // If already authenticated, redirect away
  if (user.value?.active_membership) {
    await navigateTo('/')
  }
})

async function handleRegister() {
  error.value = ''
  loading.value = true
  try {
    await register({
      email: email.value,
      password: password.value,
      full_name: fullName.value,
      org_name: orgName.value,
      org_tax_id: orgTaxId.value || undefined,
    })
    // register() handles token persistence, user fetch, and navigation to /
  } catch (err: any) {
    error.value = err.message || 'Error al crear la cuenta. Intentalo de nuevo.'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.register-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: #f5f5f5;
}
.register-form {
  background: #fff;
  padding: 2rem;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  width: 100%;
  max-width: 420px;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.register-form h2 {
  margin: 0 0 0.5rem;
  text-align: center;
}
.register-form label {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.9rem;
  color: #555;
}
.register-form label .hint {
  font-size: 0.75rem;
  color: #999;
}
.register-form input {
  padding: 0.6rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 1rem;
}
.register-form button {
  padding: 0.7rem;
  background: #1a1a2e;
  color: #fff;
  border: none;
  border-radius: 4px;
  font-size: 1rem;
  cursor: pointer;
}
.register-form button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.register-form button:hover:not(:disabled) {
  background: #2d2d44;
}
.error {
  color: #d32f2f;
  font-size: 0.85rem;
  margin: 0;
}
.login-link {
  text-align: center;
  font-size: 0.9rem;
  color: #777;
}
.login-link a {
  color: #1a1a2e;
  text-decoration: underline;
}
</style>
