<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Lock, User } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const loginFormRef = ref<FormInstance>()
const loading = ref(false)

const loginForm = reactive({
  username: '',
  password: '',
})

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 4, message: '密码长度不少于 4 位', trigger: 'blur' },
  ],
}

async function handleLogin(formEl: FormInstance | undefined) {
  if (!formEl) return
  await formEl.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      await auth.login({
        username: loginForm.username,
        password: loginForm.password,
      })
      ElMessage.success('登录成功')
      const redirect = (route.query.redirect as string) || '/dashboard'
      router.push(redirect)
    } catch {
      // 错误提示已由请求拦截器统一处理
    } finally {
      loading.value = false
    }
  })
}
</script>

<template>
  <div class="login-view">
    <div class="login-card">
      <div class="login-header">
        <div class="logo">
          <el-icon :size="42"><Monitor /></el-icon>
        </div>
        <h1 class="title">Ops Agent 运维管理平台</h1>
        <p class="subtitle">统一服务器监控 · 日志 · 配置 · AI 运维</p>
      </div>
      <el-form
        ref="loginFormRef"
        :model="loginForm"
        :rules="rules"
        size="large"
        label-position="top"
        @keyup.enter="handleLogin(loginFormRef)"
      >
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="请输入用户名"
            :prefix-icon="User"
            clearable
            autocomplete="username"
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="请输入密码"
            :prefix-icon="Lock"
            show-password
            clearable
            autocomplete="current-password"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            class="login-btn"
            :loading="loading"
            @click="handleLogin(loginFormRef)"
          >
            登 录
          </el-button>
        </el-form-item>
      </el-form>
      <div class="login-footer">Ops Agent © 2026 · 运维管理平台</div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.login-view {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1e3c72 0%, #2a5298 50%, #1e3c72 100%);
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    width: 600px;
    height: 600px;
    border-radius: 50%;
    background: rgba(64, 158, 255, 0.1);
    top: -200px;
    right: -150px;
  }

  &::after {
    content: '';
    position: absolute;
    width: 500px;
    height: 500px;
    border-radius: 50%;
    background: rgba(64, 158, 255, 0.07);
    bottom: -180px;
    left: -120px;
  }
}

.login-card {
  width: 420px;
  max-width: calc(100vw - 32px);
  padding: 40px 36px 28px;
  background: rgba(255, 255, 255, 0.97);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
  position: relative;
  z-index: 1;
  backdrop-filter: blur(6px);
}

.login-header {
  text-align: center;
  margin-bottom: 28px;

  .logo {
    color: #2a5298;
    margin-bottom: 12px;
  }

  .title {
    font-size: 22px;
    font-weight: 700;
    color: #1e3c72;
    margin-bottom: 8px;
  }

  .subtitle {
    font-size: 13px;
    color: #909399;
  }
}

.login-btn {
  width: 100%;
  letter-spacing: 4px;
}

.login-footer {
  text-align: center;
  font-size: 12px;
  color: #c0c4cc;
  margin-top: 16px;
}
</style>
