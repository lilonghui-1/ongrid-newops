<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import request from '@/api/request'

interface KnowledgeItem {
  id: number
  category: string
  symptom: string
  possible_causes: string[]
  diagnosis_steps: string[]
  solutions: string[]
  severity: string
  created_at: string
  updated_at: string
}

interface KnowledgeListResponse {
  total: number
  items: KnowledgeItem[]
}

interface CategoryOption {
  value: string
  label: string
}

const loading = ref(false)
const entries = ref<KnowledgeItem[]>([])
const total = ref(0)
const categoryFilter = ref('')
const severityFilter = ref('')
const keyword = ref('')

const categoryOptions = ref<CategoryOption[]>([])

const severityOptions = [
  { value: 'low', label: '低' },
  { value: 'medium', label: '中' },
  { value: 'high', label: '高' },
  { value: 'critical', label: '严重' },
]

const categoryLabelMap: Record<string, string> = {}

// 编辑/新增对话框
const showDialog = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')
const dialogLoading = ref(false)
const form = ref({
  category: 'system',
  symptom: '',
  possible_causes: '',
  diagnosis_steps: '',
  solutions: '',
  severity: 'medium',
})
const editingId = ref(0)

async function loadCategories() {
  try {
    const res = await request.get('/knowledge/categories')
    const data = res.data as CategoryOption[]
    categoryOptions.value = Array.isArray(data) ? data : []
    categoryOptions.value.forEach((c) => {
      categoryLabelMap[c.value] = c.label
    })
  } catch {
    // 使用默认值
  }
}

async function loadEntries() {
  loading.value = true
  try {
    const params: Record<string, unknown> = { page: 1, page_size: 500 }
    if (categoryFilter.value) params.category = categoryFilter.value
    if (severityFilter.value) params.severity = severityFilter.value
    if (keyword.value) params.keyword = keyword.value
    const res = await request.get<KnowledgeListResponse>('/knowledge/', { params })
    const data = res.data
    entries.value = Array.isArray(data.items) ? data.items : []
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

function severityTag(val: string): string {
  const map: Record<string, string> = {
    low: 'info',
    medium: 'warning',
    high: 'danger',
    critical: 'danger',
  }
  return map[val] || 'info'
}

function severityLabel(val: string): string {
  const map: Record<string, string> = {
    low: '低',
    medium: '中',
    high: '高',
    critical: '严重',
  }
  return map[val] || val
}

function fmtTime(t: string): string {
  const d = new Date(t)
  return isNaN(d.getTime()) ? t : d.toLocaleString('zh-CN')
}

function openCreate() {
  dialogMode.value = 'create'
  editingId.value = 0
  form.value = {
    category: 'system',
    symptom: '',
    possible_causes: '',
    diagnosis_steps: '',
    solutions: '',
    severity: 'medium',
  }
  showDialog.value = true
}

function openEdit(row: KnowledgeItem) {
  dialogMode.value = 'edit'
  editingId.value = row.id
  form.value = {
    category: row.category,
    symptom: row.symptom,
    possible_causes: (row.possible_causes || []).join('\n'),
    diagnosis_steps: (row.diagnosis_steps || []).join('\n'),
    solutions: (row.solutions || []).join('\n'),
    severity: row.severity,
  }
  showDialog.value = true
}

async function confirmSave() {
  if (!form.value.symptom) {
    ElMessage.warning('请输入症状描述')
    return
  }

  dialogLoading.value = true
  try {
    const body = {
      category: form.value.category,
      symptom: form.value.symptom,
      possible_causes: form.value.possible_causes.split('\n').filter(Boolean),
      diagnosis_steps: form.value.diagnosis_steps.split('\n').filter(Boolean),
      solutions: form.value.solutions.split('\n').filter(Boolean),
      severity: form.value.severity,
    }

    if (dialogMode.value === 'create') {
      await request.post('/knowledge/', body)
      ElMessage.success('知识条目已创建')
    } else {
      await request.put(`/knowledge/${editingId.value}`, body)
      ElMessage.success('知识条目已更新')
    }
    showDialog.value = false
    loadEntries()
  } catch {
    // 错误提示由拦截器处理
  } finally {
    dialogLoading.value = false
  }
}

async function deleteEntry(row: KnowledgeItem) {
  try {
    await ElMessageBox.confirm(
      `确定要删除知识条目 "${row.symptom}" 吗？`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消' },
    )
    await request.delete(`/knowledge/${row.id}`)
    ElMessage.success('知识条目已删除')
    loadEntries()
  } catch {
    // 用户取消
  }
}

function handleFilterChange() {
  loadEntries()
}

onMounted(async () => {
  await loadCategories()
  loadEntries()
})
</script>

<template>
  <div class="knowledge-view">
    <!-- 工具栏 -->
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <span class="page-title">知识库管理</span>
          <el-select
            v-model="categoryFilter"
            placeholder="全部分类"
            size="small"
            clearable
            style="width: 140px"
            @change="handleFilterChange"
          >
            <el-option v-for="c in categoryOptions" :key="c.value" :label="c.label" :value="c.value" />
          </el-select>
          <el-select
            v-model="severityFilter"
            placeholder="全部严重程度"
            size="small"
            clearable
            style="width: 150px"
            @change="handleFilterChange"
          >
            <el-option v-for="s in severityOptions" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
          <el-input
            v-model="keyword"
            placeholder="搜索症状关键词"
            size="small"
            clearable
            style="width: 200px"
            @change="handleFilterChange"
            @clear="handleFilterChange"
          />
        </div>
        <div class="toolbar-right">
          <el-button :icon="Refresh" size="small" @click="loadEntries">刷新</el-button>
          <el-button type="primary" :icon="Plus" size="small" @click="openCreate">新增知识条目</el-button>
        </div>
      </div>
    </el-card>

    <!-- 知识条目列表 -->
    <el-card shadow="never" class="table-card" v-loading="loading">
      <el-table :data="entries" stripe style="width: 100%" empty-text="暂无知识条目，点击「新增知识条目」添加">
        <el-table-column prop="symptom" label="症状描述" min-width="200" show-overflow-tooltip />
        <el-table-column label="分类" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ categoryLabel(row.category) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="严重程度" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="severityTag(row.severity)" size="small" effect="dark">
              {{ severityLabel(row.severity) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="可能原因" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.possible_causes?.length">{{ row.possible_causes.join('; ') }}</span>
            <span v-else style="color: #c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column label="诊断步骤" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.diagnosis_steps?.length">{{ row.diagnosis_steps.join('; ') }}</span>
            <span v-else style="color: #c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column label="解决方案" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.solutions?.length">{{ row.solutions.join('; ') }}</span>
            <span v-else style="color: #c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="170" align="center">
          <template #default="{ row }">
            {{ fmtTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" link type="danger" @click="deleteEntry(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增/编辑对话框 -->
    <el-dialog
      v-model="showDialog"
      :title="dialogMode === 'create' ? '新增知识条目' : '编辑知识条目'"
      width="700px"
      :close-on-click-modal="false"
    >
      <el-form :model="form" label-width="100px" label-position="right">
        <el-form-item label="症状描述">
          <el-input v-model="form.symptom" placeholder="如 CPU 使用率持续超过 80%" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category" style="width: 100%">
            <el-option v-for="c in categoryOptions" :key="c.value" :label="c.label" :value="c.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="严重程度">
          <el-select v-model="form.severity" style="width: 100%">
            <el-option v-for="s in severityOptions" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="可能原因">
          <el-input
            v-model="form.possible_causes"
            type="textarea"
            :rows="3"
            placeholder="每行一个原因"
          />
        </el-form-item>
        <el-form-item label="诊断步骤">
          <el-input
            v-model="form.diagnosis_steps"
            type="textarea"
            :rows="3"
            placeholder="每行一个步骤"
          />
        </el-form-item>
        <el-form-item label="解决方案">
          <el-input
            v-model="form.solutions"
            type="textarea"
            :rows="3"
            placeholder="每行一个方案"
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
.knowledge-view {
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
      gap: 12px;

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