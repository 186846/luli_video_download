/**
 * SRT/VTT 导出自测。运行：node web/scripts/test-subtitle-export.mjs
 */
import assert from 'node:assert/strict'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const mod = await import(pathToFileURL(join(__dirname, '../src/utils/exportFile.js')).href)

const cues = [
  { start: '00:01', text: '第一句' },
  { start: '00:05', end: '00:07', text: '第二句' },
  { start: '1:02:03', text: '第三句' },
]

assert.equal(mod.timestampToSeconds('00:01'), 1)
assert.equal(mod.timestampToSeconds('1:02:03'), 3723)
assert.equal(mod.formatSrtTime(1.5), '00:00:01,500')
assert.equal(mod.formatVttTime(1.5), '00:00:01.500')

const srt = mod.toSrt(cues)
assert.match(srt, /^1\n00:00:01,000 --> 00:00:05,000\n第一句\n/)
assert.match(srt, /2\n00:00:05,000 --> 00:00:07,000\n第二句\n/)
assert.match(srt, /3\n01:02:03,000 --> 01:02:06,000\n第三句\n/)

const vtt = mod.toVtt(cues)
assert.match(vtt, /^WEBVTT\n/)
assert.match(vtt, /00:00:01\.000 --> 00:00:05\.000\n第一句\n/)
assert.match(vtt, /00:00:05\.000 --> 00:00:07\.000\n第二句\n/)

assert.equal(mod.toSrt([]), '')
assert.equal(mod.toVtt([]), 'WEBVTT\n')

console.log('subtitle export self-test OK')
console.log('--- SRT ---\n' + srt)
console.log('--- VTT ---\n' + vtt)
