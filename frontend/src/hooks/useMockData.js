import { useEffect, useRef, useState } from 'react'

// Client-side mean-reverting random walk -- same technique the sibling
// `segarish` project uses for its demo data, and conceptually the same
// as sensor-service's drivers/simulate.py, just re-implemented here in
// JS. Used ONLY when VITE_DEMO_MODE=true (see useLiveData.js) -- a
// static host like Vercel has no backend/sensor-service to talk to, so
// this stands in for the real WebSocket feed.
function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v))
}

function walk(prev, target, pull, noise) {
  return prev + (target - prev) * pull + (Math.random() - 0.5) * noise
}

function gasLevel(ppm) {
  if (ppm < 400) return 'baik'
  if (ppm < 1000) return 'sedang'
  return 'buruk'
}

function seed() {
  return {
    gas: { ppm_est: 380, voltage: 1.4, level: 'baik' },
    load: { kg: 4.5, tared: true },
    gps: { lat: -5.98034, lon: 106.75651, heading_deg: 40, speed_kn: 4.2, satellites: 9, fix: true },
  }
}

function step(s) {
  const ppm = clamp(walk(s.gas.ppm_est, 420, 0.05, 30), 50, 1200)
  const voltage = clamp(walk(s.gas.voltage, 1.4, 0.05, 0.08), 0.4, 3.2)
  const kg = clamp(walk(s.load.kg, 5, 0.08, 0.6), 0, 50)
  const lat = s.gps.lat + (Math.random() - 0.5) * 0.0006
  const lon = s.gps.lon + (Math.random() - 0.5) * 0.0006
  const heading_deg = (s.gps.heading_deg + (Math.random() - 0.5) * 12 + 360) % 360
  const speed_kn = clamp(walk(s.gps.speed_kn, 4, 0.1, 0.6), 0, 12)

  return {
    gas: { ppm_est: ppm, voltage, level: gasLevel(ppm) },
    load: { kg, tared: true },
    gps: { lat, lon, heading_deg, speed_kn, satellites: s.gps.satellites, fix: true },
  }
}

// Mirrors the shape of backend's /ws envelope `data` field (gas/load/gps)
// so App.jsx doesn't need to know whether it's reading real or demo data.
export function useMockData(intervalMs = 1000) {
  const [data, setData] = useState(seed)
  const ref = useRef(data)

  useEffect(() => {
    const id = setInterval(() => {
      ref.current = step(ref.current)
      setData(ref.current)
    }, intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])

  return data
}
