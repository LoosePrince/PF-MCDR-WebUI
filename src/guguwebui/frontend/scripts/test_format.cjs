/* eslint-disable no-console */
/**
 * format.ts 单元测试。
 *
 * 仓库前端没有 jest/vitest，这里直接使用 devDependency 自带的 typescript
 * 把 format.ts 转译为 CommonJS 后执行断言，零新增依赖。
 * 运行：pnpm test:format
 */
const path = require('path')
const ts = require('typescript')

const root = path.resolve(__dirname, '..')
const srcPath = path.join(root, 'src', 'utils', 'format.ts')
const source = require('fs').readFileSync(srcPath, 'utf8')

const out = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
  },
  fileName: srcPath,
}).outputText

const moduleExports = {}
new Function('module', 'exports', 'require', out)(moduleExports, moduleExports, require)
const f = moduleExports

let failures = 0
function assert(condition, label) {
  if (condition) {
    console.log(`  ✓ ${label}`)
  } else {
    failures += 1
    console.error(`  ✗ ${label}`)
  }
}

console.log('format.ts 单测')
assert(f.isValidEpoch(1700000000) === true, 'isValidEpoch(1700000000)')
assert(f.isValidEpoch(0) === false, 'isValidEpoch(0)')
assert(f.isValidEpoch(null) === false, 'isValidEpoch(null)')
assert(f.isValidEpoch(undefined) === false, 'isValidEpoch(undefined)')
assert(f.isValidEpoch(Number.NaN) === false, 'isValidEpoch(NaN)')
assert(f.isValidEpoch(Number.POSITIVE_INFINITY) === false, 'isValidEpoch(Infinity)')

const ts1 = 1700000000 // 2023-11-15T02:13:20Z
assert(f.formatEpoch(undefined) === '—', 'formatEpoch 无效输入 → fallback')
assert(f.formatEpoch(ts1).includes('2023') === true, 'formatEpoch 输出含年份 2023')
assert(f.formatEpoch(ts1) === new Date(ts1 * 1000).toLocaleString(), 'formatEpoch === toLocaleString 基准')
assert(f.formatEpoch(ts1, 'n/a') === new Date(ts1 * 1000).toLocaleString(), 'formatEpoch 自定义 fallback 不影响有效输入')

assert(f.formatEpochDate(ts1) === new Date(ts1 * 1000).toLocaleDateString(), 'formatEpochDate === toLocaleDateString')

assert(f.formatDuration(0) === '0秒', 'formatDuration(0)')
assert(f.formatDuration(30) === '30秒', 'formatDuration(30)')
assert(f.formatDuration(65) === '1分钟', 'formatDuration(65)')
assert(f.formatDuration(3600) === '1小时', 'formatDuration(3600)')
assert(f.formatDuration(90061) === '1天 1小时 1分钟', 'formatDuration(90061)')
assert(f.formatDuration(undefined) === '—', 'formatDuration(undefined) → fallback')

assert(f.formatFileSize(0) === '0 B', 'formatFileSize(0)')
assert(f.formatFileSize(512) === '512 B', 'formatFileSize(512)')
assert(f.formatFileSize(1024) === '1.0 KB', 'formatFileSize(1024)')
assert(f.formatFileSize(1048576) === '1.0 MB', 'formatFileSize(1048576)')
assert(f.formatFileSize(1073741824) === '1.0 GB', 'formatFileSize(1073741824)')
assert(f.formatFileSize(-1) === '—', 'formatFileSize(-1) → fallback')

if (failures) {
  console.error(`\n${failures} 个断言失败`)
  process.exit(1)
}
console.log('\n全部通过')