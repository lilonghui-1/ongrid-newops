<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, VideoPlay } from '@element-plus/icons-vue'
import request from '@/api/request'

interface SkillItem {
  name: string
  description: string
  when_to_use: string
  security_class: string
  activation_mode: string
  keywords: string[]
  confirm_required: boolean
  enabled: boolean
}

interface SkillListResponse {
  total: number
  items: SkillItem[]
}

const loading = ref(false)
const skills = ref<SkillItem[]>([])
const total = ref(0)
const matchText = ref('')
const matchResult = ref<string[]>([])

// 执行对话框
const showExec = ref(false)
const execLoading = ref(false)
const execSkill = ref<SkillItem | null>(null)
const execParams = ref('{}')
const execApproved = ref(false)
const execResult = ref<Record<string, unknown> | null>(null)

async function loadSkills() {
  loading.value = true
  try {
    const res = await request.get<SkillListResponse>('/skills/')
    const data = res.data
    skills.value = Array.isArray(data.items) ? data.items : []
    total.value = data.total ?? 0
  } catch {
    // 错误提示由拦截器处理
  } finally {
    loading.value = false
  }
}

async function doMatch() {
  if (!matchText.value) {
    matchResult.value = []
    return
  }
  try {
    const res = await request.get<{ items: Array<{ name: string }> }>('/skills/match', {
      params: { text: matchText.value },
    })
    matchResult.value = (res.data.items || []).map((i) => i.name)
  } catch {
    // 错误提示由拦截器处理
  }
}

function openExec(skill: SkillItem) {
  execSkill.value = skill
  execParams.value = '{}'
  execApproved.value = false
  execResult.value = null
  showExec.value = true
}

async function confirmExec() {
  if (!execSkill.value) return
  execLoading.value = true
  try {
    let params: Record<string, unknown> = {}
    try {
      params = JSON.parse(execParams.value || '{}')
    } catch {
      ElMessage.warning('参数 JSON 格式不正确')
      return
    }
    const res = await request.post('/skills/execute', {
      skill: execSkill.value.name,
      params,
      reviewer_approved: execApproved.value,
    })
    execResult.value = res.data
    ElMessage.success('技能执行完成')
  } catch {
    // 错误提示由拦截器处理
  } finally {
    execLoading.value = false
  }
}

function securityTagType(cls: string): 'success' | 'warning' | 'danger' | 'info' {
  if (cls === 'read-only') return 'success'
  if (cls === 'mutating') return 'danger'
  if (cls === 'outbound') return 'warning'
  return 'info'
}

function securityLabel(cls: string): string {
  if (cls === 'read-only') return '只读'
  if (cls === 'mutating') return '变更'
  if (cls === 'outbound') return '外发'
  return cls
}

onMounted(() => {
  loadSkills()
})
</script>

<template>
  <div class="skills-view">
    <!-- 工具栏 -->
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <span class="page-title">技能目录</span>
          <span class="total-text">共 {{ total }} 个技能</span>
        </div>
        <div class="toolbar-right">
          <el-button :icon="Refresh" size="small" @click="loadSkills">刷新</el-button>
        </div>
      </div>
    </el-card>

    <!-- 技能匹配 -->
    <el-card shadow="never">
      <div class="match-row">
        <el-input
          v-model="matchText"
          placeholder="输入文本，按关键词匹配可激活技能（如：重启 nginx 服务）"
          clearable
          @keyup.enter="doMatch"
        />
        <el-button type="primary" size="small" @click="doMatch">匹配</el-button>
      </div>
      <div v-if="matchResult.length" class="match-result">
        <el-tag v-for="name in matchResult" :key="name" size="small" class="match-tag">
          {{ name }}
        </el-tag>
      </div>
      <el-empty
        v-else-if="matchText"
        description="无匹配技能"
        :image-size="60"
      />
    </el-card>

    <!-- 技能列表 -->
    <el-card shadow="never" v-loading="loading">
      <el-table :data="skills as SkillItem[]" stripe style="width: 100%" empty-text="暂无技能">
        <el-table-column prop="name" label="技能名称" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span style="font-family: monospace; color: #409eff">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="220" show-overflow-tooltip />
        <el-table-column label="安全分类" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="securityTagType(row.security_class)" size="small" effect="dark">
              {{ securityLabel(row.security_class) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="激活方式" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="row.activation_mode === 'always' ? 'primary' : 'warning'" size="small" effect="plain">
              {{ row.activation_mode === 'always' ? '始终可用' : '关键词' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="需审批" width="80" align="center">
          <template #default="{ row }">
            {{ row.confirm_required ? '是' : '否' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link :icon="VideoPlay" @click="openExec(row as SkillItem)">
              执行
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 执行对话框 -->
    <el-dialog
      v-model="showExec"
      :title="`执行技能: ${execSkill?.name || ''}`"
      width="560px"
      :close-on-click-modal="false"
    >
      <el-form label-width="90px" label-position="right">
        <el-form-item label="技能说明">
          <div class="skill-desc">{{ execSkill?.description }}</div>
        </el-form-item>
        <el-form-item label="参数 JSON">
          <el-input
            v-model="execParams"
            type="textarea"
            :rows="4"
            placeholder='如 {"host": "10.0.0.1", "command": "df -h"}'
          />
        </el-form-item>
        <el-form-item v-if="execSkill?.confirm_required || execSkill?.security_class === 'mutating'" label="审批标记">
          <el-checkbox v-model="execApproved">已通过 reviewer 审批（reviewer_approved）</el-checkbox>
        </el-form-item>
      </el-form>
      <div v-if="execResult" class="exec-result">
        <pre>{{ JSON.stringify(execResult, null, 2) }}</pre>
      </div>
      <template #footer>
        <el-button @click="showExec = false">关闭</el-button>
        <el-button type="primary" :loading="execLoading" @click="confirmExec">执行</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.skills-view {
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

      .total-text {
        color: #909399;
        font-size: 13px;
      }
    }
  }
}

.match-row {
  display: flex;
  gap: 8px;
}

.match-result {
  margin-top: 12px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.skill-desc {
  color: #606266;
  font-size: 13px;
}

.exec-result {
  margin-top: 8px;
  background: #f5f7fa;
  border-radius: 6px;
  padding: 12px;
  max-height: 240px;
  overflow: auto;

  pre {
    margin: 0;
    font-size: 12px;
    color: #303133;
    white-space: pre-wrap;
    word-break: break-all;
  }
}
</style>