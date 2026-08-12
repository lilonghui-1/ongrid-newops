<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Edit, Plus, Refresh, Search } from '@element-plus/icons-vue'
import request from '@/api/request'

interface ServerItem {
  host: string
  hostname?: string
  ip?: string
  [key: string]: unknown
}

interface ServiceItem {
  name: string
  status?: string
  pid?: number | string
  cpu?: number
  memory?: number
  [key: string]: unknown
}

interface AppServiceDef {
  id: number
  server_host: string
  name: string
  display_name: string
  description: string
  category: string
  port: number | null
  enabled: boolean
  created_by: string
  created_at: string
  updated_at: string | null
}

const categoryLabels: Record<string, string> = {
  web: 'Web 服务',
  middleware: '中间件',
  database: '数据库',
  application: '应用服务',
  custom: '自定义',
}

// ========== 动态服务 ==========
const servers = ref<ServerItem[]>([])
const selectedHost = ref('')
const services = ref<ServiceItem[]>([])
const loading = ref(false)
const selectedRows = ref<ServiceItem[]>([])

// ========== 服务定义管理 ==========
const defServers = ref<ServerItem[]>([])
const defLoading = ref(false)
const defList = ref<AppServiceDef[]>([])
const defKeyword = ref('')
const defFilterHost = ref('')
const defDialogVisible = ref(false)
const defDialogTitle = ref('')
const defFormLoading = ref(false)
const defForm = ref({
  server_host: '',
  name: '',
  display_name: '',
  description: '',
  category: 'application',
  port: null as number | null,
  enabled: true,
})
const editingDefId = ref<number | null>(null)

function num(v: unknown): number {
  if (v == null) return 0
  if (typeof v === 'number') return v
  const n = parseFloat(String(v).replace('%', ''))
  return isNaN(n) ? 0 : n
}

function isRunning(s: ServiceItem | Record<string, any>): boolean {
  return String(s.status ?? '').toLowerCase() === 'running'
}

const runningCount = computed(
  () => services.value.filter(isRunning).length,
)

const filteredDefList = computed(() => {
  const kw = defKeyword.value.trim().toLowerCase()
  const host = defFilterHost.value
  return defList.value.filter((d) => {
    if (host && d.server_host !== host) return false
    if (!kw) return true
    return (
      d.name.toLowerCase().includes(kw) ||
      (d.display_name || '').toLowerCase().includes(kw) ||
      (d.description || '').toLowerCase().includes(kw)
    )
  })
})

// ========== 动态服务 ==========
async function loadServers() {
  try {
    const res = await request.get<ServerItem[] | { items?: ServerItem[] }>('/servers')
    const raw = res.data
    servers.value = Array.isArray(raw)
      ? raw
      : (raw as { items?: ServerItem[] }).items || []
    if (servers.value.length && !selectedHost.value) {
      selectedHost.value = servers.value[0].host
    }
  } catch {
    // 错误提示由拦截器处理
  }
}

async function loadServices() {
  if (!selectedHost.value) {
    services.value = []
    return
  }
  loading.value = true
  try {
    const res = await request.get<ServiceItem[] | { services?: ServiceItem[] }>(
      `/services/${encodeURIComponent(selectedHost.value)}`,
    )
    const raw = res.data
    services.value = Array.isArray(raw)
      ? raw
      : (raw as { services?: ServiceItem[] }).services || []
  } catch {
    // 错误提示由拦截器处理
  } finally {
    loading.value = false
  }
}

async function onHostChange() {
  selectedRows.value = []
  await loadServices()
}

async function refresh() {
  await loadServices()
  ElMessage.success('服务列表已刷新')
}

async function operate(row: ServiceItem | Record<string, any>, action: 'start' | 'stop' | 'restart') {
  const label = { start: '启动', stop: '停止', restart: '重启' }[action]
  try {
    await ElMessageBox.confirm(
      `确定要对服务【${row.name}】执行【${label}】操作吗？`,
      `${label}确认`,
      {
        type: action === 'stop' ? 'warning' : 'info',
        confirmButtonText: `确定${label}`,
        cancelButtonText: '取消',
      },
    )
    if (action === 'restart') {
      await request.post(
        `/services/${encodeURIComponent(selectedHost.value)}/${encodeURIComponent(row.name)}/restart`,
      )
    } else {
      await request.post(
        `/services/${encodeURIComponent(selectedHost.value)}/${encodeURIComponent(row.name)}/${action}`,
      )
    }
    ElMessage.success(`${label}指令已发送：${row.name}`)
    await loadServices()
  } catch (e) {
    if (e !== 'cancel') {
      // 接口错误由拦截器处理
    }
  }
}

function handleSelectionChange(rows: ServiceItem[]) {
  selectedRows.value = rows
}

async function batchRestart() {
  if (!selectedRows.value.length) {
    ElMessage.warning('请先勾选要重启的服务')
    return
  }
  const names = selectedRows.value.map((r) => r.name)
  try {
    await ElMessageBox.confirm(
      `确定要批量重启以下 ${names.length} 个服务吗？\n${names.join('、')}`,
      '批量重启确认',
      {
        type: 'warning',
        confirmButtonText: '确定重启',
        cancelButtonText: '取消',
      },
    )
    await request.post(
      `/services/${encodeURIComponent(selectedHost.value)}/batch-restart`,
      { service_names: names, action: 'restart' },
    )
    ElMessage.success(`批量重启指令已发送：${names.length} 个服务`)
    selectedRows.value = []
    await loadServices()
  } catch (e) {
    if (e !== 'cancel') {
      // 接口错误由拦截器处理
    }
  }
}

// ========== 服务定义管理 ==========
async function loadDefServers() {
  try {
    const res = await request.get<ServerItem[] | { items?: ServerItem[] }>('/servers')
    const raw = res.data
    defServers.value = Array.isArray(raw)
      ? raw
      : (raw as { items?: ServerItem[] }).items || []
  } catch {
    // 错误提示由拦截器处理
  }
}

async function loadDefList() {
  defLoading.value = true
  try {
    const res = await request.get<AppServiceDef[]>('/services/manage')
    defList.value = Array.isArray(res.data) ? res.data : []
  } catch {
    // 错误提示由拦截器处理
  } finally {
    defLoading.value = false
  }
}

function openCreateDialog() {
  editingDefId.value = null
  defDialogTitle.value = '新增服务定义'
  defForm.value = {
    server_host: defServers.value.length ? defServers.value[0].host : '',
    name: '',
    display_name: '',
    description: '',
    category: 'application',
    port: null,
    enabled: true,
  }
  defDialogVisible.value = true
}

async function openEditDialog(row: AppServiceDef) {
  editingDefId.value = row.id
  defDialogTitle.value = '编辑服务定义'
  defForm.value = {
    server_host: row.server_host,
    name: row.name,
    display_name: row.display_name,
    description: row.description,
    category: row.category,
    port: row.port,
    enabled: row.enabled,
  }
  defDialogVisible.value = true
}

async function confirmDefSave() {
  if (!defForm.value.server_host) {
    ElMessage.warning('请选择所属服务器')
    return
  }
  if (!defForm.value.name.trim()) {
    ElMessage.warning('请输入服务名称')
    return
  }
  defFormLoading.value = true
  try {
    if (editingDefId.value) {
      await request.put(`/services/manage/${editingDefId.value}`, defForm.value)
      ElMessage.success('服务定义已更新')
    } else {
      await request.post('/services/manage', defForm.value)
      ElMessage.success('服务定义已创建')
    }
    defDialogVisible.value = false
    await loadDefList()
  } catch {
    // 错误提示由拦截器处理
  } finally {
    defFormLoading.value = false
  }
}

async function deleteDef(row: AppServiceDef) {
  try {
    await ElMessageBox.confirm(
      `确定要删除服务定义「${row.display_name || row.name}」吗？此操作仅删除定义，不影响服务器上的实际服务。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消' },
    )
    await request.delete(`/services/manage/${row.id}`)
    ElMessage.success('服务定义已删除')
    await loadDefList()
  } catch (e) {
    if (e !== 'cancel') {
      // 接口错误由拦截器处理
    }
  }
}

function getCategoryLabel(cat: string): string {
  return categoryLabels[cat] || cat
}

function fmtTime(t?: string): string {
  if (!t) return '-'
  const d = new Date(t)
  return isNaN(d.getTime()) ? t : d.toLocaleString('zh-CN')
}

onMounted(async () => {
  await loadServers()
  await loadServices()
  await loadDefServers()
  await loadDefList()
})
</script>

<template>
  <div class="service-list-view">
    <el-tabs type="border-card">
      <el-tab-pane label="动态服务" class="tab-pane">
        <el-card shadow="never">
          <template #header>
            <div class="toolbar">
              <div class="toolbar-left">
                <span class="title">应用服务管理</span>
                <el-select
                  v-model="selectedHost"
                  placeholder="选择服务器"
                  filterable
                  style="width: 220px"
                  @change="onHostChange"
                >
                  <el-option
                    v-for="s in servers"
                    :key="s.host"
                    :label="s.hostname || s.host"
                    :value="s.host"
                  />
                </el-select>
                <el-tag size="small" type="info">
                  共 {{ services.length }} 个，运行中 {{ runningCount }} 个
                </el-tag>
              </div>
              <div class="toolbar-right">
                <el-button
                  type="warning"
                  :disabled="!selectedRows.length"
                  @click="batchRestart"
                >
                  批量重启（{{ selectedRows.length }}）
                </el-button>
                <el-button :icon="Refresh" @click="refresh">刷新</el-button>
              </div>
            </div>
          </template>

          <el-table
            :data="services"
            v-loading="loading"
            stripe
            style="width: 100%"
            empty-text="暂无服务数据"
            @selection-change="handleSelectionChange"
          >
            <el-table-column type="selection" width="48" />
            <el-table-column prop="name" label="服务名称" min-width="180" show-overflow-tooltip />
            <el-table-column label="状态" width="110" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="isRunning(row) ? 'success' : 'danger'">
                  {{ isRunning(row) ? 'running' : 'stopped' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="pid" label="PID" width="120">
              <template #default="{ row }">{{ row.pid ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="CPU%" width="160">
              <template #default="{ row }">{{ num(row.cpu).toFixed(1) }}%</template>
            </el-table-column>
            <el-table-column label="内存%" width="160">
              <template #default="{ row }">{{ num(row.memory).toFixed(1) }}%</template>
            </el-table-column>
            <el-table-column label="操作" width="260" align="center" fixed="right">
              <template #default="{ row }">
                <el-button
                  size="small"
                  type="success"
                  link
                  :disabled="isRunning(row)"
                  @click="operate(row, 'start')"
                >
                  启动
                </el-button>
                <el-button
                  size="small"
                  type="danger"
                  link
                  :disabled="!isRunning(row)"
                  @click="operate(row, 'stop')"
                >
                  停止
                </el-button>
                <el-button
                  size="small"
                  type="warning"
                  link
                  @click="operate(row, 'restart')"
                >
                  重启
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="服务定义" class="tab-pane">
        <el-card shadow="never">
          <template #header>
            <div class="toolbar">
              <div class="toolbar-left">
                <span class="title">服务定义管理</span>
                <el-select
                  v-model="defFilterHost"
                  placeholder="按服务器筛选"
                  filterable
                  clearable
                  style="width: 200px"
                >
                  <el-option
                    v-for="s in defServers"
                    :key="s.host"
                    :label="s.hostname || s.host"
                    :value="s.host"
                  />
                </el-select>
                <el-input
                  v-model="defKeyword"
                  placeholder="搜索服务名称/描述"
                  :prefix-icon="Search"
                  clearable
                  style="width: 220px"
                />
                <el-tag size="small" type="info">
                  共 {{ filteredDefList.length }} 个
                </el-tag>
              </div>
              <div class="toolbar-right">
                <el-button type="primary" :icon="Plus" @click="openCreateDialog">
                  新增
                </el-button>
                <el-button :icon="Refresh" @click="loadDefList">刷新</el-button>
              </div>
            </div>
          </template>

          <el-table
            :data="filteredDefList as AppServiceDef[]"
            v-loading="defLoading"
            stripe
            style="width: 100%"
            empty-text="暂无服务定义，请点击「新增」添加"
          >
            <el-table-column prop="name" label="服务名称" min-width="140" show-overflow-tooltip />
            <el-table-column prop="display_name" label="显示名称" min-width="140">
              <template #default="{ row }">{{ row.display_name || '-' }}</template>
            </el-table-column>
            <el-table-column prop="server_host" label="所属服务器" min-width="140" />
            <el-table-column prop="category" label="分类" width="120">
              <template #default="{ row }">
                <el-tag size="small">{{ getCategoryLabel(row.category) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="port" label="端口" width="80" align="center">
              <template #default="{ row }">{{ row.port ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="状态" width="80" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="row.enabled ? 'success' : 'info'">
                  {{ row.enabled ? '启用' : '停用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">{{ row.description || '-' }}</template>
            </el-table-column>
            <el-table-column label="创建时间" width="170">
              <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="140" align="center" fixed="right">
              <template #default="{ row }">
                <el-button
                  size="small"
                  type="primary"
                  link
                  :icon="Edit"
                  @click="openEditDialog(row as AppServiceDef)"
                >
                  编辑
                </el-button>
                <el-button
                  size="small"
                  type="danger"
                  link
                  :icon="Delete"
                  @click="deleteDef(row as AppServiceDef)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 新增/编辑服务定义对话框 -->
    <el-dialog
      v-model="defDialogVisible"
      :title="defDialogTitle"
      width="560px"
    >
      <el-form label-width="90px" label-position="right">
        <el-form-item label="所属服务器">
          <el-select v-model="defForm.server_host" style="width: 100%" filterable>
            <el-option
              v-for="s in defServers"
              :key="s.host"
              :label="s.hostname || s.host"
              :value="s.host"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="服务名称">
          <el-input
            v-model="defForm.name"
            placeholder="如: nginx"
            :disabled="!!editingDefId"
          />
        </el-form-item>
        <el-form-item label="显示名称">
          <el-input
            v-model="defForm.display_name"
            placeholder="如: Nginx Web 服务器"
          />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="defForm.category" style="width: 100%">
            <el-option label="Web 服务" value="web" />
            <el-option label="中间件" value="middleware" />
            <el-option label="数据库" value="database" />
            <el-option label="应用服务" value="application" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="端口">
          <el-input-number
            v-model="defForm.port"
            :min="1"
            :max="65535"
            :step="1"
            placeholder="可选"
            style="width: 100%"
            :value-on-clear="null"
          />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="defForm.description"
            type="textarea"
            :rows="3"
            placeholder="服务描述信息"
          />
        </el-form-item>
        <el-form-item label="启用监控">
          <el-switch v-model="defForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="defDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="defFormLoading"
          @click="confirmDefSave"
        >
          {{ editingDefId ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.service-list-view {
  display: flex;
  flex-direction: column;
}

.tab-pane {
  :deep(.el-card) {
    border: none;
    box-shadow: none;
  }
}

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
    flex-wrap: wrap;

    .title {
      font-size: 15px;
      font-weight: 600;
      color: #303133;
    }
  }

  .toolbar-right {
    display: flex;
    align-items: center;
    gap: 8px;
  }
}
</style>