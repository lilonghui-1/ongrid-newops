/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 后端 API 基础地址（开发环境作为 Vite 代理目标） */
  readonly VITE_API_BASE: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
