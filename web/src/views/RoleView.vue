<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Plus, Edit, Delete, Key, Connection } from '@element-plus/icons-vue'
import request from '@/api/request'

/* ── 类型定义 ── */
interface RoleItem {
  id: number
  name: string
  description: string
  is_system: boolean
  permissions: string[]
  resources: { resource_type: string; resource_id: string }[]
  user_count: number
  created_at: string
}

interface PermissionGroup {
  module: string
  permissions: string[]
}

/* ── 列表状态 ── */
const loading = ref(false)
const tableData = ref<RoleItem[]>([])

/* ── 全部权限码及分组 ── */
const allPermissions = ref<string[]>([])
const permissionGroups = ref<PermissionGroup[]>([])

/* ── 资源类型选项 ── */
const resourceTypes = [
  { label: '服务器', value: 'server' },
  { label: '应用服务', value: 'service' },
  { label: '配置文件', value: 'config' },
]

function resourceTypeLabel(type: string): string {
  return resourceTypes.find((r) => r.value === type)?.label ?? type
}

function fmtTime(t: string): string {
  const d = new Date(t)
  return isNaN(d.getTime()) ? t : d.toLocaleString('zh-CN')
}

/* ── 加载角色列表 ── */
async function loadData() {
  loading.value = true
  try {
    const res = await request.get<{ total: number; roles: RoleItem[] }>('/roles')
    tableData.value = res.data.roles
  } catch {
    // 错误已由拦截器提示
  } finally {
    loading.value = false
  }
}

/* ── 加载权限码 ── */
async function loadPermissions() {
  try {
    const res = await request.get<{ permissions: string[]; groups: PermissionGroup[] }>(
      '/roles/permissions/all',
    )
    allPermissions.value = res.data.permissions
    permissionGroups.value = res.data.groups
  } catch {
    // 忽略
  }
}

/* ── 创建/编辑角色 ── */
const dialogVisible = ref(false)
const dialogTitle = ref('')
const isEdit = ref(false)
const submitLoading = ref(false)

const form = reactive({
  id: 0,
  name: '',
  description: '',
})

function resetForm() {
  form.id = 0
  form.name = ''
  form.description = ''
}

function openCreate() {
  isEdit.value = false
  dialogTitle.value = '新增角色'
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: any) {
  isEdit.value = true
  dialogTitle.value = '编辑角色'
  form.id = row.id
  form.name = row.name
  form.description = row.description
  dialogVisible.value = true
}

async function handleSubmit() {
  submitLoading.value = true
  try {
    if (isEdit.value) {
      await request.put(`/roles/${form.id}`, {
        name: form.name,
        description: form.description,
      })
      ElMessage.success('角色信息已更新')
    } else {
      await request.post('/roles', {
        name: form.name,
        description: form.description,
      })
      ElMessage.success('角色创建成功')
    }
    dialogVisible.value = false
    loadData()
  } catch {
    // 错误已由拦截器提示
  } finally {
    submitLoading.value = false
  }
}

/* ── 删除角色 ── */
async function handleDelete(row: any) {
  try {
    await ElMessageBox.confirm(
      `确定要删除角色「${row.name}」吗？此操作不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消' },
    )
    await request.delete(`/roles/${row.id}`)
    ElMessage.success('角色已删除')
    loadData()
  } catch {
    // 用户取消或请求失败
  }
}

/* ── 权限分配对话框 ── */
const permDialogVisible = ref(false)
const permLoading = ref(false)
const permForm = reactive({
  roleId: 0,
  roleName: '',
  checked: [] as string[],
})
const permIndeterminate = ref(false)
const permCheckAll = ref(false)

function openPermissions(row: any) {
  permForm.roleId = row.id
  permForm.roleName = row.name
  permForm.checked = [...row.permissions]
  permDialogVisible.value = true
  updatePermCheckAll()
}

function handlePermCheckAll(val: any) {
  permForm.checked = val ? [...allPermissions.value] : []
  permIndeterminate.value = false
}

function updatePermCheckAll() {
  const total = allPermissions.value.length
  const checked = permForm.checked.length
  permCheckAll.value = checked === total
  permIndeterminate.value = checked > 0 && checked < total
}

async function handlePermSubmit() {
  permLoading.value = true
  try {
    await request.put(`/roles/${permForm.roleId}/permissions`, {
      permissions: permForm.checked,
    })
    ElMessage.success('权限已更新')
    permDialogVisible.value = false
    loadData()
  } catch {
    // 错误已由拦截器提示
  } finally {
    permLoading.value = false
  }
}

/* ── 资源分配对话框 ── */
const resDialogVisible = ref(false)
const resLoading = ref(false)
const resForm = reactive({
  roleId: 0,
  roleName: '',
  resourceType: 'server',
  resourceIds: [] as string[],
  inputId: '',
})
const currentResources = ref<{ resource_type: string; resource_id: string }[]>([])

async function openResources(row: any) {
  resForm.roleId = row.id
  resForm.roleName = row.name
  resForm.resourceType = 'server'
  resForm.resourceIds = []
  resForm.inputId = ''
  currentResources.value = [...row.resources]
  resDialogVisible.value = true
  // 切换到第一个资源类型并加载已有
  loadResIdsByType('server')
}

function loadResIdsByType(type: string) {
  resForm.resourceType = type
  resForm.resourceIds = currentResources.value
    .filter((r) => r.resource_type === type)
    .map((r) => r.resource_id)
}

function addResourceId() {
  const id = resForm.inputId.trim()
  if (!id) return
  if (!resForm.resourceIds.includes(id)) {
    resForm.resourceIds.push(id)
  }
  resForm.inputId = ''
}

function removeResourceId(id: string) {
  resForm.resourceIds = resForm.resourceIds.filter((r) => r !== id)
}

async function handleResSubmit() {
  resLoading.value = true
  try {
    await request.put(`/roles/${resForm.roleId}/resources`, {
      resource_type: resForm.resourceType,
      resource_ids: resForm.resourceIds,
    })
    ElMessage.success(`${resourceTypeLabel(resForm.resourceType)} 资源已更新`)
    // 更新本地缓存
    currentResources.value = currentResources.value.filter(
      (r) => r.resource_type !== resForm.resourceType,
    )
    currentResources.value.push(
      ...resForm.resourceIds.map((id) => ({ resource_type: resForm.resourceType, resource_id: id })),
    )
    loadData()
  } catch {
    // 错误已由拦截器提示
  } finally {
    resLoading.value = false
  }
}

/* ── 初始化 ── */
onMounted(() => {
  loadData()
  loadPermissions()
})
</script>

<template>
  <div class="role-view">
    <!-- 工具栏 -->
    <div class="toolbar">
      <el-button type="primary" :icon="Plus" @click="openCreate">新增角色</el-button>
      <el-button :icon="Refresh" @click="loadData">刷新</el-button>
    </div>

    <!-- 角色表格 -->
    <el-table v-loading="loading" :data="tableData" border stripe style="width: 100%">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="角色名称" min-width="120" />
      <el-table-column prop="description" label="描述" min-width="180" />
      <el-table-column label="类型" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_system ? 'warning' : 'info'" size="small">
            {{ row.is_system ? '内置' : '自定义' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="权限数" width="80" align="center">
        <template #default="{ row }">
          {{ row.permissions.length }}
        </template>
      </el-table-column>
      <el-table-column label="资源数" width="80" align="center">
        <template #default="{ row }">
          {{ row.resources.length }}
        </template>
      </el-table-column>
      <el-table-column label="用户数" width="80" align="center">
        <template #default="{ row }">
          {{ row.user_count }}
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">
          {{ fmtTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" :icon="Edit" @click="openEdit(row)">编辑</el-button>
          <el-button link type="primary" :icon="Key" @click="openPermissions(row)">权限</el-button>
          <el-button link type="primary" :icon="Connection" @click="openResources(row)">资源</el-button>
          <el-button
            v-if="!row.is_system"
            link
            type="danger"
            :icon="Delete"
            @click="handleDelete(row)"
          >删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建/编辑角色对话框 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="480px" :close-on-click-modal="false">
      <el-form :model="form" label-width="80px">
        <el-form-item label="角色名称" required>
          <el-input v-model="form.name" placeholder="2-64 个字符" :disabled="isEdit && form.name === 'admin' || form.name === 'operator' || form.name === 'viewer'" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="角色描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 权限分配对话框 -->
    <el-dialog v-model="permDialogVisible" :title="`权限分配 - ${permForm.roleName}`" width="600px" :close-on-click-modal="false">
      <div class="perm-header">
        <el-checkbox
          v-model="permCheckAll"
          :indeterminate="permIndeterminate"
          @change="handlePermCheckAll"
        >
          全选
        </el-checkbox>
      </div>
      <div class="perm-groups">
        <div v-for="g in permissionGroups" :key="g.module" class="perm-group">
          <div class="perm-group-title">{{ g.module }}</div>
          <el-checkbox-group v-model="permForm.checked" @change="updatePermCheckAll">
            <el-checkbox v-for="p in g.permissions" :key="p" :label="p">
              {{ p }}
            </el-checkbox>
          </el-checkbox-group>
        </div>
      </div>
      <template #footer>
        <el-button @click="permDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="permLoading" @click="handlePermSubmit">保存权限</el-button>
      </template>
    </el-dialog>

    <!-- 资源分配对话框 -->
    <el-dialog v-model="resDialogVisible" :title="`资源分配 - ${resForm.roleName}`" width="560px" :close-on-click-modal="false">
      <el-form label-width="80px">
        <el-form-item label="资源类型">
          <el-select v-model="resForm.resourceType" @change="loadResIdsByType(resForm.resourceType)" style="width: 200px">
            <el-option v-for="t in resourceTypes" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="添加">
          <div class="res-input-row">
            <el-input
              v-model="resForm.inputId"
              placeholder="输入主机名/服务ID/配置ID"
              @keyup.enter="addResourceId"
              style="width: 320px"
            />
            <el-button type="primary" @click="addResourceId">添加</el-button>
          </div>
        </el-form-item>
        <el-form-item label="已分配">
          <div class="res-tags">
            <el-tag
              v-for="id in resForm.resourceIds"
              :key="id"
              closable
              @close="removeResourceId(id)"
              style="margin: 4px"
            >
              {{ id }}
            </el-tag>
            <span v-if="resForm.resourceIds.length === 0" class="res-empty">暂无资源</span>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="resLoading" @click="handleResSubmit">保存资源</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.role-view {
  .toolbar {
    margin-bottom: 16px;
    display: flex;
    gap: 8px;
  }

  .perm-header {
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid #ebeef5;
  }

  .perm-groups {
    max-height: 400px;
    overflow-y: auto;
  }

  .perm-group {
    margin-bottom: 16px;

    .perm-group-title {
      font-weight: 600;
      color: #303133;
      margin-bottom: 8px;
      font-size: 14px;
    }

    .el-checkbox-group {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
  }

  .res-input-row {
    display: flex;
    gap: 8px;
  }

  .res-tags {
    min-height: 40px;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
  }

  .res-empty {
    color: #c0c4cc;
    font-size: 14px;
  }
}
</style>
