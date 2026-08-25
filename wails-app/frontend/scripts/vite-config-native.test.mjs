import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'

const configPath = new URL('../vite.config.ts', import.meta.url)
const configSource = await readFile(configPath, 'utf8')

// Vite 8 將原生載入設定檔；__dirname 只靠舊相容層，未來預設值會失效。
assert.ok(configSource.includes('import.meta.url'), 'vite config 必須使用原生 ESM 路徑')
assert.ok(!configSource.includes('__dirname'), 'vite config 不可依賴 __dirname 相容層')

console.log('Vite 原生 ESM 設定檢查通過')
