import { Radio, WifiOff } from 'lucide-react'

// Sparkline ported from segarish/src/components/ui.jsx, stroke bumped to
// 2px per the dataviz skill's mark spec (thin marks, 2px lines).
export function Spark({ data, color = 'var(--brand)', h = 34 }) {
  if (!data || data.length < 2) return null
  const W = 100
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const pts = data.map((d, i) => [(i / (data.length - 1)) * W, h - 3 - ((d - min) / range) * (h - 6)])
  const line = pts.map((p) => p.join(',')).join(' ')
  const area = `0,${h} ${line} ${W},${h}`
  const gid = `spk-${color.replace(/[^a-z0-9]/gi, '')}`
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${W} ${h}`} preserveAspectRatio="none" style={{ display: 'block' }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.25} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <polygon points={area} fill={`url(#${gid})`} />
      <polyline
        points={line}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r={2.5} fill={color} />
    </svg>
  )
}

// Status chip -- uses the fixed, validated status palette (never the
// brand hue) so "baik/sedang/buruk" always reads as status, not identity.
export function StatusChip({ status, children }) {
  return <span className={`status-chip ${status}`}>{children}</span>
}

export function ConnBadge({ connected, stale }) {
  const state = !connected ? 'offline' : stale ? 'stale' : 'live'
  const label = state === 'live' ? 'Live' : state === 'stale' ? 'Data lama' : 'Terputus'
  const Icon = state === 'offline' ? WifiOff : Radio
  return (
    <span className={`conn-badge ${state}`}>
      {state === 'live' ? <span className="dot" /> : <Icon size={12} />}
      {label}
    </span>
  )
}
