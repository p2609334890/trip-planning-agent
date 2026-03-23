<template>
  <div id="app">
    <!-- 顶部导航栏 -->
    <header class="app-header">
      <div class="header-content">
        <div class="logo">
          <h1>🌍 智能旅行助手</h1>
        </div>
        <nav class="nav-menu">
          <router-link to="/" class="nav-item">
            <el-icon><House /></el-icon>
            首页
          </router-link>
          <router-link to="/my-trips" class="nav-item" v-if="authStore.isAuthenticated">
            <el-icon><Document /></el-icon>
            我的行程
          </router-link>
        </nav>
        <div class="user-section">
          <UserInfo />
        </div>
      </div>
    </header>
    
    <!-- 主要内容区 -->
    <main class="main-content">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import UserInfo from '@/components/UserInfo.vue'
import { House, Document } from '@element-plus/icons-vue'

const authStore = useAuthStore()

onMounted(() => {
  console.log('智能旅行助手启动成功！')
  console.log('用户认证状态:', authStore.isAuthenticated)
})
</script>

<style lang="scss">
:root {
  // 全局背景（主页同款）
  --app-bg:
    radial-gradient(
      1200px 800px at 15% 10%,
      rgba(255, 255, 255, 0.35) 0%,
      rgba(255, 255, 255, 0) 60%
    ),
    linear-gradient(180deg, #2e7d32 0%, #43a047 28%, #4fc3f7 70%, #0288d1 100%);

  // 品牌色（与主页背景匹配：绿 → 蓝）
  --brand-1: #2e7d32;
  --brand-2: #43a047;
  --brand-3: #4fc3f7;
  --brand-4: #0288d1;

  // 品牌渐变（按钮/徽标/标题）
  --brand-gradient: linear-gradient(135deg, var(--brand-2) 0%, var(--brand-4) 100%);
  --brand-gradient-soft: linear-gradient(135deg, rgba(67, 160, 71, 0.12) 0%, rgba(2, 136, 209, 0.12) 100%);

  --brand-shadow: 0 8px 24px rgba(2, 136, 209, 0.28);
  --brand-shadow-strong: 0 12px 32px rgba(2, 136, 209, 0.38);
}

#app {
  width: 100%;
  min-height: 100vh;
  background: var(--app-bg);
  display: flex;
  flex-direction: column;
  position: relative;
  overflow-x: hidden;
}

.app-header {
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(20px);
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08);
  padding: 0 20px;
  position: sticky;
  top: 0;
  z-index: 1000;
  transition: all 0.3s ease;

  .header-content {
    max-width: 1400px;
    margin: 0 auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 70px;
  }

  .logo {
    h1 {
      margin: 0;
      font-size: 24px;
      font-weight: 700;
      background: var(--brand-gradient);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      letter-spacing: 0.5px;
    }
  }

  .nav-menu {
    display: flex;
    gap: 8px;
    background: var(--brand-gradient-soft);
    padding: 4px;
    border-radius: 12px;
    transition: all 0.3s ease;

    .nav-item {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 10px 16px;
      border-radius: 8px;
      color: #606266;
      text-decoration: none;
      transition: all 0.3s ease;
      font-weight: 500;
      font-size: 15px;

      &:hover {
        background: rgba(2, 136, 209, 0.12);
        color: var(--brand-4);
        transform: translateY(-1px);
      }

      &.router-link-active {
        background: var(--brand-gradient);
        color: white;
        box-shadow: 0 4px 12px rgba(2, 136, 209, 0.3);
      }
    }
  }

  .user-section {
    display: flex;
    align-items: center;
  }
}

.main-content {
  flex: 1;
  padding: 24px 20px;
  position: relative;
  z-index: 1;
  pointer-events: auto;
}

// 过渡动画
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

// 响应式设计
@media (max-width: 768px) {
  .app-header {
    padding: 0 15px;

    .header-content {
      .logo h1 {
        font-size: 18px;
      }

      .nav-menu {
        gap: 15px;

        .nav-item {
          padding: 6px 10px;
          font-size: 14px;
        }
      }
    }
  }
}
</style>

<style lang="scss">
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body {
  width: 100%;
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial,
    'Noto Sans', sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol',
    'Noto Color Emoji';
}

#app {
  width: 100%;
  min-height: 100vh;
  background: var(--app-bg);
}

// 过渡动画
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

// 滚动条样式
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: #f1f1f1;
}

::-webkit-scrollbar-thumb {
  background: #888;
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: #555;
}
</style>
