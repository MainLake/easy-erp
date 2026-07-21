<template>
  <div id="app">
    <header class="navbar">
      <div class="navbar-brand">Easy ERP</div>
      <nav class="navbar-nav">
        <NuxtLink to="/">Dashboard</NuxtLink>
      </nav>
      <div class="navbar-user" v-if="user">
        <span>{{ user.full_name }}</span>
        <button class="btn-logout" @click="logout()">Logout</button>
      </div>
    </header>
    <main>
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
const { user, logout } = useAuth()
</script>

<style>
body {
  margin: 0;
  font-family: system-ui, -apple-system, sans-serif;
  background: #f5f5f5;
  color: #222;
}
.navbar {
  display: flex;
  align-items: center;
  padding: 0.75rem 1.5rem;
  background: #1a1a2e;
  color: #fff;
}
.navbar-brand {
  font-size: 1.25rem;
  font-weight: 700;
  margin-right: 2rem;
}
.navbar-nav {
  display: flex;
  gap: 1rem;
  flex: 1;
}
.navbar-nav a {
  color: #ccc;
  text-decoration: none;
}
.navbar-nav a:hover {
  color: #fff;
}
.navbar-user {
  display: flex;
  align-items: center;
  gap: 1rem;
}
.btn-logout {
  padding: 0.3rem 0.75rem;
  border: 1px solid #555;
  border-radius: 4px;
  background: transparent;
  color: #ccc;
  cursor: pointer;
}
.btn-logout:hover {
  background: #333;
  color: #fff;
}
main {
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
}
</style>
