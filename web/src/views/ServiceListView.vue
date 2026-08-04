<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
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

const servers = ref<ServerItem[]>([])
const selectedHost = ref('')
const services = ref<ServiceItem[]>([])
const loading = ref(false)
const selectedRows = ref<ServiceItem[]>([])

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
    // restart 使用专用接口；start/stop 使用通用动作接口
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

onMounted(async () => {
  await loadServers()
  await loadServices()
})
</script>

<template>
  <div class="service-list-view">
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
  </div>
</template>

<style scoped lang="scss">
.service-list-view {
  display: flex;
  flex-direction: column;
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
