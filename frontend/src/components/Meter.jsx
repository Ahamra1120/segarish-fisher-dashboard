// Radial "meter / progress track" -- a single ratio against a limit
// (per the dataviz skill's form guidance: "a single ratio against a
// limit" -> Meter, same-ramp track). The fill color is a prop so a
// status-driven meter (gas quality) and a neutral single-hue meter
// (load %) can share this one implementation.
export function Meter({ value, min = 0, max = 100, size = 96, stroke = 10, trackColor = 'var(--bg-3)', fillColor = 'var(--brand)', children }) {
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const frac = Math.max(0, Math.min(1, (value - min) / (max - min || 1)))
  const dash = frac * c

  return (
    <div className="meter-wrap" style={{ width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={trackColor} strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={fillColor}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c}`}
          style={{ transition: 'stroke-dasharray 0.6s ease, stroke 0.3s ease' }}
        />
      </svg>
      <div className="meter-center">{children}</div>
    </div>
  )
}
