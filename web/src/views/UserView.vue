<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Plus, Edit, Key, User } from '@element-plus/icons-vue'
import request from '@/api/request'

/* ── 类型定义 ── */
interface UserItem {
  id: number
  username: string
  display_name: string
  role: string
  is_active: boolean
  created_at: string
  last_login_at: string | null
}

/* ── 列表状态 ── */
const loading = ref(false)
const tableData = ref<UserItem[]>([])

/* ── 角色选项 ── */
const roleOptions = [
  { label: '管理员', value: 'admin' },
  { label: '操作员', value: 'operator' },
  { label: '观察者', value: 'viewer' },
]

function roleLabel(role: string): string {
  return roleOptions.find((r) => r.value === role)?.label ?? role
}

function roleTagType(role: string): 'danger' | 'warning' | 'info' {
  switch (role) {
    case 'admin':
      return 'danger'
    case 'operator':
      return 'warning'
    default:
      return 'info'
  }
}

/* ── 时间格式化 ── */
function fmtTime(t: string | null): string {
  if (!t) return '—'
  const d = new Date(t)
  return isNaN(d.getTime()) ? t : d.toLocaleString('zh-CN')
}

/* ── 加载列表 ── */
async function loadData() {
  loading.value = true
  try {
    const res = await request.get<{ total: number; users: UserItem[] }>('/users')
    tableData.value = res.data.users
  } catch {
    // 错误已由拦截器提示
  } finally {
    loading.value = false
  }
}

/* ── 创建/编辑对话框 ── */
const dialogVisible = ref(false)
const dialogTitle = ref('')
const isEdit = ref(false)
const submitLoading = ref(false)

const form = reactive({
  id: 0,
  username: '',
  password: '',
  display_name: '',
  role: 'viewer',
  is_active: true,
})

function resetForm() {
  form.id = 0
  form.username = ''
  form.password = ''
  form.display_name = ''
  form.role = 'viewer'
  form.is_active = true
}

function openCreate() {
  isEdit.value = false
  dialogTitle.value = '新增用户'
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: any) {
  isEdit.value = true
  dialogTitle.value = '编辑用户'
  form.id = row.id
  form.username = row.username
  form.password = ''
  form.display_name = row.display_name
  form.role = row.role
  form.is_active = row.is_active
  dialogVisible.value = true
}

async function handleSubmit() {
  submitLoading.value = true
  try {
    if (isEdit.value) {
      await request.put(`/users/${form.id}`, {
        display_name: form.display_name,
        role: form.role,
        is_active: form.is_active,
      })
      ElMessage.success('用户信息已更新')
    } else {
      await request.post('/users', {
        username: form.username,
        password: form.password,
        display_name: form.display_name,
        role: form.role,
      })
      ElMessage.success('用户创建成功')
    }
    dialogVisible.value = false
    loadData()
  } catch {
    // 错误已由拦截器提示
  } finally {
    submitLoading.value = false
  }
}

/* ── 启用/停用 ── */
async function handleToggle(row: any) {
  const action = row.is_active ? '停用' : '启用'
  try {
    await ElMessageBox.confirm(
      `确定要${action}用户「${row.username}」吗？`,
      '操作确认',
      { type: 'warning', confirmButtonText: `确定${action}`, cancelButtonText: '取消' },
    )
    await request.patch(`/users/${row.id}/toggle`)
    ElMessage.success(`已${action}`)
    loadData()
  } catch {
    // 用户取消或请求失败
  }
}

/* ── 重置密码 ── */
const pwdDialogVisible = ref(false)
const pwdLoading = ref(false)
const pwdForm = reactive({
  id: 0,
  username: '',
  new_password: '',
})

function openResetPwd(row: any) {
  pwdForm.id = row.id
  pwdForm.username = row.username
  pwdForm.new_password = ''
  pwdDialogVisible.value = true
}

async function handleResetPwd() {
  pwdLoading.value = true
  try {
    await request.put(`/users/${pwdForm.id}/password`, {
      new_password: pwdForm.new_password,
    })
    ElMessage.success(`用户「${pwdForm.username}」的密码已重置`)
    pwdDialogVisible.value = false
  } catch {
    // 错误已由拦截器提示
  } finally {
    pwdLoading.value = false
  }
}

/* ── 修改自己的密码 ── */
const myPwdDialogVisible = ref(false)
const myPwdLoading = ref(false)
const myPwdForm = reactive({
  old_password: '',
  new_password: '',
})

function openMyPwd() {
  myPwdForm.old_password = ''
  myPwdForm.new_password = ''
  myPwdDialogVisible.value = true
}

async function handleMyPwd() {
  myPwdLoading.value = true
  try {
    await request.put('/users/me/password', {
      old_password: myPwdForm.old_password,
      new_password: myPwdForm.new_password,
    })
    ElMessage.success('密码修改成功')
    myPwdDialogVisible.value = false
  } catch {
    // 错误已由拦截器提示
  } finally {
    myPwdLoading.value = false
  }
}

/* ── 用户角色分配 ── */
const roleDialogVisible = ref(false)
const roleLoading = ref(false)
const roleForm = reactive({
  userId: 0,
  username: '',
  checkedRoleIds: [] as number[],
})
const allRoles = ref<{ id: number; name: string; description: string; is_system: boolean }[]>([])

async function loadAllRoles() {
  try {
    const res = await request.get<{ total: number; roles: any[] }>('/roles')
    allRoles.value = res.data.roles.map((r) => ({
      id: r.id,
      name: r.name,
      description: r.description,
      is_system: r.is_system,
    }))
  } catch {
    // 忽略
  }
}

async function openAssignRole(row: any) {
  roleForm.userId = row.id
  roleForm.username = row.username
  roleForm.checkedRoleIds = []
  roleDialogVisible.value = true
  // 加载全量角色
  await loadAllRoles()
  // 加载该用户已分配的角色
  try {
    const res = await request.get<{ user_id: number; roles: { id: number; name: string }[] }>(
      `/users/${row.id}/roles`,
    )
    roleForm.checkedRoleIds = res.data.roles.map((r) => r.id)
  } catch {
    // 忽略
  }
}

async function handleRoleSubmit() {
  roleLoading.value = true
  try {
    await request.put(`/users/${roleForm.userId}/roles`, {
      role_ids: roleForm.checkedRoleIds,
    })
    ElMessage.success(`用户「${roleForm.username}」的角色已更新`)
    roleDialogVisible.value = false
    loadData()
  } catch {
    // 错误已由拦截器提示
  } finally {
    roleLoading.value = false
  }
}

/* ── 初始化 ── */
onMounted(() => {
  loadData()
})

/* ── 暴露给模板（供父组件调用修改密码） ── */
defineExpose({ openMyPwd })
</script>

<template>
  <div class="user-view">
    <!-- 工具栏 -->
    <div class="toolbar">
      <el-button type="primary" :icon="Plus" @click="openCreate">新增用户</el-button>
      <el-button :icon="Refresh" @click="loadData">刷新</el-button>
    </div>

    <!-- 用户表格 -->
    <el-table v-loading="loading" :data="tableData" border stripe style="width: 100%">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="username" label="用户名" min-width="120" />
      <el-table-column prop="display_name" label="显示名称" min-width="120" />
      <el-table-column label="角色" width="100">
        <template #default="{ row }">
          <el-tag :type="roleTagType(row.role)" size="small">
            {{ roleLabel(row.role) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
            {{ row.is_active ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">
          {{ fmtTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="最后登录" width="170">
        <template #default="{ row }">
          {{ fmtTime(row.last_login_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="290" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" :icon="Edit" @click="openEdit(row)">编辑</el-button>
          <el-button link type="primary" :icon="User" @click="openAssignRole(row)">角色</el-button>
          <el-button link :type="row.is_active ? 'warning' : 'success'" @click="handleToggle(row)">
            {{ row.is_active ? '停用' : '启用' }}
          </el-button>
          <el-button link type="primary" :icon="Key" @click="openResetPwd(row)">重置密码</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="480px" :close-on-click-modal="false">
      <el-form :model="form" label-width="80px">
        <el-form-item v-if="!isEdit" label="用户名" required>
          <el-input v-model="form.username" placeholder="2-64 个字符" />
        </el-form-item>
        <el-form-item v-if="!isEdit" label="密码" required>
          <el-input v-model="form.password" type="password" show-password placeholder="6-128 个字符" />
        </el-form-item>
        <el-form-item label="显示名称">
          <el-input v-model="form.display_name" placeholder="留空则使用用户名" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role" style="width: 100%">
            <el-option v-for="r in roleOptions" :key="r.value" :label="r.label" :value="r.value" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="isEdit" label="状态">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码对话框 -->
    <el-dialog v-model="pwdDialogVisible" title="重置密码" width="420px" :close-on-click-modal="false">
      <p class="pwd-hint">
        为用户「<strong>{{ pwdForm.username }}</strong>」设置新密码
      </p>
      <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="6-128 个字符" />
      <template #footer>
        <el-button @click="pwdDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="pwdLoading" @click="handleResetPwd">确认重置</el-button>
      </template>
    </el-dialog>

    <!-- 修改自己的密码对话框 -->
    <el-dialog v-model="myPwdDialogVisible" title="修改密码" width="420px" :close-on-click-modal="false">
      <el-form :model="myPwdForm" label-width="80px">
        <el-form-item label="旧密码" required>
          <el-input v-model="myPwdForm.old_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码" required>
          <el-input v-model="myPwdForm.new_password" type="password" show-password placeholder="6-128 个字符" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="myPwdDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="myPwdLoading" @click="handleMyPwd">确认修改</el-button>
      </template>
    </el-dialog>

    <!-- 角色分配对话框 -->
    <el-dialog v-model="roleDialogVisible" :title="`角色分配 - ${roleForm.username}`" width="480px" :close-on-click-modal="false">
      <p class="pwd-hint">为用户「<strong>{{ roleForm.username }}</strong>」分配角色（可多选）</p>
      <el-checkbox-group v-model="roleForm.checkedRoleIds" class="role-checkbox-group">
        <div v-for="r in allRoles" :key="r.id" class="role-checkbox-item">
          <el-checkbox :label="r.id" :value="r.id">
            <span class="role-name">{{ r.name }}</span>
            <el-tag v-if="r.is_system" size="small" type="warning" effect="plain" style="margin-left: 6px">内置</el-tag>
            <span class="role-desc">{{ r.description }}</span>
          </el-checkbox>
        </div>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="roleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="roleLoading" @click="handleRoleSubmit">保存角色</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.user-view {
  .toolbar {
    margin-bottom: 16px;
    display: flex;
    gap: 8px;
  }

  .pwd-hint {
    margin-bottom: 12px;
    color: #606266;
    font-size: 14px;
  }

  .role-checkbox-group {
    .role-checkbox-item {
      margin-bottom: 12px;
    }

    .role-name {
      font-weight: 600;
    }

    .role-desc {
      color: #909399;
      font-size: 13px;
      margin-left: 8px;
    }
  }
}
</style>
