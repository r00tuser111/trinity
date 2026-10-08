import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { scanTree, summary } from './i18n-audit.mjs'
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../src')
const catalog = JSON.parse(fs.readFileSync(path.join(root, 'i18n/zh-CN.json'), 'utf8'))
const records = scanTree(root, catalog)
const report = { overall: summary(records), templates: summary(records.filter(r => r.kind !== 'script')), scripts: summary(records.filter(r => r.kind === 'script')), missing: records.filter(r => !r.localized) }
const output = process.argv.indexOf('--json')
if (output !== -1) fs.writeFileSync(process.argv[output + 1], JSON.stringify({ ...report, records }, null, 2) + '\n')
for (const key of ['overall', 'templates', 'scripts']) console.log(`${key}: ${report[key].localized}/${report[key].total} (${report[key].percent}%)`)
if (process.argv.includes('--check') && report.overall.percent < 95) process.exitCode = 1
