import fs from 'node:fs'
import path from 'node:path'
import { parse, babelParse } from 'vue/compiler-sfc'

export const displayAttributes = new Set(['title', 'label', 'placeholder', 'aria-label', 'description', 'help', 'confirm-text', 'cancel-text', 'retry-label', 'kicker', 'lead', 'empty-text'])
const displayProperties = /^(?:label|title|description|placeholder|tooltip|help|hint|message|text|caption|emptyText|reason|summary|subtitle|lead|kicker|name)$/
const technical = new Set(['Trinity', 'Claude', 'Claude Code', 'Gemini', 'Gemini CLI', 'OpenAI', 'Codex', 'Anthropic', 'Google', 'GitHub', 'Git', 'Slack', 'Telegram', 'WhatsApp', 'ElevenLabs', 'Nevermined', 'Google AI Studio', 'Auth0', 'Mermaid', 'Markdown', 'JSON', 'YAML', 'HTML', 'TypeScript', 'JavaScript', 'Python', 'English', '简体中文', 'UTC', 'Docker', 'Redis', 'SQLite', 'PostgreSQL', 'Linux', 'macOS', 'Windows', 'Codex CLI', 'Bash', 'Grep', 'Glob', 'WebSearch', 'WebFetch', 'TodoWrite'])
export function isHumanCopy(value) {
  const s = value.replace(/\s+/g, ' ').trim()
  if (!/[a-zA-Z]{2}/.test(s.replace(/\{\w+\}/g, '')) || technical.has(s)) return false
  if (/^(?:\.env|\.mcp\.json\.template)$/.test(s)) return false
  if (s.split(/\s+/).every(token => /^(?:[\w-]+:)*(?:[\w]+-[\w/-]+|flex|grid|block|hidden)$/.test(token))) return false
  if (/^(?:sk-|ghp_|github_pat_|https?:|wss?:|mailto:|\/|\.\/|~\/|[\w.+-]+@[\w.-]+\.[a-z]+$)/i.test(s)) return false
  if (/^(?:[A-Z][A-Z_\d:+/ -]*|[\w.-]+\.(?:json|md|yaml|yml|js|py|txt|sh|com|ai|env)|[a-z\d]+(?:[-_][a-z\d]+)+|[\w-]+\/[^\s]+)$/.test(s)) return false
  if (/^(?:#|--|\$ |git |npm |pip |curl |ssh |docker |chmod |export |const |import |\{\s*"|\[\s*\{|<\w|[A-Z_]+=)/.test(s)) return false
  if (/^(?:[\w-]+:)?(?:bg-|text-|border-|px-|py-|pl-|pr-|mr-|ml-|w-|h-|max-|min-|flex|grid|items-|justify-|rounded|font-|opacity-|overflow-|whitespace-|cursor-|transition|inline-|block|hidden|relative|absolute)/.test(s) && !/[A-Z]/.test(s)) return false
  if (/^(?:white-space:|color:|background:|display:|font-size:)/.test(s) || /\x1b\[/.test(s)) return false
  if (/^[a-z_]+_\{arg\d+\}$/.test(s)) return false
  return true
}
const normalize = s => s.replace(/\s+/g, ' ').trim()
export function jsWalk(node, fn, parents = []) {
  if (!node || typeof node !== 'object') return
  if (node.type) fn(node, parents)
  for (const [key, value] of Object.entries(node)) {
    if (['loc', 'start', 'end', 'comments', 'tokens', 'leadingComments', 'trailingComments', 'innerComments', 'extra'].includes(key)) continue
    if (Array.isArray(value)) value.forEach(v => jsWalk(v, fn, [...parents, node]))
    else if (value && typeof value === 'object') jsWalk(value, fn, [...parents, node])
  }
}
function messageOf(node) {
  if (node.type === 'StringLiteral') return node.value
  if (node.type === 'TemplateLiteral') return node.quasis.map((q, i) => q.value.cooked + (i < node.expressions.length ? `{arg${i + 1}}` : '')).join('')
  return null
}
function called(node) { return node?.type === 'CallExpression' && node.callee.type === 'Identifier' ? node.callee.name : '' }
function keyOf(node) { return node?.key?.name || node?.key?.value || '' }
function translatedCall(node) { return ['t', 'translate', 'uiText', 'msg'].includes(called(node)) }
function descendants(node, fn) { jsWalk(node, fn) }

export function scanSource(source, filename, catalog) {
  const records = []
  const add = (message, start, end, kind, translated = false, extra = {}) => {
    if (!isHumanCopy(message)) return
    const key = kind === 'text' || kind === 'attribute' ? normalize(message) : message
    records.push({ file: filename, line: source.slice(0, start).split('\n').length, start, end, kind, message: key,
      localized: translated && Object.hasOwn(catalog, key), wired: translated, ...extra })
  }
  const isVue = filename.endsWith('.vue')
  const parsed = isVue ? parse(source, { filename }) : null
  if (parsed?.errors.length) throw new Error(`${filename}: ${parsed.errors.join('; ')}`)
  const descriptor = parsed?.descriptor
  
  const scripts = isVue ? [descriptor.script, descriptor.scriptSetup].filter(Boolean) : [{ content: source, loc: { start: { offset: 0 } } }]
  function exprScan(content, base, kind, attribute = false, raw = content) {
    // Vue decodes HTML entities before parsing expressions. Babel offsets refer
    // to that decoded text, whereas edits/diagnostics refer to the source file.
    const at = index => {
      let r = 0, d = 0
      while (d < index && r < raw.length) {
        const entity = raw.slice(r).match(/^&(?:#x[\da-f]+|#\d+|[a-z]+);/i)
        if (entity && raw[r] !== content[d + 1]) {
          const v = entity[0]
          const code = v.startsWith('&#x') ? parseInt(v.slice(3), 16) : v.startsWith('&#') ? parseInt(v.slice(2), 10) : 0
          r += v.length; d += code > 65535 ? 2 : 1
        } else { r++; d++ }
      }
      return base + r
    }
    let ast
    try { ast = babelParse(`(${content})`, { sourceType: 'module' }).program.body[0].expression } catch (e) { throw new Error(`${filename}: invalid UI expression: ${e.message}`) }
    function outputs(n) {
      if (!n) return
      if (translatedCall(n)) {
        const msg = messageOf(n.arguments[0] || {})
        if (msg !== null) add(msg, at(n.start - 1), at(n.end - 1), kind, true, { expression: true, attribute })
        return
      }
      const message = messageOf(n)
      if (message !== null) {
        add(message, at(n.start - 1), at(n.end - 1), kind, false, { expression: true, attribute, templateLiteral: n.type === 'TemplateLiteral', expressions: (n.expressions || []).map(e => content.slice(e.start - 1, e.end - 1)) })
        return
      }
      if (n.type === 'ConditionalExpression') { outputs(n.consequent); outputs(n.alternate) }
      else if (n.type === 'LogicalExpression' || n.type === 'BinaryExpression' && n.operator === '+') { outputs(n.left); outputs(n.right) }
      else if (n.type === 'CallExpression') {
        // Account for interpolation inside formatters and array render callbacks.
        for (const arg of n.arguments) if (arg.type === 'ArrowFunctionExpression') descendants(arg.body, child => { if (translatedCall(child)) outputs(child) })
      }
    }
    outputs(ast)
  }
  if (descriptor?.template) {
    const block = descriptor.template
    const offset = 0 // SFC template AST locations are absolute in the source.
    function visit(n, skip = false) {
      skip ||= ['code', 'pre', 'script', 'style'].includes(n.tag)
      if (skip) return
      if (n.type === 2) add(n.content, offset + n.loc.start.offset, offset + n.loc.end.offset, 'text')
      if (n.type === 5) exprScan(n.content.content, offset + n.content.loc.start.offset, 'expression', false, n.content.loc.source)
      for (const p of n.props || []) {
        if (p.type === 6 && displayAttributes.has(p.name) && p.value) add(p.value.content, offset + p.loc.start.offset, offset + p.loc.end.offset, 'attribute', false, { attributeName: p.name })
        if (p.type === 7 && p.name === 'bind' && displayAttributes.has(p.arg?.content) && p.exp) exprScan(p.exp.content, offset + p.exp.loc.start.offset, 'expression', true, p.exp.loc.source)
      }
      for (const child of n.children || []) visit(child)
    }
    visit(block.ast)
  }
  for (const block of scripts) {
    const offset = block.loc.start.offset
    let ast
    try { ast = babelParse(block.content, { sourceType: 'module', plugins: ['typescript'] }) } catch (e) { throw new Error(`${filename}: ${e.message}`) }
    jsWalk(ast, (n, parents) => {
      if (translatedCall(n)) {
        const message = messageOf(n.arguments[0] || {})
        if (message !== null) add(message, offset + n.start, offset + n.end, 'script', true)
      }
      const message = messageOf(n)
      if (message === null || !isHumanCopy(message)) return
      if (parents.some(p => translatedCall(p))) return
      const parent = parents.at(-1)
      if (['ObjectProperty', 'ObjectMethod'].includes(parent?.type) && parent.key === n || parents.some(p => ['ImportDeclaration', 'ExportNamedDeclaration'].includes(p.type) && p.source === n)) return
      // Machine comparisons/regex, logging and exceptions are diagnostics rather
      // than UI copy. User-facing caught errors are included at the UI fallback.
      if (parents.some(p => p.type === 'BinaryExpression' && p.operator !== '+' || p.type === 'SwitchCase' && p.test === n)) return
      if (parents.some(p => p.type === 'CallExpression' && p.callee.type === 'MemberExpression' && p.callee.object.name === 'console')) return
      if (parent?.type === 'ObjectProperty' && keyOf(parent) === 'type') return
      if (parents.some(p => p.type === 'NewExpression' && p.callee.name === 'Error')) return
      if (parents.some(p => p.type === 'ObjectProperty' && /^(?:class|className|style|url|path|endpoint|pattern|prompt|systemPrompt|starter_prompt|command|code|value|id|key|type|icon|color|variant|status|method|headers|role|source|notification_type|priority|event|trigger)$/.test(keyOf(p)))) return
      // Context must not leak from an outer ref/assignment into a callback or
      // an arbitrary API call. Only display properties and direct UI expression
      // branches qualify; event names, roles and helper codes stay untouched.
      const boundary = parents.findLastIndex(p => /Function|Method/.test(p.type))
      const localParents = parents.slice(boundary + 1)
      const propertyParent = [...localParents].reverse().find(p => p.type === 'ObjectProperty')
      if (propertyParent && !displayProperties.test(keyOf(propertyParent))) return
      if (propertyParent && keyOf(propertyParent) === 'name') return
      if (propertyParent && /^(?:reason|hint)$/.test(keyOf(propertyParent)) && /^[a-z]+$/.test(message)) return
      const nearestCall = [...localParents].reverse().find(p => p.type === 'CallExpression')
      const callName = nearestCall && (nearestCall.callee.name || nearestCall.callee.property?.name)
      if (nearestCall && !/^(?:ref|computed|showNotification|showError|showSuccess|notify|alert|confirm|apiErrorMessage|describeAvatarError|staleBannerMessage)$/.test(callName || '')) return
      const fn = parents[boundary]
      if (/Class|Style|Pattern|Regex/.test(fn?.id?.name || fn?.key?.name || '')) return
      let display = false, property = null
      if (parent?.type === 'ObjectProperty' && parent.value === n && displayProperties.test(keyOf(parent))) { display = true; property = parent }
      if (property && keyOf(property) === 'name' && (filename.startsWith('router/') || /^[A-Z][a-z]+[A-Z]/.test(message) || /^(?:[a-z]+[_-])+[a-z]+$/.test(message))) return
      if (parents.some(p => p.type === 'CallExpression' && p.callee.type === 'MemberExpression' && /^(?:includes|startsWith|endsWith|split|replace|replaceAll|match|test|querySelector|querySelectorAll|createElement|setAttribute|addEventListener|removeEventListener)$/.test(p.callee.property.name))) return
      const callParent = [...parents].reverse().find(p => p.type === 'CallExpression')
      if (callParent && /^(?:showNotification|showError|showSuccess|notify)$/.test(called(callParent)) && callParent.arguments.indexOf(n) > 0) return
      // Local UI error/notice refs and imperative toast/confirm APIs.
      const owner = [...localParents].reverse().find(p => ['VariableDeclarator', 'AssignmentExpression'].includes(p.type))
      const context = owner?.type === 'VariableDeclarator' ? owner.id?.name || '' : owner ? block.content.slice(owner.left.start, owner.left.end) : ''
      if (/error|message|notice|tooltip|placeholder|label|title|subtitle|hint|description|reason|emptyText/i.test(context) && !/Type|Code|Class|Style|Status|Pattern|Regex|Key|Id|Token|Url/i.test(context)) display = true
      if (parents.some(p => p.type === 'CallExpression' && /^(?:showNotification|showError|showSuccess|notify|alert|confirm)$/.test(called(p)))) display = true
      // Remaining prose returned by UI formatting helpers; opaque status ids
      // are only included in the explicit display metadata above.
      if (localParents.some(p => p.type === 'ReturnStatement') && /\b[A-Za-z]+\s+[a-zA-Z]+\b/.test(message)) display = true
      if (!display) return
      if (parents.some(p => p.type === 'TemplateLiteral' && p !== n)) return
      add(message, offset + n.start, offset + n.end, 'script', false, { templateLiteral: n.type === 'TemplateLiteral', expressions: (n.expressions || []).map(e => block.content.slice(e.start, e.end)), propertyStart: property ? offset + property.start : undefined, propertyEnd: property ? offset + property.end : undefined, propertyName: property && keyOf(property), deferred: parents.some(p => /Function|Method/.test(p.type)) })
    })
  }
  // A source message can be recorded only once, even in nested expressions.
  return [...new Map(records.map(r => [`${r.start}:${r.end}`, r])).values()]
}
export function scanTree(root, catalog) {
  const files = []
  function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name === 'i18n' || entry.name === 'node_modules') continue
      const file = path.join(dir, entry.name)
      if (entry.isDirectory()) walk(file)
      else if (/\.(vue|js)$/.test(file)) files.push(file)
    }
  }
  walk(root)
  // Generated files are byte-compared with their generator; translate their copy where it renders.
  const generated = source => /^\/\/ GENERATED by .*DO NOT EDIT/m.test(source)
  return files.sort().flatMap(file => {
    const source = fs.readFileSync(file, 'utf8')
    return generated(source) ? [] : scanSource(source, path.relative(root, file), catalog)
  })
}
export function summary(records) {
  const total = records.length, localized = records.filter(r => r.localized).length
  return { total, localized, missing: total - localized, percent: total ? +(localized / total * 100).toFixed(2) : 100 }
}
