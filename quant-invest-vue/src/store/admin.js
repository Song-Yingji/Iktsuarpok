import { ref } from 'vue'
import { adminApi } from '../api'

// 知识库统计：上传文档面板与后台页头共用同一份数据，避免重复请求
const kbStats = ref(null)

async function loadKbStats(force = false) {
  if (kbStats.value && !force) return kbStats.value
  kbStats.value = await adminApi.stats()
  return kbStats.value
}

export function useAdminKb() {
  return { kbStats, loadKbStats }
}
