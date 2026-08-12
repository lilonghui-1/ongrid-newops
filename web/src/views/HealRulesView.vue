<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import request from '@/api/request'

interface RuleAction {
  tool: string
  params: Record<string, unknown>
  confirm_required: boolean
}

interface HealRuleItem {
  id: number
  name: string
  condition: string
  description: string | null
  actions: RuleAction[]
  enabled: boolean
  created_at: string
  updated_at: string
}

interface HealRuleListResponse {
  total: number
  items: HealRuleItem[]
}

const loading = ref(false)
const rules = ref<HealRuleItem[]>([])
const total = ref(0)
const enabledFilter = ref<boolean | ''>('')

// 编辑/新增对话框
const showDialog = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')
const dialogLoading = ref(false)
const form = ref({
  name: '',
  condition: '',
  description: '',
  actions: [{ tool: '', params: '{}', confirm_required: false }] as Array<{
    tool: string
    params: string
    confirm_required: boolean
  }>,
})
const editingId = ref(0)

const toolOptions = [
  { value: 'service_control', label: 'service_control - 服务控制' },
  { value: 'ssh_execute', label: 'ssh_execute - 远程执行' },
  { value: 'db_execute', label: 'db_execute - 数据库执行' },
  { value: 'send_notification', label: 'send_notification - 发送通知' },
]

async function loadRules() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {}
    if (enabledFilter.value !== '') params.enabled = enabledFilter.value
    const res = await request.get<HealRuleListResponse>('/heal-rules/', { params })
    const data = res.data
    rules.value = Array.isArray(data.items) ? data.items : []
    total.value = data.total ?? 0
  } catch {
    // 错误提示由拦截器处理
  } finally {
    loading.value = false
  }
}

function fmtTime(t: string): string {
  const d = new Date(t)
  return isNaN(d.getTime()) ? t : d.toLocaleString('zh-CN')
}

function actionsText(actions: RuleAction[]): string {
  if (!actions?.length) return '-'
  return actions.map((a) => {
    const confirm = a.confirm_required ? ' [需确认]' : ''
    return `${a.tool}${confirm}`
  }).join('; ')
}

function openCreate() {
  dialogMode.value = 'create'
  editingId.value = 0
  form.value = {
    name: '',
    condition: '',
    description: '',
    actions: [{ tool: '', params: '{}', confirm_required: false }],
  }
  showDialog.value = true
}

function openEdit(row: HealRuleItem) {
  dialogMode.value = 'edit'
  editingId.value = row.id
  form.value = {
    name: row.name,
    condition: row.condition,
    description: row.description || '',
    actions: (row.actions || []).map((a) => ({
      tool: a.tool,
      params: JSON.stringify(a.params || {}, null, 2),
      confirm_required: a.confirm_required || false,
    })),
  }
  if (form.value.actions.length === 0) {
    form.value.actions = [{ tool: '', params: '{}', confirm_required: false }]
  }
  showDialog.value = true
}

function addAction() {
  form.value.actions.push({ tool: '', params: '{}', confirm_required: false })
}

function removeAction(index: number) {
  if (form.value.actions.length <= 1) return
  form.value.actions.splice(index, 1)
}

async function confirmSave() {
  if (!form.value.name) {
    ElMessage.warning('请输入规则名称')
    return
  }
  if (!form.value.condition) {
    ElMessage.warning('请输入触发条件')
    return
  }

  // 验证操作
  const validActions = form.value.actions.filter((a) => a.tool)
  if (validActions.length === 0) {
    ElMessage.warning('请至少添加一个操作')
    return
  }

  dialogLoading.value = true
  try {
    const body = {
      name: form.value.name,
      condition: form.value.condition,
      description: form.value.description || null,
      actions: validActions.map((a) => ({
        tool: a.tool,
        params: (() => {
          try {
            return JSON.parse(a.params || '{}')
          } catch {
            return {}
          }
        })(),
        confirm_required: a.confirm_required,
      })),
    }

    if (dialogMode.value === 'create') {
      await request.post('/heal-rules/', body)
      ElMessage.success('自愈规则已创建')
    } else {
      await request.put(`/heal-rules/${editingId.value}`, body)
      ElMessage.success('自愈规则已更新')
    }
    showDialog.value = false
    loadRules()
  } catch {
    // 错误提示由拦截器处理
  } finally {
    dialogLoading.value = false
  }
}

async function deleteRule(row: HealRuleItem) {
  try {
    await ElMessageBox.confirm(
      `确定要删除自愈规则 "${row.name}" 吗？`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消' },
    )
    await request.delete(`/heal-rules/${row.id}`)
    ElMessage.success('自愈规则已删除')
    loadRules()
  } catch {
    // 用户取消
  }
}

async function toggleEnabled(row: HealRuleItem) {
  try {
    await request.put(`/heal-rules/${row.id}`, { enabled: !row.enabled })
    ElMessage.success(row.enabled ? '规则已禁用' : '规则已启用')
    loadRules()
  } catch {
    // 错误提示由拦截器处理
  }
}

function handleFilterChange() {
  loadRules()
}

onMounted(() => {
  loadRules()
})
</script>

<template>
  <div class="heal-rules-view">
    <!-- 工具栏 -->
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <span class="page-title">自愈规则管理</span>
          <el-select
            v-model="enabledFilter"
            placeholder="全部状态"
            size="small"
            clearable
            style="width: 130px"
            @change="handleFilterChange"
          >
            <el-option label="已启用" :value="true" />
            <el-option label="已禁用" :value="false" />
          </el-select>
        </div>
        <div class="toolbar-right">
          <el-button :icon="Refresh" size="small" @click="loadRules">刷新</el-button>
          <el-button type="primary" :icon="Plus" size="small" @click="openCreate">新增规则</el-button>
        </div>
      </div>
    </el-card>

    <!-- 自愈规则列表 -->
    <el-card shadow="never" class="table-card" v-loading="loading">
      <el-table :data="rules as HealRuleItem[]" stripe style="width: 100%" empty-text="暂无自愈规则，点击「新增规则」添加">
        <el-table-column prop="name" label="规则名称" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span style="font-family: monospace; color: #409eff">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="condition" label="触发条件" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span style="font-family: monospace">{{ row.condition }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.description || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            {{ actionsText(row.actions) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small" effect="dark">
              {{ row.enabled ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="170" align="center">
          <template #default="{ row }">
            {{ fmtTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openEdit(row as HealRuleItem)">编辑</el-button>
            <el-button size="small" link :type="row.enabled ? 'warning' : 'success'" @click="toggleEnabled(row as HealRuleItem)">
              {{ row.enabled ? '禁用' : '启用' }}
            </el-button>
            <el-button size="small" link type="danger" @click="deleteRule(row as HealRuleItem)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增/编辑对话框 -->
    <el-dialog
      v-model="showDialog"
      :title="dialogMode === 'create' ? '新增自愈规则' : '编辑自愈规则'"
      width="700px"
      :close-on-click-modal="false"
    >
      <el-form :model="form" label-width="100px" label-position="right">
        <el-form-item label="规则名称">
          <el-input
            v-model="form.name"
            placeholder="如 restart_nginx"
            :disabled="dialogMode === 'edit'"
          />
        </el-form-item>
        <el-form-item label="触发条件">
          <el-input
            v-model="form.condition"
            placeholder="如 nginx_status == 'stopped' or nginx_error_rate > 0.1"
          />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="2"
            placeholder="规则描述（可选）"
          />
        </el-form-item>
        <el-form-item label="执行操作">
          <div class="actions-container">
            <div v-for="(action, idx) in form.actions" :key="idx" class="action-item">
              <div class="action-row">
                <el-select v-model="action.tool" placeholder="选择工具" style="flex: 1; min-width: 200px">
                  <el-option v-for="t in toolOptions" :key="t.value" :label="t.label" :value="t.value" />
                </el-select>
                <el-button
                  v-if="form.actions.length > 1"
                  size="small"
                  type="danger"
                  link
                  @click="removeAction(idx)"
                >
                  移除
                </el-button>
              </div>
              <div class="action-row" style="margin-top: 8px">
                <el-input
                  v-model="action.params"
                  type="textarea"
                  :rows="2"
                  placeholder='参数 JSON，如 {"service_name": "nginx", "action": "restart"}'
                />
              </div>
              <div class="action-row" style="margin-top: 4px">
                <el-checkbox v-model="action.confirm_required">需要人工确认</el-checkbox>
              </div>
              <el-divider v-if="idx < form.actions.length - 1" style="margin: 8px 0" />
            </div>
            <el-button size="small" type="primary" link @click="addAction">+ 添加操作</el-button>
          </div>
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
.heal-rules-view {
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

.actions-container {
  width: 100%;

  .action-item {
    .action-row {
      display: flex;
      gap: 8px;
      align-items: center;
    }
  }
}
</style>