<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Refresh, Search } from '@element-plus/icons-vue'
import request from '@/api/request'

interface TopoNode {
  node_id: number
  type: string
  name: string
  props?: Record<string, unknown>
}

interface TopoRelation {
  src: number
  dst: number
  type: string
}

interface TopoOverview {
  node_count: number
  relation_count: number
  nodes: TopoNode[]
  relations: TopoRelation[]
}

interface ExpandHit {
  node_id: number
  node_name: string
  node_type: string
  hops: number
  relation_type: string
  semantics: string
  propagates: boolean
  reached_via: string
}

const loading = ref(false)
const overview = ref<TopoOverview>({ node_count: 0, relation_count: 0, nodes: [], relations: [] })

// 搜索
const searchKeyword = ref('')
const searchNodes = ref<TopoNode[]>([])

// 展开
const expandNode = ref('')
const expandDepth = ref(2)
const expandDirection = ref<'both' | 'downstream' | 'upstream'>('both')
const expandResult = ref<{ center: { node_name: string }; count: number; hits: ExpandHit[] } | null>(null)
const expandLoading = ref(false)

function typeTag(t: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  if (t === 'service') return 'success'
  if (t === 'app') return 'primary'
  if (t === 'cluster') return 'warning'
  if (t === 'device' || t === 'rack') return 'info'
  return 'info'
}

async function loadOverview() {
  loading.value = true
  try {
    const res = await request.get<TopoOverview>('/topology/')
    overview.value = res.data
  } catch {
    // 错误提示由拦截器处理
  } finally {
    loading.value = false
  }
}

async function doSearch() {
  if (!searchKeyword.value) {
    searchNodes.value = []
    return
  }
  try {
    const res = await request.get<{ nodes: TopoNode[] }>('/topology/search', {
      params: { keyword: searchKeyword.value },
    })
    searchNodes.value = res.data.nodes || []
  } catch {
    // 错误提示由拦截器处理
  }
}

async function doExpand() {
  if (!expandNode.value) return
  expandLoading.value = true
  try {
    const res = await request.get<{ center: { node_name: string }; count: number; hits: ExpandHit[] }>(
      '/topology/expand',
      {
        params: {
          node: expandNode.value,
          depth: expandDepth.value,
          direction: expandDirection.value,
        },
      },
    )
    expandResult.value = res.data
  } catch {
    // 错误提示由拦截器处理
  } finally {
    expandLoading.value = false
  }
}

function semanticsLabel(s: string): string {
  const map: Record<string, string> = {
    hard_dep: '硬依赖',
    runtime_dep: '运行依赖',
    traffic: '流量',
    redundancy: '冗余',
    observation: '观测',
    aggregation: '聚合',
  }
  return map[s] || s
}

function viaLabel(v: string): string {
  return v === 'downstream' ? '下游' : v === 'upstream' ? '上游' : v
}

onMounted(() => {
  loadOverview()
})
</script>

<template>
  <div class="topology-view">
    <!-- 概览 -->
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <span class="page-title">拓扑管理</span>
          <el-tag size="small" effect="plain">节点 {{ overview.node_count }}</el-tag>
          <el-tag size="small" type="success" effect="plain">关系 {{ overview.relation_count }}</el-tag>
        </div>
        <div class="toolbar-right">
          <el-button :icon="Refresh" size="small" @click="loadOverview">刷新</el-button>
        </div>
      </div>
    </el-card>

    <div class="grid-2">
      <!-- 节点列表 -->
      <el-card shadow="never" v-loading="loading">
        <template #header>拓扑节点</template>
        <el-table :data="overview.nodes as TopoNode[]" stripe size="small" max-height="420" empty-text="暂无节点（请检查 knowledge/topology.yaml）">
          <el-table-column prop="node_id" label="ID" width="60" />
          <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">
              <span style="font-family: monospace; color: #409eff">{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="type" label="类型" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="typeTagOverview(row.type)" size="small" effect="plain">{{ row.type }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 关系列表 -->
      <el-card shadow="never" v-loading="loading">
        <template #header>拓扑关系</template>
        <el-table :data="overview.relations as TopoRelation[]" stripe size="small" max-height="420" empty-text="暂无关系">
          <el-table-column label="来源" min-width="120" show-overflow-tooltip>
            <template #default="{ row }">
              <span style="font-family: monospace">{{ row.src }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="type" label="关系" min-width="120" show-overflow-tooltip>
            <template #default="{ row }">
              <el-tag size="small" type="warning" effect="plain">{{ row.type }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="目标" min-width="120" show-overflow-tooltip>
            <template #default="{ row }">
              <span style="font-family: monospace">{{ row.dst }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <!-- 搜索 -->
    <el-card shadow="never">
      <template #header>节点搜索</template>
      <div class="search-row">
        <el-input
          v-model="searchKeyword"
          placeholder="输入节点名称关键词（如 mysql / nginx / 192.168）"
          clearable
          @keyup.enter="doSearch"
        />
        <el-button type="primary" size="small" :icon="Search" @click="doSearch">搜索</el-button>
      </div>
      <div v-if="searchNodes.length" class="search-result">
        <el-tag
          v-for="n in searchNodes"
          :key="n.node_id"
          size="small"
          :type="typeTagOverview(n.type)"
          class="search-tag"
        >
          {{ n.node_id }}:{{ n.name }}({{ n.type }})
        </el-tag>
      </div>
    </el-card>

    <!-- 影响面展开 -->
    <el-card shadow="never" v-loading="expandLoading">
      <template #header>影响面展开（RCA）</template>
      <div class="expand-row">
        <el-input
          v-model="expandNode"
          placeholder="节点名称或 ID，如 nginx-gateway"
          style="flex: 1"
          clearable
        />
        <el-input-number v-model="expandDepth" :min="1" :max="5" size="small" />
        <el-select v-model="expandDirection" size="small" style="width: 120px">
          <el-option label="双向" value="both" />
          <el-option label="下游" value="downstream" />
          <el-option label="上游" value="upstream" />
        </el-select>
        <el-button type="primary" size="small" @click="doExpand">展开</el-button>
      </div>
      <el-table
        v-if="expandResult"
        :data="expandResult.hits as ExpandHit[]"
        stripe
        size="small"
        max-height="360"
        empty-text="无传播可达节点"
        style="margin-top: 12px"
      >
        <el-table-column prop="node_name" label="受影响节点" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <span style="font-family: monospace; color: #e6a23c">{{ row.node_name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="hops" label="跳数" width="60" align="center" />
        <el-table-column prop="relation_type" label="关系" width="120" align="center">
          <template #default="{ row }">
            <el-tag size="small" type="warning" effect="plain">{{ row.relation_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="语义" width="110" align="center">
          <template #default="{ row }">
            {{ semanticsLabel(row.semantics) }}
          </template>
        </el-table-column>
        <el-table-column label="方向" width="80" align="center">
          <template #default="{ row }">
            {{ viaLabel(row.reached_via) }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped lang="scss">
.topology-view {
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
  }
}

.grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;

  @media (max-width: 1200px) {
    grid-template-columns: 1fr;
  }
}

.search-row,
.expand-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.search-result {
  margin-top: 12px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>