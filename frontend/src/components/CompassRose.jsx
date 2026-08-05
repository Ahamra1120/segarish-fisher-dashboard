// GPS heading indicator. Deliberately labeled/behaved as "Heading (GPS)"
// rather than "Compass": the Sologood M10 has no magnetometer, so this
// is course-over-ground, only meaningful while moving -- see
// sensor-service/drivers/gps.py. Below, the needle greys out and
// straightens when there's no fix or no heading yet, instead of
// pointing somewhere misleading.
const TICKS = { 0: 'U', 90: 'T', 180: 'S', 270: 'B' } // Utara/Timur/Selatan/Barat

export function CompassRose({ headingDeg, hasFix, size = 120 }) {
  const cx = size / 2
  const cy = size / 2
  const r = size / 2 - 12
  const active = hasFix && headingDeg != null
  const angle = active ? headingDeg : 0
  const needleColor = active ? 'var(--brand)' : 'var(--text-2)'

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--border-strong)" strokeWidth={1.5} />
      {Object.entries(TICKS).map(([deg, label]) => {
        const rad = ((Number(deg) - 90) * Math.PI) / 180
        const x1 = cx + Math.cos(rad) * (r - 7)
        const y1 = cy + Math.sin(rad) * (r - 7)
        const x2 = cx + Math.cos(rad) * r
        const y2 = cy + Math.sin(rad) * r
        const lx = cx + Math.cos(rad) * (r - 18)
        const ly = cy + Math.sin(rad) * (r - 18)
        return (
          <g key={deg}>
            <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--text-2)" strokeWidth={1.5} />
            <text x={lx} y={ly} fontSize={11} fontWeight={700} fill="var(--text-2)" textAnchor="middle" dominantBaseline="middle">
              {label}
            </text>
          </g>
        )
      })}
      <g style={{ transform: `rotate(${angle}deg)`, transformOrigin: `${cx}px ${cy}px`, transition: 'transform 0.5s ease' }}>
        <polygon points={`${cx},${cy - r + 22} ${cx - 6},${cy} ${cx + 6},${cy}`} fill={needleColor} />
        <polygon points={`${cx},${cy + r - 22} ${cx - 6},${cy} ${cx + 6},${cy}`} fill="var(--border-strong)" />
      </g>
      <circle cx={cx} cy={cy} r={4} fill="var(--text-0)" />
    </svg>
  )
}
