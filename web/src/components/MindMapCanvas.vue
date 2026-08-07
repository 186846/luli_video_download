<script setup>
/**
 * NoteGPT 风格思维导图：
 * 横向展开 · 点阵画布 · 彩色圆角节点 · 贝塞尔连线 ·
 * 缩放/拖拽/折叠 · 页内全屏 · 导出 PNG / FreeMind / OPML / SVG
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { safeFilename } from '../utils/exportFile'
import {
  downloadBlob,
  downloadFreeMind,
  downloadOpml,
  svgToPngBlob,
} from '../utils/mindMapExport'

const props = defineProps({
  root: { type: Object, required: true },
})

const H_GAP = 64
const V_GAP = 16
const PAD = 72

const BRANCH = [
  { fill: '#E8F1FF', border: '#4B8BFF', text: '#1e3a8a', line: '#7BA7FF' },
  { fill: '#E8F8EF', border: '#34B36F', text: '#14532d', line: '#6BCF95' },
  { fill: '#FFF3E6', border: '#F59E0B', text: '#78350f', line: '#FBBF24' },
  { fill: '#F3E8FF', border: '#A855F7', text: '#581c87', line: '#C084FC' },
  { fill: '#FFE8EE', border: '#F43F5E', text: '#881337', line: '#FB7185' },
  { fill: '#E6FAF8', border: '#14B8A6', text: '#134e4a', line: '#5EEAD4' },
  { fill: '#EEF0FF', border: '#6366F1', text: '#312e81', line: '#A5B4FC' },
  { fill: '#FFF8E6', border: '#EAB308', text: '#713f12', line: '#FACC15' },
]

const viewportRef = ref(null)
const rootEl = ref(null)
const scale = ref(1)
const offset = ref({ x: 40, y: 40 })
const collapsed = ref(new Set())
const dragging = ref(false)
const dragStart = ref({ x: 0, y: 0, ox: 0, oy: 0 })
const layoutTick = ref(0)
const isFullscreen = ref(false)
const exportOpen = ref(false)
const exportBusy = ref(false)
const exportMsg = ref('')

const ROOT_STYLE = {
  fill: '#1777ff',
  border: '#0d66e8',
  text: '#ffffff',
  line: '#93c5fd',
}

function charWidth(ch, fs) {
  if (/[\u4e00-\u9fff\u3400-\u4dbf]/.test(ch)) return fs
  if (/[A-Z0-9]/.test(ch)) return fs * 0.62
  return fs * 0.52
}

function measureNode(name, depth) {
  const maxW = [248, 200, 176, 156][Math.min(depth, 3)]
  const fs = [15, 13, 12, 11][Math.min(depth, 3)]
  const padX = depth === 0 ? 22 : 14
  const padY = depth === 0 ? 14 : 9
  const lineH = fs * 1.45
  const contentMax = maxW - padX * 2
  const lines = []
  let cur = ''
  let curW = 0
  for (const ch of String(name || '未命名')) {
    const cw = charWidth(ch, fs)
    if (curW + cw > contentMax && cur) {
      lines.push(cur)
      cur = ch
      curW = cw
    } else {
      cur += ch
      curW += cw
    }
  }
  if (cur) lines.push(cur)
  const textW = Math.max(
    ...lines.map((l) => [...l].reduce((s, c) => s + charWidth(c, fs), 0)),
    48,
  )
  return {
    w: Math.min(maxW, Math.ceil(textW + padX * 2)),
    h: Math.max(Math.ceil(lineH + padY * 2), Math.ceil(lines.length * lineH + padY * 2)),
    lines,
    fs,
    padX,
    padY,
    lineH,
  }
}

function pathKey(path) {
  return path.join('.')
}

/** @param {boolean} respectCollapse 为 false 时导出完整树 */
function cloneTree(node, path = [], respectCollapse = true) {
  const key = pathKey(path)
  const kids = Array.isArray(node?.children) ? node.children : []
  const isCollapsed =
    respectCollapse && collapsed.value.has(key) && kids.length > 0
  return {
    name: String(node?.name || '未命名'),
    path: [...path],
    key,
    hasKids: kids.length > 0,
    collapsed: isCollapsed,
    children: isCollapsed
      ? []
      : kids.map((c, i) => cloneTree(c, [...path, i], respectCollapse)),
    rawChildren: kids.length,
  }
}

function layoutTree(node, depth, branchIndex) {
  const size = measureNode(node.name, depth)
  Object.assign(node, size, { depth, branchIndex })
  const kids = node.children || []
  if (!kids.length) {
    node.subH = node.h
    return node
  }
  kids.forEach((c, i) => layoutTree(c, depth + 1, depth === 0 ? i : branchIndex))
  const kidsH = kids.reduce((s, c) => s + c.subH, 0) + V_GAP * (kids.length - 1)
  node.subH = Math.max(node.h, kidsH)
  return node
}

function assignPos(node, x, yTop) {
  node.x = x
  node.y = yTop + node.subH / 2 - node.h / 2
  const kids = node.children || []
  let cy = yTop
  const kidsH = kids.reduce((s, c) => s + c.subH, 0) + Math.max(0, kids.length - 1) * V_GAP
  if (kids.length && kidsH < node.subH) {
    cy = yTop + (node.subH - kidsH) / 2
  }
  for (const c of kids) {
    assignPos(c, x + node.w + H_GAP, cy)
    cy += c.subH + V_GAP
  }
}

function flatten(node, list = [], links = []) {
  list.push(node)
  for (const c of node.children || []) {
    links.push({
      from: node,
      to: c,
      color: BRANCH[c.branchIndex % BRANCH.length].line,
    })
    flatten(c, list, links)
  }
  return { nodes: list, links }
}

function buildModel(respectCollapse) {
  if (!props.root) return null
  const tree = cloneTree(props.root, [], respectCollapse)
  layoutTree(tree, 0, 0)
  assignPos(tree, PAD, PAD)
  const { nodes, links } = flatten(tree)
  const maxX = Math.max(...nodes.map((n) => n.x + n.w), 400)
  const maxY = Math.max(...nodes.map((n) => n.y + n.h), 300)
  return {
    nodes,
    links,
    width: maxX + PAD,
    height: maxY + PAD,
  }
}

const treeModel = computed(() => {
  layoutTick.value
  return buildModel(true)
})

const transformStyle = computed(() => ({
  transform: `translate(${offset.value.x}px, ${offset.value.y}px) scale(${scale.value})`,
  transformOrigin: '0 0',
}))

const zoomLabel = computed(() => `${Math.round(scale.value * 100)}%`)

function nodeStyle(n) {
  if (n.depth === 0) return ROOT_STYLE
  return BRANCH[n.branchIndex % BRANCH.length]
}

function linkPath(link) {
  const a = link.from
  const b = link.to
  const x1 = a.x + a.w
  const y1 = a.y + a.h / 2
  const x2 = b.x
  const y2 = b.y + b.h / 2
  const dx = Math.max(36, (x2 - x1) * 0.45)
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`
}

function toggle(node) {
  if (!node.hasKids) return
  const next = new Set(collapsed.value)
  if (next.has(node.key)) next.delete(node.key)
  else next.add(node.key)
  collapsed.value = next
  layoutTick.value += 1
}

function zoomBy(delta) {
  const next = Math.min(2.2, Math.max(0.35, scale.value + delta))
  scale.value = Math.round(next * 100) / 100
}

function fitView() {
  const el = viewportRef.value
  const model = treeModel.value
  if (!el || !model) return
  const vw = el.clientWidth
  const vh = el.clientHeight
  if (vw <= 0 || vh <= 0) return
  const sx = (vw - 48) / model.width
  const sy = (vh - 48) / model.height
  const s = Math.min(1.05, Math.max(0.35, Math.min(sx, sy)))
  scale.value = Math.round(s * 100) / 100
  offset.value = {
    x: Math.max(16, (vw - model.width * scale.value) / 2),
    y: Math.max(16, (vh - model.height * scale.value) / 2),
  }
}

function resetView() {
  scale.value = 1
  offset.value = { x: 40, y: 40 }
  nextTick(fitView)
}

function expandAll() {
  collapsed.value = new Set()
  layoutTick.value += 1
  nextTick(fitView)
}

function collapseBranches() {
  const rootKids = props.root?.children || []
  const next = new Set()
  rootKids.forEach((_, i) => next.add(String(i)))
  collapsed.value = next
  layoutTick.value += 1
  nextTick(fitView)
}

function setBodyScrollLock(lock) {
  document.body.style.overflow = lock ? 'hidden' : ''
}

function enterFullscreen() {
  isFullscreen.value = true
  exportOpen.value = false
  setBodyScrollLock(true)
  nextTick(() => {
    fitView()
  })
}

function exitFullscreen() {
  if (!isFullscreen.value) return
  isFullscreen.value = false
  setBodyScrollLock(false)
  nextTick(fitView)
}

function toggleFullscreen() {
  if (isFullscreen.value) exitFullscreen()
  else enterFullscreen()
}

function onKeydown(e) {
  if (e.key === 'Escape') {
    if (exportOpen.value) {
      exportOpen.value = false
      return
    }
    if (isFullscreen.value) {
      e.preventDefault()
      exitFullscreen()
    }
  }
}

function onDocPointerDown(e) {
  if (!exportOpen.value) return
  if (rootEl.value?.contains(e.target)) {
    if (e.target?.closest?.('.mmc-export')) return
  }
  exportOpen.value = false
}

function onWheel(e) {
  e.preventDefault()
  const dir = e.deltaY > 0 ? -0.08 : 0.08
  zoomBy(dir)
}

function onPointerDown(e) {
  if (e.button !== 0) return
  if (e.target?.closest?.('.mmc-node')) return
  dragging.value = true
  dragStart.value = {
    x: e.clientX,
    y: e.clientY,
    ox: offset.value.x,
    oy: offset.value.y,
  }
  e.currentTarget.setPointerCapture?.(e.pointerId)
}

function onPointerMove(e) {
  if (!dragging.value) return
  offset.value = {
    x: dragStart.value.ox + (e.clientX - dragStart.value.x),
    y: dragStart.value.oy + (e.clientY - dragStart.value.y),
  }
}

function onPointerUp() {
  dragging.value = false
}

function escapeSvgText(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** 完整展开树的 SVG（导出用，不受折叠影响） */
function buildFullSvg() {
  const model = buildModel(false)
  if (!model) return null

  const links = model.links
    .map((l) => {
      const color = l.color
      return `<path d="${linkPath(l)}" fill="none" stroke="${color}" stroke-width="2.2" stroke-linecap="round"/>`
    })
    .join('')

  const nodes = model.nodes
    .map((n) => {
      const st = nodeStyle(n)
      const r = n.depth === 0 ? 14 : 10
      const texts = n.lines
        .map((line, i) => {
          const ty = n.padY + n.fs * 0.9 + i * n.lineH
          return `<text x="${n.padX}" y="${ty}" fill="${st.text}" font-size="${n.fs}" font-family="system-ui, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif">${escapeSvgText(line)}</text>`
        })
        .join('')
      return `<g transform="translate(${n.x},${n.y})">
        <rect width="${n.w}" height="${n.h}" rx="${r}" ry="${r}" fill="${st.fill}" stroke="${st.border}" stroke-width="${n.depth === 0 ? 0 : 1.5}"/>
        ${texts}
      </g>`
    })
    .join('')

  const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${model.width}" height="${model.height}" viewBox="0 0 ${model.width} ${model.height}">
  <rect width="100%" height="100%" fill="#f7f8fa"/>
  ${links}
  ${nodes}
</svg>`
  return { svg, model }
}

function fileBase() {
  return String(props.root?.name || 'mindmap').slice(0, 40)
}

function exportSvg() {
  exportOpen.value = false
  const built = buildFullSvg()
  if (!built) return
  downloadBlob(
    safeFilename(fileBase(), 'svg'),
    new Blob([built.svg], { type: 'image/svg+xml;charset=utf-8' }),
  )
  exportMsg.value = '已下载 SVG'
  clearExportMsgSoon()
}

async function exportPng() {
  exportOpen.value = false
  if (exportBusy.value) return
  const built = buildFullSvg()
  if (!built) return
  exportBusy.value = true
  exportMsg.value = '正在生成高清 PNG…'
  try {
    const blob = await svgToPngBlob(built.svg, {
      width: built.model.width,
      height: built.model.height,
      scale: 2,
    })
    downloadBlob(safeFilename(fileBase(), 'png'), blob)
    exportMsg.value = '已下载 PNG（2x）'
  } catch (err) {
    exportMsg.value = err?.message || 'PNG 导出失败'
  } finally {
    exportBusy.value = false
    clearExportMsgSoon()
  }
}

function exportMm() {
  exportOpen.value = false
  downloadFreeMind(props.root)
  exportMsg.value = '已下载 FreeMind（.mm）'
  clearExportMsgSoon()
}

function exportOpml() {
  exportOpen.value = false
  downloadOpml(props.root)
  exportMsg.value = '已下载 OPML'
  clearExportMsgSoon()
}

let msgTimer = null
function clearExportMsgSoon() {
  if (msgTimer) clearTimeout(msgTimer)
  msgTimer = setTimeout(() => {
    exportMsg.value = ''
    msgTimer = null
  }, 2800)
}

watch(isFullscreen, () => {
  nextTick(() => {
    const el = viewportRef.value
    if (el && resizeObserver) {
      try {
        resizeObserver.disconnect()
        resizeObserver.observe(el)
      } catch {
        /* ignore */
      }
    }
    fitView()
  })
})

watch(
  () => props.root,
  () => {
    collapsed.value = new Set()
    layoutTick.value += 1
    nextTick(fitView)
  },
  { deep: true },
)

let resizeObserver = null

onMounted(() => {
  nextTick(fitView)
  window.addEventListener('resize', fitView)
  window.addEventListener('keydown', onKeydown)
  document.addEventListener('pointerdown', onDocPointerDown, true)
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      const el = viewportRef.value
      if (el && el.clientWidth > 0 && el.clientHeight > 0) fitView()
    })
    if (viewportRef.value) resizeObserver.observe(viewportRef.value)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', fitView)
  window.removeEventListener('keydown', onKeydown)
  document.removeEventListener('pointerdown', onDocPointerDown, true)
  resizeObserver?.disconnect()
  resizeObserver = null
  setBodyScrollLock(false)
  if (msgTimer) clearTimeout(msgTimer)
})
</script>

<template>
  <Teleport to="body" :disabled="!isFullscreen">
    <div ref="rootEl" class="mmc" :class="{ 'is-fullscreen': isFullscreen }">
      <div class="mmc-toolbar">
        <button type="button" class="mmc-btn" title="缩小" @click="zoomBy(-0.1)">−</button>
        <span class="mmc-zoom">{{ zoomLabel }}</span>
        <button type="button" class="mmc-btn" title="放大" @click="zoomBy(0.1)">+</button>
        <span class="mmc-sep" />
        <button type="button" class="mmc-btn" title="适应画布" @click="fitView">适应</button>
        <button type="button" class="mmc-btn" title="重置" @click="resetView">重置</button>
        <span class="mmc-sep" />
        <button type="button" class="mmc-btn" title="展开全部" @click="expandAll">展开</button>
        <button type="button" class="mmc-btn" title="折叠一级分支" @click="collapseBranches">折叠</button>
        <span class="mmc-sep" />
        <button
          type="button"
          class="mmc-btn"
          :title="isFullscreen ? '退出全屏 (Esc)' : '全屏阅读'"
          @click="toggleFullscreen"
        >
          {{ isFullscreen ? '退出全屏' : '全屏' }}
        </button>
        <div class="mmc-export">
          <button
            type="button"
            class="mmc-btn mmc-btn--primary"
            :disabled="exportBusy"
            title="导出导图"
            @click="exportOpen = !exportOpen"
          >
            {{ exportBusy ? '导出中…' : '导出' }}
          </button>
          <div v-if="exportOpen" class="mmc-export-menu" role="menu">
            <button type="button" role="menuitem" @click="exportPng">高清 PNG（2x）</button>
            <button type="button" role="menuitem" @click="exportMm">FreeMind（.mm）</button>
            <button type="button" role="menuitem" @click="exportOpml">OPML（.opml）</button>
            <button type="button" role="menuitem" @click="exportSvg">矢量 SVG</button>
          </div>
        </div>
        <span v-if="exportMsg" class="mmc-export-msg">{{ exportMsg }}</span>
      </div>

      <div
        ref="viewportRef"
        class="mmc-viewport"
        :class="{ 'is-dragging': dragging }"
        @wheel.prevent="onWheel"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
      >
        <div class="mmc-stage" :style="transformStyle">
          <svg
            v-if="treeModel"
            class="mmc-links"
            :width="treeModel.width"
            :height="treeModel.height"
          >
            <path
              v-for="(l, i) in treeModel.links"
              :key="i"
              class="mmc-link"
              :d="linkPath(l)"
              :stroke="l.color"
            />
          </svg>

          <div
            v-for="n in treeModel?.nodes || []"
            :key="n.key"
            class="mmc-node"
            :class="[
              `mmc-node--lv${Math.min(n.depth, 3)}`,
              { 'mmc-node--root': n.depth === 0, 'mmc-node--foldable': n.hasKids },
            ]"
            :style="{
              left: `${n.x}px`,
              top: `${n.y}px`,
              width: `${n.w}px`,
              minHeight: `${n.h}px`,
              '--mmc-fill': nodeStyle(n).fill,
              '--mmc-border': nodeStyle(n).border,
              '--mmc-text': nodeStyle(n).text,
              fontSize: `${n.fs}px`,
            }"
            @click.stop="toggle(n)"
          >
            <span class="mmc-node-text">
              <span v-for="(line, li) in n.lines" :key="li" class="mmc-line">{{ line }}</span>
            </span>
            <span v-if="n.hasKids" class="mmc-toggle" :title="n.collapsed ? '展开' : '折叠'">
              {{ n.collapsed ? '+' : '−' }}
            </span>
          </div>
        </div>

        <p class="mmc-hint">
          {{ isFullscreen ? '全屏阅读 · ' : '' }}拖拽画布 · 滚轮缩放 · 点击节点折叠
          <template v-if="isFullscreen"> · Esc 退出</template>
        </p>
      </div>
    </div>
  </Teleport>
</template>
