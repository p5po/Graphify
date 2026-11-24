"""html — moved verbatim from graphify/export.py."""
from __future__ import annotations

from graphify.exporters.base import COMMUNITY_COLORS  # noqa: E402,F401
from pathlib import Path
import html as _html
from graphify.analyze import _node_community_map
from graphify.paths import write_text_atomic
import json
import networkx as nx
from graphify.security import sanitize_label


MAX_NODES_FOR_VIZ = 5_000
_HTML_STALE_MARKER = ".graph.html.stale"

def _viz_node_limit() -> int:
    """Return the effective viz node limit, honoring GRAPHIFY_VIZ_NODE_LIMIT env var.

    Falls back to MAX_NODES_FOR_VIZ when the env var is unset, empty, or non-integer.
    Set to 0 to disable HTML viz unconditionally (useful for CI runners).
    """
    import os
    raw = os.environ.get("GRAPHIFY_VIZ_NODE_LIMIT")
    if raw is None or not raw.strip():
        return MAX_NODES_FOR_VIZ
    try:
        return int(raw)
    except ValueError:
        return MAX_NODES_FOR_VIZ

def _html_styles() -> str:
    return """<style>
  :root {
    --bg: #0F1115;
    --panel: #16181D;
    --panel-alt: #1C1F26;
    --border: #23272F;
    --border-hover: #374151;
    --input-border: #2D323B;
    --input-focus: #3B82F6;
    --text: #F3F4F6;
    --text-2: #9CA3AF;
    --text-3: #D1D5DB;
    --muted: #6B7280;
    --count: #9CA3AF;
    --accent: #3B82F6;
    --accent-bg: rgba(59, 130, 246, 0.12);
    --neighbor-border: #3B82F6;
    --node-label: #F3F4F6;
    --font-mono: ui-monospace, "JetBrains Mono", "Cascadia Code", "Fira Code", Menlo, Consolas, monospace;
    --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }
  [data-theme="light"] {
    --bg: #F8F9FA;
    --panel: #FFFFFF;
    --panel-alt: #F3F4F6;
    --border: #E5E7EB;
    --border-hover: #D1D5DB;
    --input-border: #D1D5DB;
    --input-focus: #2563EB;
    --text: #111827;
    --text-2: #4B5563;
    --text-3: #1F2937;
    --muted: #9CA3AF;
    --count: #6B7280;
    --accent: #2563EB;
    --accent-bg: rgba(37, 99, 235, 0.08);
    --neighbor-border: #2563EB;
    --node-label: #111827;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font-sans);
    display: flex;
    height: 100vh;
    overflow: hidden;
    -webkit-font-smoothing: antialiased;
  }
  #graph { flex: 1; }
  #sidebar {
    width: 320px;
    background: var(--panel);
    border-left: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  #theme-wrap {
    display: flex;
    gap: 4px;
    padding: 8px 12px;
    border-bottom: 1px solid var(--border);
  }
  #theme-wrap button {
    flex: 1;
    background: var(--bg);
    color: var(--text-2);
    border: 1px solid var(--input-border);
    border-radius: 4px;
    padding: 4px 0;
    font-size: 11px;
    font-family: var(--font-mono);
    cursor: pointer;
    transition: all 0.15s ease;
  }
  #theme-wrap button:hover {
    color: var(--text);
    border-color: var(--border-hover);
  }
  #theme-wrap button[aria-pressed="true"] {
    background: var(--accent);
    border-color: var(--accent);
    color: #ffffff;
    font-weight: 500;
  }
  #search-wrap {
    padding: 12px;
    border-bottom: 1px solid var(--border);
  }
  #search {
    width: 100%;
    background: var(--bg);
    border: 1px solid var(--input-border);
    color: var(--text);
    padding: 7px 10px;
    border-radius: 4px;
    font-size: 12px;
    font-family: var(--font-mono);
    outline: none;
    transition: border-color 0.15s;
  }
  #search:focus {
    border-color: var(--input-focus);
  }
  #search-results {
    max-height: 140px;
    overflow-y: auto;
    padding: 4px 12px;
    border-bottom: 1px solid var(--border);
    display: none;
  }
  .search-item {
    padding: 4px 6px;
    cursor: pointer;
    border-radius: 4px;
    font-size: 11.5px;
    font-family: var(--font-mono);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .search-item:hover {
    background: var(--panel-alt);
    color: var(--accent);
  }
  #info-panel {
    padding: 14px;
    border-bottom: 1px solid var(--border);
    min-height: 140px;
    max-height: 48vh;
    overflow-y: auto;
  }
  #info-panel h3 {
    font-size: 11px;
    color: var(--text-2);
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
  }
  #info-content {
    font-size: 12px;
    color: var(--text-3);
    line-height: 1.5;
  }
  #info-content .empty {
    color: var(--muted);
    font-style: italic;
    font-size: 12px;
  }
  .node-header {
    margin-bottom: 8px;
  }
  .node-title {
    font-family: var(--font-mono);
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
    word-break: break-all;
  }
  .node-meta-grid {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 4px 8px;
    font-size: 11.5px;
    margin: 8px 0;
  }
  .node-meta-key {
    color: var(--text-2);
    font-family: var(--font-mono);
  }
  .node-meta-val {
    color: var(--text);
    font-family: var(--font-mono);
    word-break: break-all;
  }
  .copy-agent-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    padding: 6px 10px;
    margin: 8px 0 4px 0;
    background: var(--panel-alt);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 4px;
    font-family: var(--font-mono);
    font-size: 11.5px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .copy-agent-btn:hover {
    border-color: var(--accent);
    color: var(--accent);
    background: var(--accent-bg);
  }
  .copy-agent-btn.copied {
    background: #059669 !important;
    border-color: #059669 !important;
    color: #ffffff !important;
  }
  .ref-preview {
    font-family: var(--font-mono);
    font-size: 10.5px;
    color: var(--text-2);
    background: var(--bg);
    border: 1px dashed var(--border);
    border-radius: 3px;
    padding: 3px 6px;
    margin-bottom: 8px;
    word-break: break-all;
    user-select: all;
  }
  .conn-section-title {
    margin-top: 10px;
    margin-bottom: 4px;
    color: var(--text-2);
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-weight: 600;
  }
  .neighbor-link {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 3px 6px;
    margin: 2px 0;
    border-radius: 3px;
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 11.5px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    border-left: 2px solid var(--neighbor-border);
    background: var(--bg);
    transition: background 0.1s;
  }
  .neighbor-link:hover {
    background: var(--panel-alt);
  }
  .neighbor-link .conn-badge {
    font-size: 9.5px;
    padding: 1px 4px;
    border-radius: 2px;
    background: var(--panel-alt);
    color: var(--text-2);
    text-transform: uppercase;
  }
  #neighbors-list {
    max-height: 150px;
    overflow-y: auto;
    margin-top: 2px;
  }
  #legend-wrap {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
  }
  #legend-wrap h3 {
    font-size: 11px;
    color: var(--text-2);
    margin-bottom: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
  }
  .legend-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 6px;
    cursor: pointer;
    border-radius: 4px;
    font-size: 12px;
    transition: background 0.1s;
  }
  .legend-item:hover {
    background: var(--panel-alt);
  }
  .legend-item.dimmed {
    opacity: 0.3;
  }
  .legend-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .legend-label {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 12px;
  }
  .legend-count {
    color: var(--count);
    font-size: 11px;
    font-family: var(--font-mono);
  }
  #stats {
    padding: 8px 14px;
    border-top: 1px solid var(--border);
    font-size: 11px;
    font-family: var(--font-mono);
    color: var(--muted);
  }
  #legend-controls {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
    padding: 2px 0;
  }
  #legend-controls label {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    font-size: 11.5px;
    color: var(--text-2);
    user-select: none;
  }
  #legend-controls label:hover {
    color: var(--text);
  }
  .legend-cb, #select-all-cb {
    appearance: none;
    -webkit-appearance: none;
    width: 13px;
    height: 13px;
    border: 1px solid var(--input-border);
    border-radius: 2px;
    background: var(--bg);
    cursor: pointer;
    position: relative;
    flex-shrink: 0;
  }
  .legend-cb:checked, #select-all-cb:checked {
    background: var(--accent);
    border-color: var(--accent);
  }
  .legend-cb:checked::after, #select-all-cb:checked::after {
    content: '';
    position: absolute;
    left: 3.5px;
    top: 1px;
    width: 3.5px;
    height: 6px;
    border: solid #fff;
    border-width: 0 1.5px 1.5px 0;
    transform: rotate(45deg);
  }
  #select-all-cb:indeterminate {
    background: var(--accent);
    border-color: var(--accent);
  }
  #select-all-cb:indeterminate::after {
    content: '';
    position: absolute;
    left: 2px;
    top: 4.5px;
    width: 7px;
    height: 2px;
    background: #fff;
    border: none;
    transform: none;
  }
  #graph-toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%) translateY(20px);
    background: var(--panel);
    color: var(--text);
    border: 1px solid var(--border);
    padding: 7px 14px;
    border-radius: 4px;
    font-family: var(--font-mono);
    font-size: 11.5px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    opacity: 0;
    pointer-events: none;
    transition: all 0.2s ease;
    z-index: 10000;
  }
  #graph-toast.show {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
</style>"""

def _hyperedge_script(hyperedges_json: str) -> str:
    return f"""<script>
// Render hyperedges as shaded regions
const hyperedges = {hyperedges_json};
// afterDrawing passes ctx already transformed to network coordinate space.
// Draw node positions raw — no manual pan/zoom/DPR math needed.

// Andrew's monotone chain. Returns the hull in counter-clockwise order, which
// is what the perimeter must be traced in. Collinear and duplicate points
// collapse to the extremes, so degenerate member sets render as a segment
// rather than a zero-area crossed path.
function convexHull(pts) {{
    const p = pts.slice().sort((a, b) => (a.x - b.x) || (a.y - b.y));
    if (p.length < 3) return p;
    const cross = (o, a, b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
    const build = seq => {{
        const out = [];
        for (const q of seq) {{
            while (out.length >= 2 && cross(out[out.length - 2], out[out.length - 1], q) <= 0) out.pop();
            out.push(q);
        }}
        out.pop();
        return out;
    }};
    const hull = build(p).concat(build(p.slice().reverse()));
    return hull.length >= 3 ? hull : p;
}}
network.on('afterDrawing', function(ctx) {{
    hyperedges.forEach(h => {{
        // Legend toggles only set `hidden` on nodes; getPositions() still
        // returns them, so skip hidden members or their hull lingers.
        const positions = h.nodes
            .filter(nid => {{ const n = nodesDS.get(nid); return n && n.hidden !== true; }})
            .map(nid => network.getPositions([nid])[nid])
            .filter(p => p !== undefined);
        if (positions.length < 2) return;
        ctx.save();
        ctx.globalAlpha = 0.12;
        ctx.fillStyle = '#6366f1';
        ctx.strokeStyle = '#6366f1';
        ctx.lineWidth = 2;
        ctx.beginPath();
        // Centroid and expanded hull in network coordinates.
        // The perimeter must follow hull order, not h.nodes order: tracing the
        // raw member order self-intersects whenever the layout does not happen
        // to place members in angular order, filling as crossed wedges.
        const cx = positions.reduce((s, p) => s + p.x, 0) / positions.length;
        const cy = positions.reduce((s, p) => s + p.y, 0) / positions.length;
        const hull = convexHull(positions);
        const expanded = hull.map(p => ({{
            x: cx + (p.x - cx) * 1.15,
            y: cy + (p.y - cy) * 1.15
        }}));
        ctx.moveTo(expanded[0].x, expanded[0].y);
        expanded.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
        ctx.closePath();
        ctx.fill();
        ctx.globalAlpha = 0.4;
        ctx.stroke();
        // Label
        ctx.globalAlpha = 0.8;
        ctx.fillStyle = '#4f46e5';
        ctx.font = 'bold 11px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(h.label, cx, cy - 5);
        ctx.restore();
    }});
}});
</script>"""

def _html_script(nodes_json: str, edges_json: str, legend_json: str) -> str:
    return f"""<script>
const RAW_NODES = {nodes_json};
const RAW_EDGES = {edges_json};
const LEGEND = {legend_json};

// HTML-escape helper — prevents XSS when injecting graph data into innerHTML
function esc(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}}

// Build vis datasets
const nodesDS = new vis.DataSet(RAW_NODES.map((n, i) => ({{
  id: n.id, label: n.label, color: n.color, size: n.size,
  font: n.font, title: n.title,
  // Fermat/golden-angle spiral seed positions (#3699): spreading nodes out
  // before physics runs keeps avoidOverlap from computing near-zero-distance
  // repulsion that blows the BarnesHut recursion into a stack overflow on large
  // graphs. `i` is the map index — physics still settles small graphs identically.
  x: 30 * Math.sqrt(i) * Math.cos(i * 2.4),
  y: 30 * Math.sqrt(i) * Math.sin(i * 2.4),
  community: n.community, community_name: n.community_name,
  source_file: n.source_file, source_location: n.source_location,
  start_line: n.start_line, end_line: n.end_line,
  file_type: n.file_type, degree: n.degree,
  member_count: n.member_count,
}})));

const edgesDS = new vis.DataSet(RAW_EDGES.map((e, i) => ({{
  id: i, from: e.from, to: e.to,
  label: '',
  rel: e.label,
  title: e.title,
  dashes: e.dashes,
  width: e.width,
  color: e.color,
  arrows: {{ to: {{ enabled: true, scaleFactor: 0.5 }} }},
}})));

const container = document.getElementById('graph');
const network = new vis.Network(container, {{ nodes: nodesDS, edges: edgesDS }}, {{
  physics: {{
    enabled: true,
    solver: 'forceAtlas2Based',
    forceAtlas2Based: {{
      gravitationalConstant: -60,
      centralGravity: 0.005,
      springLength: 120,
      springConstant: 0.08,
      damping: 0.4,
      avoidOverlap: 0.8,
    }},
    stabilization: {{ iterations: 200, fit: true }},
  }},
  interaction: {{
    hover: true,
    tooltipDelay: 100,
    hideEdgesOnDrag: true,
    navigationButtons: false,
    keyboard: false,
  }},
  nodes: {{ shape: 'dot', borderWidth: 1.5 }},
  edges: {{ smooth: {{ type: 'continuous', roundness: 0.2 }}, selectionWidth: 3 }},
}});

// Theme toggle (#3894): Light / Dark / System, persisted in localStorage.
const THEME_KEY = 'graphify-theme';
const themeMQ = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;
let themeLabelColor = '#ffffff';  // matches the per-node font color set in Python
function themePref() {{
  let p = null;
  try {{ p = localStorage.getItem(THEME_KEY); }} catch (e) {{}}
  return (p === 'light' || p === 'dark' || p === 'system') ? p : null;
}}
function applyTheme(pref) {{
  const t = pref === 'light' ? 'light' : (pref === 'system' && themeMQ && themeMQ.matches) ? 'light' : 'dark';
  const root = document.documentElement;
  if (!root) return;
  root.setAttribute('data-theme', t);
  document.querySelectorAll('[data-theme-choice]').forEach(b => {{
    b.setAttribute('aria-pressed', String(b.dataset.themeChoice === (pref || 'dark')));
  }});
  const labelColor = getComputedStyle(root).getPropertyValue('--node-label').trim();
  if (labelColor && labelColor !== themeLabelColor) {{
    themeLabelColor = labelColor;
    nodesDS.update(nodesDS.get().map(n => ({{ id: n.id, font: Object.assign({{}}, n.font, {{ color: labelColor }}) }})));
  }}
}}
document.querySelectorAll('[data-theme-choice]').forEach(b => {{
  b.addEventListener('click', () => {{
    const pref = b.dataset.themeChoice;
    try {{ localStorage.setItem(THEME_KEY, pref); }} catch (e) {{}}
    applyTheme(pref);
  }});
}});
if (themeMQ) {{
  const onSchemeChange = () => {{ if (themePref() === 'system') applyTheme('system'); }};
  if (themeMQ.addEventListener) themeMQ.addEventListener('change', onSchemeChange);
  else if (themeMQ.addListener) themeMQ.addListener(onSchemeChange);
}}
applyTheme(themePref());

network.once('stabilizationIterationsDone', () => {{
  network.setOptions({{ physics: {{ enabled: false }} }});
}});

function getAgentRef(n) {{
  if (!n || !n.source_file || n.source_file === '-' || n.source_file === 'None') return '';
  const file = n.source_file;
  const isPureFile = (n.id === file || n.label === file || n.file_type === 'file' || (!n.source_location && !n.start_line));
  if (isPureFile && (!n.source_location || (n.source_location === 'L1' && n.label.endsWith(file)))) {{
    return `@${{file}}`;
  }}
  let start = n.start_line;
  let end = n.end_line;
  if ((start === undefined || start === null) && n.source_location) {{
    const raw = String(n.source_location).trim().replace(/^L/i, '');
    const m = raw.match(/^(\\d+)(?:[-:]L?(\\d+))?$/i);
    if (m) {{
      start = parseInt(m[1], 10);
      end = m[2] ? parseInt(m[2], 10) : start;
    }}
  }}
  if (start !== undefined && start !== null) {{
    const endLine = (end !== undefined && end !== null) ? end : start;
    return `@${{file}}:L${{start}}-L${{endLine}}`;
  }}
  return `@${{file}}`;
}}

function copyAgentRef(refText, btnEl) {{
  if (!refText) return;
  const originalHtml = btnEl.innerHTML;
  function markCopied() {{
    btnEl.classList.add('copied');
    btnEl.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right:5px;flex-shrink:0;"><polyline points="20 6 9 17 4 12"></polyline></svg><span class="btn-text">Copied!</span>';
    showToast(`Copied: ${{refText}}`);
    setTimeout(() => {{
      btnEl.classList.remove('copied');
      btnEl.innerHTML = originalHtml;
    }}, 2000);
  }}
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(refText).then(markCopied).catch(() => {{
      fallbackCopy(refText, markCopied);
    }});
  }} else {{
    fallbackCopy(refText, markCopied);
  }}
}}

function fallbackCopy(text, onSuccess) {{
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.left = '-9999px';
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  try {{
    document.execCommand('copy');
    if (onSuccess) onSuccess();
  }} catch(e) {{}}
  document.body.removeChild(ta);
}}

function showToast(msg) {{
  let toast = document.getElementById('graph-toast');
  if (!toast) {{
    toast = document.createElement('div');
    toast.id = 'graph-toast';
    document.body.appendChild(toast);
  }}
  toast.textContent = msg;
  toast.className = 'show';
  clearTimeout(toast._timeout);
  toast._timeout = setTimeout(() => {{
    toast.className = '';
  }}, 2200);
}}

function showInfo(nodeId) {{
  const n = nodesDS.get(nodeId);
  if (!n) return;
  const connectedEdgeIds = network.getConnectedEdges(nodeId);
  const neighborIds = network.getConnectedNodes(nodeId);
  
  const callsOut = [];
  const callsIn = [];
  const otherConns = [];
  
  connectedEdgeIds.forEach(eid => {{
    const edge = edgesDS.get(eid);
    if (!edge) return;
    const isOut = edge.from === nodeId;
    const otherId = isOut ? edge.to : edge.from;
    const otherNode = nodesDS.get(otherId);
    if (!otherNode) return;
    const rel = edge.rel || edge.label || 'connects';
    const item = {{
      id: otherId,
      label: otherNode.label,
      rel: rel,
      color: otherNode.color ? otherNode.color.background : '#555',
    }};
    if (rel === 'calls' || rel === 'contains' || rel === 'imports' || rel === 'method') {{
      if (isOut) callsOut.push(item);
      else callsIn.push(item);
    }} else {{
      otherConns.push(item);
    }}
  }});

  const isMetaNode = !n.file_type && !n.source_file;
  const ref = getAgentRef(n);
  
  let html = `<div class="node-header"><div class="node-title">${{esc(n.label)}}</div></div>`;
  
  if (ref) {{
    html += `<button type="button" class="copy-agent-btn" id="copy-ref-btn" data-ref="${{esc(ref)}}">` +
            `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:5px;flex-shrink:0;"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>` +
            `<span class="btn-text">Copy @file:L</span>` +
            `</button>` +
            `<div class="ref-preview" title="Agent reference">${{esc(ref)}}</div>`;
  }}
  
  html += `<div class="node-meta-grid">`;
  if (!isMetaNode && n.source_file && n.source_file !== '-') {{
    html += `<span class="node-meta-key">File</span><span class="node-meta-val">${{esc(n.source_file)}}</span>`;
  }}
  if (n.source_location) {{
    html += `<span class="node-meta-key">Lines</span><span class="node-meta-val">${{esc(n.source_location)}}</span>`;
  }}
  if (n.community_name) {{
    html += `<span class="node-meta-key">Cluster</span><span class="node-meta-val">${{esc(n.community_name)}}</span>`;
  }}
  if (!isMetaNode && n.file_type) {{
    html += `<span class="node-meta-key">Type</span><span class="node-meta-val">${{esc(n.file_type)}}</span>`;
  }} else if (n.member_count !== undefined && n.member_count !== null) {{
    html += `<span class="node-meta-key">Members</span><span class="node-meta-val">${{esc(n.member_count)}}</span>`;
  }}
  html += `<span class="node-meta-key">Degree</span><span class="node-meta-val">${{n.degree || 0}}</span>`;
  html += `</div>`;
  
  function renderLinks(list) {{
    return list.map(item => {{
      return `<span class="neighbor-link" style="border-left-color:${{esc(item.color)}}" data-nid="${{esc(item.id)}}">` +
             `<span class="conn-badge">${{esc(item.rel)}}</span>` +
             `<span>${{esc(item.label)}}</span>` +
             `</span>`;
    }}).join('');
  }}

  if (callsOut.length > 0) {{
    html += `<div class="conn-section-title">Calls / Contains (${{callsOut.length}})</div><div id="neighbors-list">${{renderLinks(callsOut)}}</div>`;
  }}
  if (callsIn.length > 0) {{
    html += `<div class="conn-section-title">Called by / In (${{callsIn.length}})</div><div id="neighbors-list">${{renderLinks(callsIn)}}</div>`;
  }}
  if (otherConns.length > 0) {{
    html += `<div class="conn-section-title">Connections (${{otherConns.length}})</div><div id="neighbors-list">${{renderLinks(otherConns)}}</div>`;
  }} else if (!callsOut.length && !callsIn.length && neighborIds.length > 0) {{
    const genericItems = neighborIds.map(nid => {{
      const nb = nodesDS.get(nid);
      const color = nb ? nb.color.background : '#555';
      return `<span class="neighbor-link" style="border-left-color:${{esc(color)}}" data-nid="${{esc(nid)}}"><span>${{esc(nb ? nb.label : nid)}}</span></span>`;
    }}).join('');
    html += `<div class="conn-section-title">Connections (${{neighborIds.length}})</div><div id="neighbors-list">${{genericItems}}</div>`;
  }}

  document.getElementById('info-content').innerHTML = html;
}}

function focusNode(nodeId) {{
  network.focus(nodeId, {{ scale: 1.4, animation: true }});
  network.selectNodes([nodeId]);
  showInfo(nodeId);
}}

// Neighbor links use a data attribute + one delegated listener rather than an
// inline onclick. A node id/label sourced from a document or a scraped URL
// (graphify add) can contain a double-quote; dropping the stringified id
// unescaped into a quoted onclick both broke every link and allowed a hostile
// source to inject an event handler into the local report (stored XSS, #1838).
// esc() on data-nid keeps the value inside the attribute; the listener reads it
// back verbatim. Bound to document so it survives the innerHTML rebuild that
// recreates #neighbors-list on each showInfo().
document.addEventListener('click', e => {{
  const copyBtn = e.target.closest('#copy-ref-btn');
  if (copyBtn && copyBtn.dataset.ref) {{
    copyAgentRef(copyBtn.dataset.ref, copyBtn);
    return;
  }}
  const el = e.target.closest('.neighbor-link');
  if (el && el.dataset.nid !== undefined) focusNode(el.dataset.nid);
}});

// Sidebar tooltips reuse vis-network's .vis-tooltip style and 100ms tooltipDelay.
// Names get one only when CSS ellipsis truncates them (the full text is still in
// the DOM); counts always get one, to say what the number is. Text is set with
// textContent only (labels are untrusted). Delegated on document so rows rebuilt
// later (search results, showInfo()) are covered.
const sidebarTip = document.createElement('div');
sidebarTip.className = 'vis-tooltip';
sidebarTip.style.cssText = 'white-space: normal; max-width: 360px; overflow-wrap: break-word;';
document.body.appendChild(sidebarTip);
let sidebarTipTimer = null;
let sidebarTipEl = null;    // element whose text the tooltip shows
let sidebarTipZone = null;  // element the pointer must leave to hide it
function hideSidebarTip() {{
  clearTimeout(sidebarTipTimer);
  sidebarTip.style.visibility = 'hidden';
  sidebarTip.textContent = '';
  sidebarTipEl = sidebarTipZone = null;
}}
document.addEventListener('mouseover', e => {{
  const zone = e.target.closest && e.target.closest('.legend-count, .legend-item, .search-item, .neighbor-link');
  // Anywhere on a legend row except its count (dot, checkbox, gaps, padding)
  // stands for the row's name, so moving within the row never re-triggers it.
  const el = zone && zone.classList.contains('legend-item') ? zone.querySelector('.legend-label') : zone;
  if (!el || el === sidebarTipEl) return;
  hideSidebarTip();
  const isCount = el.classList.contains('legend-count');
  if (!isCount && el.scrollWidth <= el.clientWidth) return;
  const text = isCount ? `${{el.textContent}} ${{el.textContent === '1' ? 'node' : 'nodes'}}` : el.textContent;
  sidebarTipEl = el;
  sidebarTipZone = zone;
  const x = e.clientX, y = e.clientY;
  sidebarTipTimer = setTimeout(() => {{
    sidebarTip.textContent = text;
    sidebarTip.style.left = sidebarTip.style.top = '0px';  // measure at full max-width
    sidebarTip.style.visibility = 'visible';
    const w = sidebarTip.offsetWidth, h = sidebarTip.offsetHeight;
    sidebarTip.style.left = Math.max(4, Math.min(x + 12, window.innerWidth - w - 4)) + 'px';
    sidebarTip.style.top = (y + 16 + h > window.innerHeight ? Math.max(4, y - h - 8) : y + 16) + 'px';
  }}, 100);
}});
document.addEventListener('mouseout', e => {{
  if (sidebarTipZone && !sidebarTipZone.contains(e.relatedTarget)) hideSidebarTip();
}});
// A click rebuilds or hides the row (showInfo(), search pick) without a mouseout.
document.addEventListener('mousedown', hideSidebarTip);

// Track hovered node — hover detection is more reliable than click params
let hoveredNodeId = null;
network.on('hoverNode', params => {{
  hoveredNodeId = params.node;
  container.style.cursor = 'pointer';
}});
network.on('blurNode', () => {{
  hoveredNodeId = null;
  container.style.cursor = 'default';
}});
container.addEventListener('click', () => {{
  if (hoveredNodeId !== null) {{
    showInfo(hoveredNodeId);
    network.selectNodes([hoveredNodeId]);
  }}
}});
network.on('click', params => {{
  if (params.nodes.length > 0) {{
    showInfo(params.nodes[0]);
  }} else if (hoveredNodeId === null) {{
    document.getElementById('info-content').innerHTML = '<span class="empty">Click a node to inspect it</span>';
  }}
}});

const searchInput = document.getElementById('search');
const searchResults = document.getElementById('search-results');
searchInput.addEventListener('input', () => {{
  const q = searchInput.value.toLowerCase().trim();
  searchResults.innerHTML = '';
  if (!q) {{ searchResults.style.display = 'none'; return; }}
  const matches = RAW_NODES.filter(n => n.label.toLowerCase().includes(q)).slice(0, 20);
  if (!matches.length) {{ searchResults.style.display = 'none'; return; }}
  searchResults.style.display = 'block';
  matches.forEach(n => {{
    const el = document.createElement('div');
    el.className = 'search-item';
    el.textContent = n.label;
    el.style.borderLeft = `3px solid ${{n.color.background}}`;
    el.style.paddingLeft = '8px';
    el.onclick = () => {{
      network.focus(n.id, {{ scale: 1.5, animation: true }});
      network.selectNodes([n.id]);
      showInfo(n.id);
      searchResults.style.display = 'none';
      searchInput.value = '';
    }};
    searchResults.appendChild(el);
  }});
}});
document.addEventListener('click', e => {{
  if (!searchResults.contains(e.target) && e.target !== searchInput)
    searchResults.style.display = 'none';
}});

const hiddenCommunities = new Set();

const selectAllCb = document.getElementById('select-all-cb');

function updateSelectAllState() {{
  const total = LEGEND.length;
  const hidden = hiddenCommunities.size;
  selectAllCb.checked = hidden === 0;
  selectAllCb.indeterminate = hidden > 0 && hidden < total;
}}

function toggleAllCommunities(hide) {{
  document.querySelectorAll('.legend-item').forEach(item => {{
    hide ? item.classList.add('dimmed') : item.classList.remove('dimmed');
  }});
  document.querySelectorAll('.legend-cb').forEach(cb => {{
    cb.checked = !hide;
  }});
  LEGEND.forEach(c => {{
    if (hide) hiddenCommunities.add(c.cid); else hiddenCommunities.delete(c.cid);
  }});
  const updates = RAW_NODES.map(n => ({{ id: n.id, hidden: hide }}));
  nodesDS.update(updates);
  updateSelectAllState();
}}

const legendEl = document.getElementById('legend');
LEGEND.forEach(c => {{
  const item = document.createElement('div');
  item.className = 'legend-item';
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.className = 'legend-cb';
  cb.checked = true;
  cb.addEventListener('change', (e) => {{
    e.stopPropagation();
    if (cb.checked) {{
      hiddenCommunities.delete(c.cid);
      item.classList.remove('dimmed');
    }} else {{
      hiddenCommunities.add(c.cid);
      item.classList.add('dimmed');
    }}
    const updates = RAW_NODES
      .filter(n => n.community === c.cid)
      .map(n => ({{ id: n.id, hidden: !cb.checked }}));
    nodesDS.update(updates);
    updateSelectAllState();
  }});
  item.innerHTML = `<div class="legend-dot" style="background:${{c.color}}"></div>
    <span class="legend-label">${{c.label}}</span>
    <span class="legend-count">${{c.count}}</span>`;
  item.prepend(cb);
  item.onclick = (e) => {{
    if (e.target === cb) return;
    cb.checked = !cb.checked;
    cb.dispatchEvent(new Event('change'));
  }};
  legendEl.appendChild(item);
}});
</script>"""


def _html_document_title(output_path: str) -> str:
    """Return a portable label for the graph.html <title>.

    Tracked artifacts must not embed the generator host absolute path
    (regression of #433; reported again as #2598 on Windows). Keep from the
    configured output-dir bare name (``graphify-out`` / ``GRAPHIFY_OUT``
    basename) onward — portable in every case; otherwise fall back to a
    cwd-relative label, and finally the filename only.
    """
    from graphify.paths import GRAPHIFY_OUT_NAME

    raw = str(output_path).replace("\\", "/")
    # Drop Windows drive prefix so Path parts are comparable on any OS.
    if len(raw) >= 3 and raw[1] == ":" and raw[0].isalpha() and raw[2] == "/":
        raw = raw[2:]  # "/Users/..." style after drive strip
    p = Path(raw)

    parts = list(Path(raw).parts)
    # Path("C:/Users/..") on POSIX may keep "C:" as first part — strip it.
    if parts and len(parts[0]) == 2 and parts[0][1] == ":" and parts[0][0].isalpha():
        parts = parts[1:]
    # Prefer keeping from the output-dir marker onward: portable in every
    # case, whereas a cwd-relative path still leaks host/user segments when
    # the graph is built from a directory ABOVE the project (#2598 follow-up).
    marker = GRAPHIFY_OUT_NAME
    for i, part in enumerate(parts):
        if part == marker or part.startswith("graphify-out"):
            return "/".join(parts[i:])

    # No standard out-dir marker (fully custom output path): fall back to a
    # cwd-relative label when the target is under cwd, else the bare filename.
    try:
        resolved = p if p.is_absolute() else (Path.cwd() / p)
        rel = resolved.resolve().relative_to(Path.cwd().resolve())
        label = rel.as_posix()
        if label and label != ".":
            return label
    except (ValueError, OSError, RuntimeError):
        pass

    name = p.name
    return name if name else "graph.html"

def to_html(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
    community_labels: dict[int, str] | None = None,
    member_counts: dict[int, int] | None = None,
    node_limit: int | None = None,
    learning_overlay: dict | None = None,
) -> bool:
    """Generate an interactive vis.js HTML visualization of the graph.

    Features: node size by degree, click-to-inspect panel, search box,
    community filter, physics clustering by community, confidence-styled edges.
    Raises ValueError if graph exceeds MAX_NODES_FOR_VIZ.

    If member_counts is provided (aggregated community view), node sizes are
    based on community member counts rather than graph degree.

    If node_limit is set and the graph exceeds it, automatically builds an
    aggregated community-level meta-graph instead of raising ValueError.

    Returns True when the output was written. Returns False when an aggregated
    view would contain fewer than two communities and is intentionally skipped.
    """
    limit = node_limit if node_limit is not None else _viz_node_limit()
    if G.number_of_nodes() > limit:
        if node_limit is not None:
            # Build aggregated community meta-graph
            from collections import Counter as _Counter
            import networkx as _nx
            print(f"Graph has {G.number_of_nodes()} nodes (above {limit} limit). Building aggregated community view...")
            node_to_community = {nid: cid for cid, members in communities.items() for nid in members}
            meta = _nx.Graph()
            for cid, members in communities.items():
                meta.add_node(str(cid), label=(community_labels or {}).get(cid, f"Community {cid}"))
            edge_counts = _Counter()
            for u, v in G.edges():
                cu, cv = node_to_community.get(u), node_to_community.get(v)
                if cu is not None and cv is not None and cu != cv:
                    edge_counts[(min(cu, cv), max(cu, cv))] += 1
            for (cu, cv), w in edge_counts.items():
                meta.add_edge(str(cu), str(cv), weight=w,
                              relation=f"{w} cross-community edges", confidence="AGGREGATED")
            if meta.number_of_nodes() <= 1:
                print("Single community - aggregated view not useful. Skipping graph.html.")
                return False
            meta_communities = {cid: [str(cid)] for cid in communities}
            mc = {cid: len(members) for cid, members in communities.items()}
            # Remap hyperedges from semantic node IDs to community IDs
            raw_hyperedges = G.graph.get("hyperedges", [])
            if raw_hyperedges:
                remapped = []
                for he in raw_hyperedges:
                    he_members = he.get("nodes", [])
                    comm_ids, seen = [], set()
                    for nid in he_members:
                        c = node_to_community.get(nid)
                        if c is None:
                            continue
                        s = str(c)
                        if s in seen:
                            continue
                        seen.add(s)
                        comm_ids.append(s)
                    if len(comm_ids) < 2:
                        continue
                    remapped.append({
                        "id": he.get("id", ""),
                        "label": he.get("label") or he.get("relation", "").replace("_", " "),
                        "nodes": comm_ids,
                    })
                meta.graph["hyperedges"] = remapped
            written = to_html(meta, meta_communities, output_path,
                              community_labels=community_labels, member_counts=mc)
            if not written:
                return False
            print(f"graph.html written (aggregated: {meta.number_of_nodes()} community nodes, {meta.number_of_edges()} cross-community edges)")
            print("Tip: run with --obsidian for full node-level detail.")
            return True
        raise ValueError(
            f"Graph has {G.number_of_nodes()} nodes - too large for HTML viz "
            f"(limit: {limit}). Use --no-viz, raise GRAPHIFY_VIZ_NODE_LIMIT, "
            f"or reduce input size."
        )

    node_community = _node_community_map(communities)
    degree = dict(G.degree())
    max_deg = max(degree.values(), default=1) or 1
    max_mc = (max(member_counts.values(), default=1) or 1) if member_counts else 1

    # Work-memory overlay (derived sidecar). When not passed explicitly, load it
    # best-effort from the sibling .graphify_learning.json next to the output
    # graph.html (which lives beside graph.json). Empty/missing => no learning
    # fields, so the un-annotated render is byte-identical to pre-feature.
    if learning_overlay is None:
        learning_overlay = {}
        try:
            from graphify.reflect import load_learning_overlay as _llo
            learning_overlay = _llo(Path(output_path))
        except Exception:
            learning_overlay = {}
    # Status -> ring color. preferred=green, contested=amber. Tentative gets no
    # ring (it's not yet trustworthy enough to highlight in the map).
    _RING = {"preferred": "#22c55e", "contested": "#f59e0b"}

    # Build nodes list for vis.js
    vis_nodes = []
    for node_id, data in G.nodes(data=True):
        cid = node_community.get(node_id, 0)
        color = COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)]
        label = sanitize_label(data.get("label", node_id))
        deg = degree.get(node_id, 1)
        if member_counts:
            mc = member_counts.get(cid, 1)
            size = 10 + 30 * (mc / max_mc)
            font_size = 12
        else:
            size = 10 + 30 * (deg / max_deg)
            # Only show label for high-degree nodes by default; others show on hover
            font_size = 12 if deg >= max_deg * 0.15 else 0
        node = {
            "id": node_id,
            "label": label,
            "color": {"background": color, "border": color, "highlight": {"background": "#ffffff", "border": color}},
            "size": round(size, 1),
            "font": {"size": font_size, "color": "#ffffff"},
            # Tooltip `title` is a STRING, which vis-network renders via
            # Popup.setText -> `frame.innerText = t` (verified in the pinned
            # 9.1.6 bundle: the only non-Element branch is innerText, and the
            # bundle has zero `innerHTML = <var>` sinks). So raw special chars
            # are shown literally and must NOT be html-escaped here or the user
            # sees `&amp;`/`&lt;` in the tooltip (#3664/#3686). This is the
            # #1838 stored-XSS boundary: never pass an HTMLElement as `title`,
            # and do not change the vis-network pin below without re-checking
            # Popup rendering (the test_export version-pin guard enforces this).
            "title": label,
            "community": cid,
            "community_name": sanitize_label((community_labels or {}).get(cid, f"Community {cid}")),
            "source_file": sanitize_label(str(data.get("source_file") or "")),
            "source_location": sanitize_label(str(data.get("source_location") or "")),
            "start_line": data.get("start_line"),
            "end_line": data.get("end_line"),
            "file_type": data.get("file_type", ""),
            "degree": deg,
        }
        if member_counts:
            node["member_count"] = member_counts.get(cid, len(communities.get(cid, [])))
        # Conditional learning fields — only present for annotated nodes, so
        # un-annotated output keeps the exact pre-feature node dict shape.
        entry = learning_overlay.get(str(node_id)) if learning_overlay else None
        if entry:
            status = sanitize_label(str(entry.get("status", "")))
            stale = bool(entry.get("stale"))
            node["learning_status"] = status
            node["learning_stale"] = stale
            ring = _RING.get(status)
            if ring:
                # Status-colored ring via the border; stale => desaturated +
                # dashed (vis.js supports per-node `shapeProperties.borderDashes`).
                if stale:
                    ring = "#9ca3af"
                    node["shapeProperties"] = {"borderDashes": [4, 4]}
                node["borderWidth"] = 3
                node["color"] = {
                    "background": color, "border": ring,
                    "highlight": {"background": "#ffffff", "border": ring},
                }
            # Lesson line appended to the hover title.
            if status == "contested":
                lesson = f"Lesson: contested (useful {entry.get('uses', 0)} / dead-end {entry.get('neg', 0)})"
            elif status == "preferred":
                lesson = f"Lesson: preferred source ({entry.get('uses', 0)} useful, score={entry.get('score', 0)})"
            else:
                lesson = f"Lesson: {status} ({entry.get('uses', 0)} useful)"
            if stale:
                lesson += " [code changed — re-verify]"
            node["title"] = f"{label}\n{sanitize_label(lesson)}"
        vis_nodes.append(node)

    # Build edges list. Restore original edge direction from _src/_tgt
    # (stashed by build.py for exactly this reason): undirected NetworkX
    # canonicalizes endpoint order, which would otherwise flip the arrow
    # for `calls` and `rationale_for` in the rendered graph (#563).
    vis_edges = []
    for u, v, data in G.edges(data=True):
        confidence = data.get("confidence", "EXTRACTED")
        relation = data.get("relation", "")
        true_src = data.get("_src", u)
        true_tgt = data.get("_tgt", v)
        vis_edges.append({
            "from": true_src,
            "to": true_tgt,
            "label": relation,
            "title": sanitize_label(f"{relation} [{confidence}]"),
            "dashes": confidence != "EXTRACTED",
            "width": 2 if confidence == "EXTRACTED" else 1,
            "color": {"opacity": 0.7 if confidence == "EXTRACTED" else 0.35},
            "confidence": confidence,
        })

    # Build community legend data
    legend_data = []
    for cid in sorted((community_labels or {}).keys()):
        color = COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)]
        lbl = _html.escape(sanitize_label((community_labels or {}).get(cid, f"Community {cid}")))
        n = member_counts.get(cid, len(communities.get(cid, []))) if member_counts else len(communities.get(cid, []))
        legend_data.append({"cid": cid, "color": color, "label": lbl, "count": n})

    # Escape every `<` as < so embedded JSON cannot break out of the <script>
    # element. Escaping only `</` is not enough: an unclosed `<!--` then a later
    # `<script` in a label drive the HTML tokenizer into script-data-double-escaped
    # state, where the real `</script>` no longer closes the tag and the page goes
    # blank (#4124). `<` round-trips through JSON.parse, so labels render unchanged.
    def _js_safe(obj) -> str:
        return json.dumps(obj).replace("<", "\\u003c")

    nodes_json = _js_safe(vis_nodes)
    edges_json = _js_safe(vis_edges)
    legend_json = _js_safe(legend_data)
    hyperedges_json = _js_safe(getattr(G, "graph", {}).get("hyperedges", []))
    title = _html.escape(sanitize_label(_html_document_title(output_path)))
    stats = f"{G.number_of_nodes()} nodes &middot; {G.number_of_edges()} edges &middot; {len(communities)} communities"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>graphify - {title}</title>
<script src="https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js"
        integrity="sha384-Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1"
        crossorigin="anonymous"></script>
{_html_styles()}
<script id="graphify-theme-init">
// Apply the saved theme before first paint (#3894). No saved choice keeps the
// historical dark look; "system" follows prefers-color-scheme.
(function () {{
  var pref = null;
  try {{ pref = localStorage.getItem('graphify-theme'); }} catch (e) {{}}
  var t = pref === 'light' ? 'light'
    : pref === 'system' && window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light'
    : 'dark';
  document.documentElement.setAttribute('data-theme', t);
}})();
</script>
</head>
<body>
<div id="graph"></div>
<div id="sidebar">
  <div id="theme-wrap" role="group" aria-label="Theme">
    <button type="button" data-theme-choice="light">Light</button>
    <button type="button" data-theme-choice="dark">Dark</button>
    <button type="button" data-theme-choice="system">System</button>
  </div>
  <div id="search-wrap">
    <input id="search" type="text" placeholder="Search nodes..." autocomplete="off">
    <div id="search-results"></div>
  </div>
  <div id="info-panel">
    <h3>Node Details</h3>
    <div id="info-content"><span class="empty">Click a node to inspect it</span></div>
  </div>
  <div id="legend-wrap">
    <h3>Clusters</h3>
    <div id="legend-controls">
      <label><input type="checkbox" id="select-all-cb" checked onchange="toggleAllCommunities(!this.checked)">Select All</label>
    </div>
    <div id="legend"></div>
  </div>
  <div id="stats">{stats}</div>
</div>
{_html_script(nodes_json, edges_json, legend_json)}
{_hyperedge_script(hyperedges_json)}
</body>
</html>"""

    write_text_atomic(output_path, html)
    return True
