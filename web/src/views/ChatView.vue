<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
} from 'vue'
import { ElMessage } from 'element-plus'
import { ChatLineRound, Plus, Promotion, Upload } from '@element-plus/icons-vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import request from '@/api/request'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

marked.setOptions({ async: false, breaks: true, gfm: true })

interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
  streaming?: boolean
}

interface ChatSession {
  id: string
  title?: string
  created_at?: string
  updated_at?: string
  [key: string]: unknown
}

interface ChatModel {
  id: string
  name?: string
  [key: string]: unknown
}

const sessions = ref<ChatSession[]>([])
const currentSession = ref<ChatSession | null>(null)
const messages = ref<ChatMessage[]>([])
const models = ref<ChatModel[]>([])
const selectedModel = ref('')
const input = ref('')
const sending = ref(false)

const messageListRef = ref<HTMLElement>()

// 上传上下文弹窗
const uploadVisible = ref(false)
const uploadForm = ref({ type: 'log' as 'log' | 'config' | 'error', content: '' })

const currentSessionId = computed(() => currentSession.value?.id || '')

async function loadModels() {
  try {
    const res = await request.get('/chat/models')
    const data = res.data
    const list: ChatModel[] = Array.isArray(data)
      ? data.map((m) =>
          typeof m === 'string' ? { id: m, name: m } : { id: m.model, name: m.name },
        )
      : Array.isArray((data as { models?: any[] })?.models)
        ? (data as { models: any[] }).models.map((m) =>
            typeof m === 'string' ? { id: m, name: m } : { id: m.model, name: m.name },
          )
        : []
    models.value = list
    if (list.length && !selectedModel.value) {
      selectedModel.value = list[0].id
    }
  } catch {
    // 错误提示由拦截器处理
  }
}

async function loadSessions() {
  try {
    const res = await request.get('/chat/sessions')
    const data = res.data
    sessions.value = Array.isArray(data)
      ? data
      : (data as { sessions?: ChatSession[] })?.sessions || []
    if (sessions.value.length && !currentSession.value) {
      await selectSession(sessions.value[0])
    }
  } catch {
    // 错误提示由拦截器处理
  }
}

async function createSession() {
  try {
    const res = await request.post('/chat/sessions', {
      title: `新会话 ${new Date().toLocaleString('zh-CN')}`,
    })
    const data = res.data
    const session: ChatSession = data
    sessions.value.unshift(session)
    await selectSession(session)
    ElMessage.success('已创建新会话')
  } catch {
    // 错误提示由拦截器处理
  }
}

async function selectSession(session: ChatSession) {
  if (currentSessionId.value === session.id) return
  currentSession.value = session
  messages.value = []
  try {
    const res = await request.get(
      `/chat/${encodeURIComponent(session.id)}/messages`,
    )
    const data = res.data
    const list: ChatMessage[] = Array.isArray(data)
      ? data
      : (data as { messages?: ChatMessage[] })?.messages || []
    messages.value = list.map((m) => ({
      role: m.role === 'user' ? 'user' : 'assistant',
      content: m.content || '',
    }))
    scrollToBottom()
  } catch {
    // 错误提示由拦截器处理
  }
}

function renderMarkdown(content: string): string {
  if (!content) return ''
  try {
    const html = marked.parse(content, { async: false }) as string
    return DOMPurify.sanitize(html, { ADD_ATTR: ['target'] })
  } catch {
    return DOMPurify.sanitize(content)
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
}

async function sendMessage() {
  const text = input.value.trim()
  if (!text) return
  if (!currentSessionId.value) {
    ElMessage.warning('请先选择或创建会话')
    return
  }
  if (sending.value) return

  messages.value.push({ role: 'user', content: text })
  input.value = ''
  scrollToBottom()

  // 占位 AI 消息，流式增量追加到此对象（响应式数组元素）
  messages.value.push({ role: 'assistant', content: '', streaming: true })
  const aiMsg = messages.value[messages.value.length - 1]
  sending.value = true
  scrollToBottom()

  const abortController = new AbortController()
  try {
    const resp = await fetch(
      `/api/chat/${encodeURIComponent(currentSessionId.value)}/send`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${auth.token}`,
        },
        body: JSON.stringify({
          message: text,
          model: selectedModel.value || undefined,
        }),
        signal: abortController.signal,
      },
    )
    if (!resp.ok || !resp.body) {
      throw new Error(`请求失败：${resp.status}`)
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n')
      buffer = parts.pop() || ''
      for (const part of parts) {
        const line = part.trim()
        if (!line) continue
        if (!line.startsWith('data:')) continue
        const payload = line.slice(5).trim()
        if (payload === '[DONE]' || payload === 'DONE') {
          // 结束
        } else {
          let delta = ''
          try {
            const obj = JSON.parse(payload)
            delta =
              obj.content ||
              obj.delta ||
              obj.message ||
              obj.text ||
              (typeof obj === 'string' ? obj : '')
          } catch {
            delta = payload
          }
          if (delta) {
            aiMsg.content += delta
            scrollToBottom()
          }
        }
      }
    }
  } catch (e) {
    if ((e as Error)?.name === 'AbortError') {
      // 用户取消
    } else {
      ElMessage.error('对话请求失败')
      aiMsg.content += '\n\n> 请求失败，请稍后重试'
    }
  } finally {
    aiMsg.streaming = false
    sending.value = false
  }
}

function onInputEnter(e: Event | KeyboardEvent) {
  const ke = e as KeyboardEvent
  if (ke.shiftKey) return
  ke.preventDefault()
  sendMessage()
}

function openUpload() {
  if (!currentSessionId.value) {
    ElMessage.warning('请先选择或创建会话')
    return
  }
  uploadForm.value = { type: 'log', content: '' }
  uploadVisible.value = true
}

async function submitUpload() {
  if (!uploadForm.value.content.trim()) {
    ElMessage.warning('请粘贴上下文内容')
    return
  }
  try {
    await request.post(
      `/chat/${encodeURIComponent(currentSessionId.value)}/upload`,
      {
        type: uploadForm.value.type,
        content: uploadForm.value.content,
      },
    )
    ElMessage.success('上下文已上传')
    uploadVisible.value = false
  } catch {
    // 错误提示由拦截器处理
  }
}

onMounted(() => {
  loadModels()
  loadSessions()
})

onBeforeUnmount(() => {
  // 组件卸载时无需特殊清理（fetch 在卸载后会自然失败）
})
</script>

<template>
  <div class="chat-view">
    <el-row :gutter="16" class="chat-row">
      <!-- 左侧会话列表 -->
      <el-col :xs="24" :sm="24" :md="6" :lg="5">
        <el-card shadow="never" class="session-card">
          <template #header>
            <div class="session-head">
              <span class="card-title">会话列表</span>
              <el-button type="primary" size="small" :icon="Plus" @click="createSession">
                新建
              </el-button>
            </div>
          </template>
          <div class="session-list">
            <el-empty
              v-if="!sessions.length"
              description="暂无会话"
              :image-size="60"
            />
            <div
              v-for="s in sessions"
              :key="s.id"
              class="session-item"
              :class="{ active: currentSessionId === s.id }"
              @click="selectSession(s)"
            >
              <el-icon><ChatLineRound /></el-icon>
              <span class="session-title">{{ s.title || s.id }}</span>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 右侧对话区 -->
      <el-col :xs="24" :sm="24" :md="18" :lg="19">
        <el-card shadow="never" class="chat-card">
          <template #header>
            <div class="chat-head">
              <span class="card-title">
                {{ currentSession?.title || 'AI 运维对话' }}
              </span>
              <div class="model-select">
                <span class="label">模型：</span>
                <el-select
                  v-model="selectedModel"
                  placeholder="选择模型"
                  size="small"
                  style="width: 200px"
                >
                  <el-option
                    v-for="m in models"
                    :key="m.id"
                    :label="m.name || m.id"
                    :value="m.id"
                  />
                </el-select>
              </div>
            </div>
          </template>

          <div ref="messageListRef" class="message-list">
            <el-empty
              v-if="!messages.length"
              description="开始与 AI 运维助手对话吧"
              :image-size="100"
            />
            <div
              v-for="(msg, idx) in messages"
              :key="idx"
              class="message-row"
              :class="msg.role"
            >
              <div class="message-avatar">
                <el-icon v-if="msg.role === 'user'"><UserFilled /></el-icon>
                <el-icon v-else><ChatLineRound /></el-icon>
              </div>
              <div class="message-bubble" :class="msg.role">
                <div
                  v-if="msg.role === 'assistant'"
                  class="markdown-body"
                  v-html="renderMarkdown(msg.content)"
                ></div>
                <div v-else class="user-text">{{ msg.content }}</div>
                <span v-if="msg.streaming" class="typing">|</span>
              </div>
            </div>
          </div>

          <div class="input-area">
            <el-input
              v-model="input"
              type="textarea"
              :rows="3"
              resize="none"
              placeholder="输入消息，Enter 发送，Shift+Enter 换行"
              :disabled="sending"
              @keydown.enter="onInputEnter"
            />
            <div class="input-actions">
              <el-button :icon="Upload" @click="openUpload">上传上下文</el-button>
              <el-button
                type="primary"
                :icon="Promotion"
                :loading="sending"
                :disabled="!input.trim()"
                @click="sendMessage"
              >
                发送
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 上传上下文弹窗 -->
    <el-dialog v-model="uploadVisible" title="上传上下文" width="600px">
      <el-form label-position="top">
        <el-form-item label="上下文类型">
          <el-select v-model="uploadForm.type" style="width: 100%">
            <el-option label="日志" value="log" />
            <el-option label="配置文件" value="config" />
            <el-option label="错误信息" value="error" />
          </el-select>
        </el-form-item>
        <el-form-item label="内容">
          <el-input
            v-model="uploadForm.content"
            type="textarea"
            :rows="10"
            placeholder="粘贴日志、配置文件或错误信息内容"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" @click="submitUpload">上传</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.chat-view {
  display: flex;
  flex-direction: column;
}

.chat-row {
  margin: 0;
  height: calc(100vh - 120px);
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.session-card {
  height: 100%;

  .session-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .session-list {
    max-height: calc(100vh - 200px);
    overflow: auto;
  }

  .session-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    border-radius: 6px;
    cursor: pointer;
    color: #606266;
    transition: all 0.2s;
    margin-bottom: 4px;

    .session-title {
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 13px;
    }

    &:hover {
      background: #f5f7fa;
    }

    &.active {
      background: #ecf5ff;
      color: #409eff;
    }
  }

  :deep(.el-card__body) {
    padding: 8px;
  }
}

.chat-card {
  height: 100%;
  display: flex;
  flex-direction: column;

  :deep(.el-card__body) {
    flex: 1;
    display: flex;
    flex-direction: column;
    padding: 0;
    overflow: hidden;
  }

  .chat-head {
    display: flex;
    align-items: center;
    justify-content: space-between;

    .model-select {
      display: flex;
      align-items: center;
      gap: 6px;

      .label {
        font-size: 13px;
        color: #909399;
      }
    }
  }
}

.message-list {
  flex: 1;
  overflow: auto;
  padding: 16px;
  background: #f7f8fa;
}

.message-row {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;

  .message-avatar {
    width: 34px;
    height: 34px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    color: #fff;
    font-size: 18px;
  }

  &.user .message-avatar {
    background: #409eff;
  }

  &.assistant .message-avatar {
    background: #67c23a;
  }

  .message-bubble {
    max-width: 75%;
    padding: 10px 14px;
    border-radius: 10px;
    line-height: 1.6;
    word-break: break-word;

    &.user {
      background: #409eff;
      color: #fff;
      border-top-right-radius: 2px;
    }

    &.assistant {
      background: #fff;
      color: #303133;
      border: 1px solid #ebeef5;
      border-top-left-radius: 2px;
    }

    .user-text {
      white-space: pre-wrap;
    }

    .typing {
      animation: blink 1s steps(2) infinite;
      color: #409eff;
    }
  }

  &.user {
    flex-direction: row-reverse;

    .message-bubble {
      border-top-right-radius: 2px;
      border-top-left-radius: 10px;
    }
  }
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.input-area {
  border-top: 1px solid #ebeef5;
  padding: 12px;
  background: #fff;

  .input-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 8px;
  }
}

/* Markdown 渲染样式 */
.markdown-body {
  font-size: 14px;
  line-height: 1.7;

  :deep(p) {
    margin: 6px 0;
  }

  :deep(h1),
  :deep(h2),
  :deep(h3) {
    margin: 12px 0 8px;
    font-weight: 600;
  }

  :deep(ul),
  :deep(ol) {
    padding-left: 22px;
    margin: 6px 0;
  }

  :deep(code) {
    background: #f3f4f6;
    color: #c7254e;
    padding: 2px 5px;
    border-radius: 4px;
    font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
    font-size: 13px;
  }

  :deep(pre) {
    background: #1e1e1e;
    color: #d4d4d4;
    padding: 12px;
    border-radius: 8px;
    overflow-x: auto;
    margin: 8px 0;

    code {
      background: transparent;
      color: #d4d4d4;
      padding: 0;
      font-size: 13px;
    }
  }

  :deep(table) {
    border-collapse: collapse;
    margin: 8px 0;
    width: 100%;

    th,
    td {
      border: 1px solid #ebeef5;
      padding: 6px 10px;
    }

    th {
      background: #f5f7fa;
    }
  }

  :deep(blockquote) {
    border-left: 4px solid #409eff;
    padding-left: 12px;
    color: #909399;
    margin: 8px 0;
  }
}
</style>
