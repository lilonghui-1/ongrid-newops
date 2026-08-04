<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Refresh, SwitchButton } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import request from '@/api/request'

const route = useRoute()
const router = useRouter()

const host = computed(() => String(route.params.host || ''))

interface StatusData {
  host?: string
  online?: boolean
  cpu?: { usage?: number; cores?: number; load_avg?: string }
  memory?: { total?: string; used?: string; free?: string; usage?: number }
  disk?: { total?: string; used?: string; free?: string; usage?: number }
  uptime?: string
  [key: string]: unknown
}

interface ProcessItem {
  pid: number | string
  name?: string
  cpu?: number
  memory?: number
  [key: string]: unknown
}

const loading = ref(false)
const metricsLoading = ref(false)
const status = ref<StatusData>({})
const processes = ref<ProcessItem[]>([])
const timeRange = ref<'1h' | '24h' | '7d'>('1h')

const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null

function num(v: unknown): number {
  if (v == null) return 0
  if (typeof v === 'number') return v
  const n = parseFloat(String(v).replace('%', ''))
  return isNaN(n) ? 0 : n
}

function isOnline(): boolean {
  return status.value.online === true
}

function uptimeText(): string {
  return status.value.uptime || '-'
}

const cpu = computed(() => num(status.value.cpu?.usage))
const mem = computed(() => num(status.value.memory?.usage))
const disk = computed(() => num(status.value.disk?.usage))

function usageColor(v: number) {
  if (v >= 90) return '#f56c6c'
  if (v >= 80) return '#e6a23c'
  return '#67c23a'
}

async function loadStatus() {
  loading.value = true
  try {
    const res = await request.get<StatusData>(
      `/servers/${encodeURIComponent(host.value)}/status`,
    )
    status.value = res.data || {}
  } catch {
    // 错误提示由拦截器处理
  } finally {
    loading.value = false
  }
}

interface ParsedMetrics {
  times: string[]
  cpu: number[]
  memory: number[]
  disk: number[]
}

/** 兼容多种 metrics 响应结构 */
function parseMetrics(data: unknown): ParsedMetrics {
  const empty: ParsedMetrics = { times: [], cpu: [], memory: [], disk: [] }
  if (!data || typeof data !== 'object') return empty
  const d = data as Record<string, unknown>

  // 后端 MetricHistoryResponse: { host, metrics: [{cpu_usage, memory_usage, disk_usage, collected_at}], time_range }
  const metrics = d.metrics as Record<string, unknown>[] | undefined
  if (Array.isArray(metrics) && metrics.length > 0) {
    const times: string[] = []
    const cpuArr: number[] = []
    const memArr: number[] = []
    const diskArr: number[] = []
    for (const m of metrics) {
      times.push(String(m.collected_at || m.timestamp || ''))
      cpuArr.push(num(m.cpu_usage ?? m.cpu))
      memArr.push(num(m.memory_usage ?? m.memory ?? m.mem))
      diskArr.push(num(m.disk_usage ?? m.disk))
    }
    return { times, cpu: cpuArr, memory: memArr, disk: diskArr }
  }

  // 兼容旧格式：series 数组
  const series = d.series as
    | { name?: string; data?: number[] }[]
    | undefined
  if (Array.isArray(series)) {
    const times = (d.timestamps as string[]) || (d.times as string[]) || (d.labels as string[]) || []
    const find = (names: string[]) =>
      series.find(
        (s) =>
          s.name && names.some((n) => s.name!.toLowerCase().includes(n)),
      )?.data || []
    return {
      times,
      cpu: find(['cpu']),
      memory: find(['mem', 'memory']),
      disk: find(['disk']),
    }
  }
  return empty
}

async function loadMetrics() {
  metricsLoading.value = true
  try {
    const res = await request.get(
      `/servers/${encodeURIComponent(host.value)}/metrics`,
      { params: { time_range: timeRange.value } },
    )
    const parsed = parseMetrics(res.data)
    renderChart(parsed)
  } catch {
    // 错误提示由拦截器处理
  } finally {
    metricsLoading.value = false
  }
}

function renderChart(data: ParsedMetrics) {
  if (!chartRef.value) return
  if (!chart) chart = echarts.init(chartRef.value)
  const option: echarts.EChartsOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['CPU', '内存', '磁盘'], top: 0 },
    grid: { left: 50, right: 24, top: 40, bottom: 40 },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: data.times.length ? data.times : ['暂无数据'],
    },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: '{value}%' },
      max: 100,
    },
    color: ['#409eff', '#67c23a', '#e6a23c'],
    series: [
      {
        name: 'CPU',
        type: 'line',
        smooth: true,
        showSymbol: false,
        areaStyle: { opacity: 0.1 },
        data: data.cpu,
      },
      {
        name: '内存',
        type: 'line',
        smooth: true,
        showSymbol: false,
        areaStyle: { opacity: 0.1 },
        data: data.memory,
      },
      {
        name: '磁盘',
        type: 'line',
        smooth: true,
        showSymbol: false,
        areaStyle: { opacity: 0.1 },
        data: data.disk,
      },
    ],
  }
  chart.setOption(option, true)
}

async function refreshAll() {
  await Promise.all([loadStatus(), loadMetrics()])
  ElMessage.success('已刷新')
}

async function powerAction(action: 'restart' | 'shutdown') {
  const label = action === 'restart' ? '重启' : '关机'
  try {
    await ElMessageBox.confirm(
      `确定要对服务器 ${host.value} 执行【${label}】操作吗？该操作可能导致服务中断。`,
      `${label}确认`,
      {
        type: 'warning',
        confirmButtonText: `确定${label}`,
        cancelButtonText: '取消',
        confirmButtonClass: action === 'shutdown' ? 'el-button--danger' : '',
      },
    )
    await request.post(
      `/servers/${encodeURIComponent(host.value)}/power`,
      { action },
    )
    ElMessage.success(`${label}指令已发送`)
    setTimeout(loadStatus, 2000)
  } catch (e) {
    if (e !== 'cancel') {
      // 接口错误由拦截器处理
    }
  }
}

function handleResize() {
  chart?.resize()
}

function goBack() {
  router.push('/servers')
}

watch(timeRange, () => loadMetrics())

onMounted(async () => {
  await loadStatus()
  await nextTick()
  await loadMetrics()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div class="server-detail-view" v-loading="loading">
    <div class="page-head">
      <el-button :icon="ArrowLeft" link @click="goBack">返回列表</el-button>
      <span class="head-title">
        服务器详情 - {{ host }}
      </span>
      <el-button :icon="Refresh" size="small" @click="refreshAll">刷新</el-button>
    </div>

    <!-- 信息卡 -->
    <el-card shadow="never" class="info-card">
      <el-descriptions :column="4" border>
        <el-descriptions-item label="主机地址">
          {{ host }}
        </el-descriptions-item>
        <el-descriptions-item label="CPU 核心">
          {{ status.cpu?.cores ?? '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="负载均值">
          {{ status.cpu?.load_avg || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="isOnline() ? 'success' : 'danger'" size="small">
            <span class="dot" :class="isOnline() ? 'online' : 'offline'"></span>
            {{ isOnline() ? '在线' : '离线' }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 指标卡片 -->
    <el-row :gutter="16">
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="metric-card">
          <div class="metric-head">
            <span class="metric-name">CPU 使用率</span>
            <el-icon color="#409eff"><Cpu /></el-icon>
          </div>
          <div class="metric-value" :style="{ color: usageColor(cpu) }">
            {{ cpu.toFixed(1) }}%
          </div>
          <el-progress
            :percentage="cpu"
            :color="usageColor(cpu)"
            :stroke-width="8"
          />
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="metric-card">
          <div class="metric-head">
            <span class="metric-name">内存使用率</span>
            <el-icon color="#67c23a"><Histogram /></el-icon>
          </div>
          <div class="metric-value" :style="{ color: usageColor(mem) }">
            {{ mem.toFixed(1) }}%
          </div>
          <el-progress
            :percentage="mem"
            :color="usageColor(mem)"
            :stroke-width="8"
          />
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="metric-card">
          <div class="metric-head">
            <span class="metric-name">磁盘使用率</span>
            <el-icon color="#e6a23c"><Coin /></el-icon>
          </div>
          <div class="metric-value" :style="{ color: usageColor(disk) }">
            {{ disk.toFixed(1) }}%
          </div>
          <el-progress
            :percentage="disk"
            :color="usageColor(disk)"
            :stroke-width="8"
          />
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="metric-card">
          <div class="metric-head">
            <span class="metric-name">运行时长</span>
            <el-icon color="#909399"><Timer /></el-icon>
          </div>
          <div class="metric-value uptime">{{ uptimeText() }}</div>
          <div class="metric-sub">持续运行中</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 趋势图 -->
    <el-card shadow="never" class="chart-card" v-loading="metricsLoading">
      <template #header>
        <div class="card-head">
          <span class="card-title">资源使用趋势</span>
          <el-radio-group v-model="timeRange" size="small">
            <el-radio-button value="1h">近 1 小时</el-radio-button>
            <el-radio-button value="24h">近 24 小时</el-radio-button>
            <el-radio-button value="7d">近 7 天</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <div ref="chartRef" class="chart-container"></div>
    </el-card>

    <!-- 进程列表 -->
    <el-card shadow="never">
      <template #header>
        <span class="card-title">进程列表</span>
      </template>
      <el-table :data="processes" stripe max-height="420" empty-text="暂无进程数据">
        <el-table-column prop="pid" label="PID" width="120" />
        <el-table-column prop="name" label="进程名称" min-width="200" show-overflow-tooltip />
        <el-table-column label="CPU%" width="180">
          <template #default="{ row }">
            <el-progress
              :percentage="Math.min(100, num(row.cpu))"
              :stroke-width="10"
              :color="usageColor(num(row.cpu))"
            />
          </template>
        </el-table-column>
        <el-table-column label="内存%" width="180">
          <template #default="{ row }">
            <el-progress
              :percentage="Math.min(100, num(row.memory))"
              :stroke-width="10"
              :color="usageColor(num(row.memory))"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 电源操作 -->
    <el-card shadow="never" class="power-card">
      <template #header>
        <span class="card-title">电源操作</span>
      </template>
      <div class="power-actions">
        <el-button
          type="warning"
          :icon="Refresh"
          @click="powerAction('restart')"
        >
          重启服务器
        </el-button>
        <el-button
          type="danger"
          :icon="SwitchButton"
          @click="powerAction('shutdown')"
        >
          关机
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped lang="scss">
.server-detail-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-head {
  display: flex;
  align-items: center;
  gap: 12px;

  .head-title {
    font-size: 16px;
    font-weight: 600;
    color: #303133;
    flex: 1;
  }
}

.metric-card {
  margin-bottom: 16px;

  .metric-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;

    .metric-name {
      font-size: 13px;
      color: #909399;
    }
  }

  .metric-value {
    font-size: 26px;
    font-weight: 700;
    margin-bottom: 8px;

    &.uptime {
      font-size: 22px;
    }
  }

  .metric-sub {
    font-size: 12px;
    color: #c0c4cc;
    margin-top: 12px;
  }
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.chart-card {
  .chart-container {
    width: 100%;
    height: 360px;
  }
}

.power-card {
  .power-actions {
    display: flex;
    gap: 12px;
  }
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  margin-right: 4px;
  vertical-align: middle;

  &.online {
    background: #fff;
  }

  &.offline {
    background: #fff;
  }
}
</style>
