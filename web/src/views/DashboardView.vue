<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import request from '@/api/request'

const router = useRouter()

interface ServerItem {
  host: string
  name?: string
  online?: boolean
  os_type?: string
  cpu_usage?: number
  memory_usage?: number
  disk_usage?: number
  uptime?: string
  [key: string]: unknown
}

interface AlertItem {
  time: string
  server: string
  type: string
  level: '严重' | '警告' | '信息'
  message: string
}

const loading = ref(false)
const servers = ref<ServerItem[]>([])
const alerts = ref<AlertItem[]>([])
let timer: ReturnType<typeof setInterval> | null = null

/** 安全取数值：兼容 snake_case / camelCase / 百分比字符串 */
function num(v: unknown): number {
  if (v == null) return 0
  if (typeof v === 'number') return v
  const n = parseFloat(String(v).replace('%', ''))
  return isNaN(n) ? 0 : n
}

function isOnline(s: ServerItem): boolean {
  return s.online === true
}

function fmtTime(t?: string): string {
  if (!t) return new Date().toLocaleString('zh-CN')
  const d = new Date(t)
  return isNaN(d.getTime()) ? t : d.toLocaleString('zh-CN')
}

function uptimeText(s: ServerItem): string {
  const u = s.uptime
  if (u == null || u === '') return '-'
  if (typeof u === 'number') {
    // 秒数转可读
    const days = Math.floor(u / 86400)
    const hours = Math.floor((u % 86400) / 3600)
    const mins = Math.floor((u % 3600) / 60)
    return days > 0 ? `${days}天${hours}小时` : `${hours}小时${mins}分`
  }
  return String(u)
}

const stats = computed(() => {
  const total = servers.value.length
  const online = servers.value.filter(isOnline).length
  const offline = total - online
  return { total, online, offline, alerts: alerts.value.length }
})

function buildAlerts() {
  const list: AlertItem[] = []
  for (const s of servers.value) {
    const cpu = num(s.cpu_usage)
    const mem = num(s.memory_usage)
    const disk = num(s.disk_usage)
    const name = s.name || s.host
    if (!isOnline(s)) {
      list.push({
        time: fmtTime(),
        server: name,
        type: '可用性',
        level: '严重',
        message: `服务器离线（${s.host}）`,
      })
      continue
    }
    if (cpu >= 90) {
      list.push({ time: fmtTime(), server: name, type: 'CPU', level: '严重', message: `CPU 使用率过高：${cpu.toFixed(1)}%` })
    } else if (cpu >= 80) {
      list.push({ time: fmtTime(), server: name, type: 'CPU', level: '警告', message: `CPU 使用率偏高：${cpu.toFixed(1)}%` })
    }
    if (mem >= 90) {
      list.push({ time: fmtTime(), server: name, type: '内存', level: '严重', message: `内存使用率过高：${mem.toFixed(1)}%` })
    } else if (mem >= 80) {
      list.push({ time: fmtTime(), server: name, type: '内存', level: '警告', message: `内存使用率偏高：${mem.toFixed(1)}%` })
    }
    if (disk >= 90) {
      list.push({ time: fmtTime(), server: name, type: '磁盘', level: '严重', message: `磁盘使用率过高：${disk.toFixed(1)}%` })
    } else if (disk >= 80) {
      list.push({ time: fmtTime(), server: name, type: '磁盘', level: '警告', message: `磁盘使用率偏高：${disk.toFixed(1)}%` })
    }
  }
  alerts.value = list.slice(0, 10)
}

async function loadData() {
  loading.value = true
  try {
    const res = await request.get<ServerItem[] | { items?: ServerItem[] }>('/servers')
    const raw = res.data
    const list: ServerItem[] = Array.isArray(raw)
      ? raw
      : (raw as { items?: ServerItem[] }).items || []
    // 拉取每台服务器实时状态进行补充
    const results = await Promise.allSettled(
      list.map(async (s) => {
        try {
          const r = await request.get(
            `/servers/${encodeURIComponent(s.host)}/status`,
          )
          const d = r.data || {}
          // 后端返回嵌套结构: cpu:{usage}, memory:{usage}, disk:{usage}
          const cpuData = (d as Record<string, any>)?.cpu || {}
          const memData = (d as Record<string, any>)?.memory || {}
          const diskData = (d as Record<string, any>)?.disk || {}
          return {
            ...s,
            online: d.online ?? s.online,
            cpu_usage: cpuData.usage ?? 0,
            memory_usage: memData.usage ?? 0,
            disk_usage: diskData.usage ?? 0,
            uptime: d.uptime || '',
          } as ServerItem
        } catch {
          return s
        }
      }),
    )
    servers.value = results.map((p, i) =>
      p.status === 'fulfilled' ? p.value : list[i],
    )
    buildAlerts()
  } catch {
    // 错误提示由拦截器处理
  } finally {
    loading.value = false
  }
}

async function refresh() {
  await loadData()
  ElMessage.success('数据已刷新')
}

function goDetail(host: string) {
  router.push(`/servers/${encodeURIComponent(host)}`)
}

function levelTag(level: AlertItem['level']) {
  return level === '严重' ? 'danger' : level === '警告' ? 'warning' : 'info'
}

function usageColor(v: number) {
  if (v >= 90) return '#f56c6c'
  if (v >= 80) return '#e6a23c'
  return '#67c23a'
}

onMounted(() => {
  loadData()
  timer = setInterval(loadData, 30000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="dashboard-view" v-loading="loading">
    <!-- KPI 卡片 -->
    <el-row :gutter="16" class="kpi-row">
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="kpi-card kpi-total">
          <div class="kpi-icon"><el-icon :size="28"><Monitor /></el-icon></div>
          <div class="kpi-body">
            <div class="kpi-label">服务器总数</div>
            <div class="kpi-value">{{ stats.total }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="kpi-card kpi-online">
          <div class="kpi-icon"><el-icon :size="28"><CircleCheck /></el-icon></div>
          <div class="kpi-body">
            <div class="kpi-label">在线数</div>
            <div class="kpi-value">{{ stats.online }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="kpi-card kpi-offline">
          <div class="kpi-icon"><el-icon :size="28"><CircleClose /></el-icon></div>
          <div class="kpi-body">
            <div class="kpi-label">离线数</div>
            <div class="kpi-value">{{ stats.offline }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="kpi-card kpi-alert">
          <div class="kpi-icon"><el-icon :size="28"><Warning /></el-icon></div>
          <div class="kpi-body">
            <div class="kpi-label">活跃告警</div>
            <div class="kpi-value">{{ stats.alerts }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 服务器状态网格 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">服务器状态</span>
          <el-button :icon="Refresh" size="small" @click="refresh">刷新</el-button>
        </div>
      </template>
      <el-empty v-if="!servers.length" description="暂无服务器数据" />
      <el-row v-else :gutter="16">
        <el-col
          v-for="s in servers"
          :key="s.host"
          :xs="24"
          :sm="12"
          :md="8"
          :lg="6"
        >
          <el-card
            shadow="hover"
            class="server-card"
            @click="goDetail(s.host)"
          >
            <div class="server-card-head">
              <div class="server-name">
                <span
                  class="status-dot"
                  :class="isOnline(s) ? 'online' : 'offline'"
                ></span>
                {{ s.name || s.host }}
              </div>
              <el-tag size="small" :type="isOnline(s) ? 'success' : 'danger'">
                {{ isOnline(s) ? '在线' : '离线' }}
              </el-tag>
            </div>
            <div class="server-meta">地址：{{ s.host }}</div>
            <div class="server-meta">系统：{{ s.os_type || '-' }}</div>
            <div class="server-meta">运行：{{ uptimeText(s) }}</div>
            <div class="metric">
              <div class="metric-label">CPU {{ num(s.cpu_usage).toFixed(1) }}%</div>
              <el-progress
                :percentage="num(s.cpu_usage)"
                :color="usageColor(num(s.cpu_usage))"
                :stroke-width="8"
              />
            </div>
            <div class="metric">
              <div class="metric-label">内存 {{ num(s.memory_usage).toFixed(1) }}%</div>
              <el-progress
                :percentage="num(s.memory_usage)"
                :color="usageColor(num(s.memory_usage))"
                :stroke-width="8"
              />
            </div>
            <div class="metric">
              <div class="metric-label">磁盘 {{ num(s.disk_usage).toFixed(1) }}%</div>
              <el-progress
                :percentage="num(s.disk_usage)"
                :color="usageColor(num(s.disk_usage))"
                :stroke-width="8"
              />
            </div>
          </el-card>
        </el-col>
      </el-row>
    </el-card>

    <!-- 告警列表 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">最近告警</span>
          <el-tag size="small" type="info">最近 {{ alerts.length }} 条</el-tag>
        </div>
      </template>
      <el-table :data="alerts" stripe size="default" empty-text="暂无告警">
        <el-table-column prop="time" label="时间" width="180" />
        <el-table-column prop="server" label="服务器" min-width="140" />
        <el-table-column prop="type" label="类型" width="100" />
        <el-table-column prop="level" label="级别" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="levelTag(row.level)">{{ row.level }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="消息" min-width="240" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>

<style scoped lang="scss">
.dashboard-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.kpi-row {
  margin-bottom: 0;
}

.kpi-card {
  :deep(.el-card__body) {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 20px;
  }
}

.kpi-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}

.kpi-total .kpi-icon {
  background: linear-gradient(135deg, #409eff, #337ecc);
}
.kpi-online .kpi-icon {
  background: linear-gradient(135deg, #67c23a, #4eaa23);
}
.kpi-offline .kpi-icon {
  background: linear-gradient(135deg, #f56c6c, #c44040);
}
.kpi-alert .kpi-icon {
  background: linear-gradient(135deg, #e6a23c, #b8821f);
}

.kpi-body {
  flex: 1;

  .kpi-label {
    font-size: 13px;
    color: #909399;
  }

  .kpi-value {
    font-size: 28px;
    font-weight: 700;
    color: #303133;
    margin-top: 4px;
  }
}

.section-card {
  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;

    .section-title {
      font-size: 15px;
      font-weight: 600;
      color: #303133;
    }
  }
}

.server-card {
  margin-bottom: 16px;
  cursor: pointer;
  transition: transform 0.2s;

  &:hover {
    transform: translateY(-2px);
  }

  .server-card-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;

    .server-name {
      font-size: 15px;
      font-weight: 600;
      color: #303133;
      display: flex;
      align-items: center;
      gap: 8px;
    }
  }

  .server-meta {
    font-size: 12px;
    color: #909399;
    line-height: 1.8;
  }

  .metric {
    margin-top: 10px;

    .metric-label {
      font-size: 12px;
      color: #606266;
      margin-bottom: 2px;
    }
  }
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;

  &.online {
    background: #67c23a;
    box-shadow: 0 0 6px rgba(103, 194, 58, 0.6);
  }

  &.offline {
    background: #f56c6c;
    box-shadow: 0 0 6px rgba(245, 108, 108, 0.6);
  }
}
</style>
