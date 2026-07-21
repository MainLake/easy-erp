<template>
  <div class="app-shell">
    <!-- Top Navbar — full width above sidebar + main -->
    <header class="topbar">
      <div class="topbar-brand">Easy ERP</div>
      <div class="topbar-center">
        <OrgSelector />
      </div>
      <div class="topbar-user" v-if="user">
        <span class="topbar-user-name">{{ user.full_name }}</span>
        <button class="btn-logout" @click="logout()">Cerrar sesión</button>
      </div>
    </header>

    <div class="app-body">
      <Sidebar />
      <main class="main-content">
        <slot />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
const { user, logout } = useAuth()
</script>

<style>
/* === Reset / Base — scoped to app-shell === */
body {
  margin: 0;
  font-family: var(--font-family);
  background: var(--color-bg);
  color: var(--color-body);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* === App Shell Layout === */
.app-shell {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

/* === Top Navbar === */
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--topbar-height);
  padding: 0 1.5rem;
  background: #1a1a2e;
  color: #fff;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.12);
}

.topbar-brand {
  font-size: 1.2rem;
  font-weight: 700;
  letter-spacing: -0.3px;
}

.topbar-center {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex: 1;
  justify-content: center;
}

.topbar-user {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.topbar-user-name {
  font-size: 0.85rem;
  color: #ccc;
  white-space: nowrap;
}

.btn-logout {
  padding: 0.3rem 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.25);
  border-radius: var(--radius-sm);
  background: transparent;
  color: #ccc;
  cursor: pointer;
  font-family: var(--font-family);
  font-size: 0.8rem;
  transition: background 0.15s ease, color 0.15s ease;
}

.btn-logout:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

/* === Body: Sidebar + Main === */
.app-body {
  display: flex;
  flex: 1;
}

.main-content {
  flex: 1;
  overflow-y: auto;
  padding: 0;
  min-height: calc(100vh - var(--topbar-height));
}

/* === Responsive: mobile === */
@media (max-width: 768px) {
  .topbar {
    padding: 0 0.75rem;
  }

  .topbar-brand {
    font-size: 1rem;
  }

  .topbar-center {
    display: none;
  }

  .topbar-user-name {
    display: none;
  }

  .btn-logout {
    font-size: 0.75rem;
    padding: 0.25rem 0.5rem;
  }
}
</style>
