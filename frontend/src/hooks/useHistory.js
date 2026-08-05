import { useEffect, useState } from 'react'

// Polls backend's /api/history for a sparkline series. Kept separate
// from the /ws live feed since history is a much lower-frequency,
// larger payload that only the spark blocks need.
export function useHistorySeries(sensor, field, { minutes = 10, refreshMs = 8000, maxPoints = 30 } = {}) {
  const [series, setSeries] = useState([])

  useEffect(() => {
    let cancelled = false

    async function tick() {
      try {
        const resp = await fetch(`/api/history?sensor=${sensor}&minutes=${minutes}`)
        const rows = await resp.json()
        if (cancelled || !Array.isArray(rows)) return
        const values = rows.map((r) => r[field]).filter((v) => v != null)
        setSeries(values.slice(-maxPoints))
      } catch {
        // keep the last known series on a transient fetch failure
      }
    }

    tick()
    const id = setInterval(tick, refreshMs)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [sensor, field, minutes, refreshMs, maxPoints])

  return series
}
