import { createApp } from 'vue'
import { createPinia } from 'pinia'
import type { Component } from 'vue'
import App from './App.vue'
import router from './router'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

// Element Plus 组件按需自动导入（见 vite.config.ts 中 ElementPlusResolver）。
// 以下为「函数式调用」组件的样式（ElMessage / ElMessageBox / ElNotification / ElLoading），
// 按需导入时这些组件的样式不会随模板自动引入，需手动引入一次。
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/notification/style/css'
import 'element-plus/es/components/loading/style/css'

// 全局样式
import '@/styles/index.scss'

const app = createApp(App)

// 全局注册 Element Plus 图标组件
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component as Component)
}

app.use(createPinia())
app.use(router)

app.mount('#app')
