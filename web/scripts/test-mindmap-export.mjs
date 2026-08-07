/**
 * 思维导图导出单元自测（Node，无浏览器依赖）。
 * 运行：node web/scripts/test-mindmap-export.mjs
 */
import assert from 'node:assert/strict'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const exportPath = join(__dirname, '../src/utils/mindMapExport.js')

const {
  escapeXmlAttr,
  normalizeNode,
  toFreeMindXml,
  toOpmlXml,
} = await import(pathToFileURL(exportPath).href)

const sample = {
  name: '测试视频 <标题> & "引号"',
  children: [
    {
      name: '核心要点',
      children: [{ name: '要点A', children: [{ name: '细节1', children: [] }] }],
    },
    { name: '章节详解', children: [{ name: '00:01 开场', children: [] }] },
  ],
}

assert.equal(escapeXmlAttr(`a&b<"'>`), 'a&amp;b&lt;&quot;&apos;&gt;')

const norm = normalizeNode({ name: '  ', children: ['叶子'] })
assert.equal(norm.name, '未命名')
assert.equal(norm.children[0].name, '叶子')

const mm = toFreeMindXml(sample)
assert.match(mm, /<\?xml version="1.0" encoding="UTF-8"\?>/)
assert.match(mm, /<map version="1.0.1">/)
assert.match(mm, /TEXT="测试视频 &lt;标题&gt; &amp; &quot;引号&quot;"/)
assert.match(mm, /TEXT="核心要点"/)
assert.match(mm, /TEXT="细节1"/)
assert.match(mm, /<\/map>/)

const opml = toOpmlXml(sample)
assert.match(opml, /<opml version="2.0">/)
assert.match(opml, /<title>测试视频 &lt;标题&gt; &amp; &quot;引号&quot;<\/title>/)
assert.match(opml, /text="章节详解"/)
assert.match(opml, /<\/opml>/)

const empty = toFreeMindXml(null)
assert.match(empty, /TEXT="视频大纲"/)

console.log('mindMapExport self-test OK')
console.log('--- FreeMind sample (truncated) ---')
console.log(mm.slice(0, 280) + '...')
console.log('--- OPML sample (truncated) ---')
console.log(opml.slice(0, 280) + '...')
