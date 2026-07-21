<template>
  <div>
    <h1>Dashboard</h1>
    <p v-if="user">Welcome, {{ user.full_name }} — role: {{ user.role }}</p>
    <p v-else>Loading…</p>
  </div>
</template>

<script setup lang="ts">
definePageMeta({ middleware: 'auth' })

const { user } = useAuth()
</script>
