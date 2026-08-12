<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Check } from '@element-plus/icons-vue'
import request from '@/api/request'

interface ParamItem {
  id: number
  key: string
  value: string | null
  description: string | null
  is_secret: boolean
  category: string
  created_at: string
  updated_at: string
}

interface ParamListResponse {
  total: number
  items: ParamItem[]
}

interface CategoryOption {
  value: string
  label: string
}

const loading = ref(false)
const applyLoading = ref(false)
const params = ref<ParamItem[]>([])
const total = ref(0)
const categoryFilter = ref('')

const categoryOptions = ref<CategoryOption[]>([])

// 编辑/新增对话框
const showDialog = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')
const dialogLoading = ref(false)
const form = ref({
  key: '',
  value: '',
  description: '',
  is_secret: false,
  category: 'general',
})

const categoryLabelMap: Record<string, string> = {}

async function loadCategories() {
  try {
    const res = await request.get('/parameters/categories')
    const data = res.data as CategoryOption[]
    categoryOptions.value = Array.isArray(data) ? data : []
    categoryOptions.value.forEach((c) => {
      categoryLabelMap[c.value] = c.label
    })
  } catch {
    // 使用默认值
  }
}

async function loadParams() {
  loading.value = true
  try {
    const params: Record<string, unknown> = { page: 1, page_size: 500 }
    if (categoryFilter.value) {
      params.category = categoryFilter.value
    }
    const res = await request.get<ParamListResponse>('/parameters/', { params })
    const data = res.data
    params.value = Array.isArray(data.items) ? data.items : []
    total.value = data.total ?? 0
  } catch {
    // 错误提示由拦截器处理
  } finally {
    loading.value = false
  }
}

function categoryLabel(val: string): string {
  return categoryLabelMap[val] || val
}

function categoryTag(val: string): 'success' | 'warning' | 'danger' | 'info' | undefined {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info' | undefined> = {
    ssh: undefined,
    database: 'success',
    llm: 'warning',
    email: 'danger',
    notify: 'info',
    web: undefined,
    log_platform: 'success',
    general: 'info',
  }
  return map[val] ?? 'info'
}

function fmtTime(t: string): string {
  const d = new Date(t)
  return isNaN(d.getTime()) ? t : d.toLocaleString('zh-CN')
}

function openCreate() {
  dialogMode.value = 'create'
  form.value = { key: '', value: '', description: '', is_secret: false, category: 'general' }
  showDialog.value = true
}

function openEdit(row: ParamItem) {
  dialogMode.value = 'edit'
  form.value = {
    key: row.key,
    value: row.value === '******' ? '' : (row.value || ''),
    description: row.description || '',
    is_secret: row.is_secret,
    category: row.category,
  }
  showDialog.value = true
}

async function confirmSave() {
  if (!form.value.key) {
    ElMessage.warning('请输入参数名')
    return
  }

  dialogLoading.value = true
  try {
    if (dialogMode.value === 'create') {
      await request.post('/parameters/', form.value)
      ElMessage.success('参数已创建')
    } else {
      await request.put(`/parameters/${encodeURIComponent(form.value.key)}`, {
        value: form.value.value,
        description: form.value.description,
        is_secret: form.value.is_secret,
        category: form.value.category,
      })
      ElMessage.success('参数已更新')
    }
    showDialog.value = false
    loadParams()
  } catch {
    // 错误提示由拦截器处理
  } finally {
    dialogLoading.value = false
  }
}

async function deleteParam(row: ParamItem) {
  try {
    await ElMessageBox.confirm(
      `确定要删除参数 "${row.key}" 吗？`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消' },
    )
    await request.delete(`/parameters/${encodeURIComponent(row.key)}`)
    ElMessage.success('参数已删除')
    loadParams()
  } catch {
    // 用户取消
  }
}

async function applyParameters() {
  try {
    await ElMessageBox.confirm(
      '应用参数将把所有参数值注入环境变量并触发配置热重载，确定继续？',
      '应用确认',
      { type: 'warning', confirmButtonText: '确定应用', cancelButtonText: '取消' },
    )
    applyLoading.value = true
    const res = await request.post('/parameters/apply')
    const data = res.data as { success?: boolean; message?: string }
    if (data.success) {
      ElMessage.success(data.message || '参数已应用')
    } else {
      ElMessage.warning(data.message || '应用失败')
    }
  } catch {
    // 用户取消或请求失败
  } finally {
    applyLoading.value = false
  }
}

function handleFilterChange() {
  loadParams()
}

onMounted(async () => {
  await loadCategories()
  loadParams()
})
</script>

<template>
  <div class="param-view">
    <!-- 工具栏 -->
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <span class="page-title">参数管理</span>
          <el-select
            v-model="categoryFilter"
            placeholder="全部分类"
            size="small"
            clearable
            style="width: 160px"
            @change="handleFilterChange"
          >
            <el-option
              v-for="c in categoryOptions"
              :key="c.value"
              :label="c.label"
              :value="c.value"
            />
          </el-select>
        </div>
        <div class="toolbar-right">
          <el-button :icon="Refresh" size="small" @click="loadParams">刷新</el-button>
          <el-button type="success" :icon="Check" size="small" :loading="applyLoading" @click="applyParameters">
            应用到配置
          </el-button>
          <el-button type="primary" :icon="Plus" size="small" @click="openCreate">新增参数</el-button>
        </div>
      </div>
    </el-card>

    <!-- 参数列表 -->
    <el-card shadow="never" class="table-card" v-loading="loading">
      <el-table :data="params as ParamItem[]" stripe style="width: 100%" empty-text="暂无参数，点击「新增参数」添加">
        <el-table-column prop="key" label="参数名" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span style="font-family: monospace; color: #409eff">{{ row.key }}</span>
          </template>
        </el-table-column>
        <el-table-column label="值" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.is_secret && row.value" style="font-family: monospace; color: #909399">******</span>
            <span v-else style="font-family: monospace">{{ row.value || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="120" align="center">
          <template #default="{ row }">
            <el-tag :type="categoryTag(row.category)" size="small" effect="plain">
              {{ categoryLabel(row.category) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="敏感" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_secret" size="small" type="danger">是</el-tag>
            <span v-else style="color: #c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.description || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="170" align="center">
          <template #default="{ row }">
            {{ fmtTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openEdit(row as ParamItem)">编辑</el-button>
            <el-button size="small" link type="danger" @click="deleteParam(row as ParamItem)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增/编辑对话框 -->
    <el-dialog
      v-model="showDialog"
      :title="dialogMode === 'create' ? '新增参数' : '编辑参数'"
      width="550px"
      :close-on-click-modal="false"
    >
      <el-form :model="form" label-width="80px" label-position="right">
        <el-form-item label="参数名">
          <el-input
            v-model="form.key"
            placeholder="如 SSH_PASSWORD、MYSQL_PASSWORD"
            :disabled="dialogMode === 'edit'"
          />
        </el-form-item>
        <el-form-item label="参数值">
          <el-input
            v-model="form.value"
            :type="form.is_secret ? 'password' : 'text'"
            placeholder="参数值"
            show-password
          />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category" style="width: 100%">
            <el-option
              v-for="c in categoryOptions"
              :key="c.value"
              :label="c.label"
              :value="c.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="敏感">
          <el-switch v-model="form.is_secret" />
          <span style="margin-left: 8px; color: #909399; font-size: 12px">密码、密钥等敏感信息</span>
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="2"
            placeholder="参数描述（可选）"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="dialogLoading" @click="confirmSave">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.param-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.toolbar-card {
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;

    .toolbar-left {
      display: flex;
      align-items: center;
      gap: 16px;

      .page-title {
        font-size: 16px;
        font-weight: 600;
        color: #303133;
      }
    }

    .toolbar-right {
      display: flex;
      gap: 8px;
    }
  }
}

.table-card {
  .pagination-wrap {
    display: flex;
    justify-content: flex-end;
    margin-top: 16px;
  }
}
</style>
