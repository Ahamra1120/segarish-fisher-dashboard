import { Camera, CameraOff, Compass, Fish, Scale, Wind } from 'lucide-react'
import { useEffect, useState } from 'react'
import { CompassRose } from './components/CompassRose.jsx'
import { Meter } from './components/Meter.jsx'
import { ConnBadge, Spark, StatusChip } from './components/ui.jsx'
import { useClock } from './hooks/useClock.js'
import { useHistorySeries } from './hooks/useHistory.js'
import { useSocket } from './hooks/useSocket.js'

const STATUS_LABEL = { baik: 'Baik', sedang: 'Sedang', buruk: 'Buruk', unknown: 'Belum kalibrasi' }
const STATUS_CLASS = { baik: 'good', sedang: 'warning', buruk: 'critical', unknown: 'neutral' }
const STATUS_COLOR = {
  baik: 'var(--status-good)',
  sedang: 'var(--status-warning)',
  buruk: 'var(--status-critical)',
  unknown: 'var(--text-2)',
}

const DEFAULT_UI_CONFIG = { gas_warn_ppm: 400, gas_danger_ppm: 1000, load_capacity_kg: 50 }

export default function App() {
  const { envelope, wsConnected } = useSocket()
  const now = useClock()
  const [uiConfig, setUiConfig] = useState(DEFAULT_UI_CONFIG)
  const [taring, setTaring] = useState(false)

  useEffect(() => {
    fetch('/api/config')
      .then((r) => r.json())
      .then((c) => setUiConfig((prev) => ({ ...prev, ...c })))
      .catch(() => {})
  }, [])

  const connected = wsConnected && envelope.connected
  const stale = envelope.stale || !wsConnected
  const data = envelope.data || {}
  const gas = data.gas
  const load = data.load
  const gps = data.gps
  const camera = data.camera

  const gasSeries = useHistorySeries('gas', 'ppm_est', { minutes: 8, maxPoints: 30 })
  const loadSeries = useHistorySeries('load', 'kg', { minutes: 8, maxPoints: 30 })

  const gasLevel = gas?.level || 'unknown'
  const gasPpm = gas?.ppm_est ?? 0
  const gasScaleMax = Math.max(uiConfig.gas_danger_ppm * 1.2, 1)

  const loadKg = load?.kg ?? 0
  const loadCapacity = uiConfig.load_capacity_kg || 50
  const loadPct = Math.round((Math.max(0, loadKg) / loadCapacity) * 100)
  const loadOver = loadKg > loadCapacity

  async function handleTare() {
    setTaring(true)
    try {
      await fetch('/api/load/tare', { method: 'POST' })
    } catch {
      // transient network hiccup -- the fisher can just tap tare again
    } finally {
      setTaring(false)
    }
  }

  const camAge = camera?.last_capture_ts ? now.getTime() / 1000 - camera.last_capture_ts : Infinity
  const camFresh = camera?.available && camAge < 15
  const camSrc = camFresh ? `/api/camera/snapshot.jpg?t=${Math.floor(now.getTime() / 2000)}` : null

  return (
    <div className="kiosk">
      <header className="kiosk-header">
        <div className="brand-mark">
          <div className="brand-logo">
            <Fish size={18} />
          </div>
          <div>
            <div className="brand-name">SEGARISH</div>
            <div className="brand-sub">Fisher Dashboard</div>
          </div>
        </div>
        <div className="kiosk-header-spacer" />
        <ConnBadge connected={connected} stale={stale} />
        <div className="clock">
          <div className="time mono">{now.toLocaleTimeString('id-ID', { hour12: false })}</div>
          <div className="date">{now.toLocaleDateString('id-ID', { weekday: 'short', day: '2-digit', month: 'short' })}</div>
        </div>
      </header>

      <div className="kiosk-grid">
        {/* --- Gas quality (MQ135) --- */}
        <section className="panel">
          <div className="panel-head">
            <div className="panel-icon">
              <Wind size={14} color="var(--brand)" />
            </div>
            <div>
              <div className="panel-title">Kualitas Udara</div>
              <div className="panel-sub">Sensor MQ135</div>
            </div>
            <div className="panel-head-spacer" />
            <StatusChip status={STATUS_CLASS[gasLevel]}>{STATUS_LABEL[gasLevel]}</StatusChip>
          </div>
          <div className="panel-body">
            <Meter value={gasPpm} min={0} max={gasScaleMax} fillColor={STATUS_COLOR[gasLevel]}>
              <div className="meter-center">
                <div className="v">{gas?.ppm_est != null ? Math.round(gas.ppm_est) : '—'}</div>
                <div className="u">ppm est.</div>
              </div>
            </Meter>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="hero-label">Tegangan sensor</div>
              <div className="row between" style={{ marginBottom: 6 }}>
                <span className="mono" style={{ fontWeight: 700, fontSize: 15 }}>
                  {gas?.voltage != null ? `${gas.voltage.toFixed(2)} V` : '—'}
                </span>
              </div>
              <div className="spark-block">
                <div className="sb-head">
                  <span>Tren 8 menit</span>
                </div>
                <Spark data={gasSeries} color={STATUS_COLOR[gasLevel]} />
              </div>
            </div>
          </div>
        </section>

        {/* --- Load cell --- */}
        <section className="panel">
          <div className="panel-head">
            <div className="panel-icon">
              <Scale size={14} color="var(--brand)" />
            </div>
            <div>
              <div className="panel-title">Berat Muatan</div>
              <div className="panel-sub">Load cell (HX711)</div>
            </div>
            <div className="panel-head-spacer" />
            <button className="btn" onClick={handleTare} disabled={taring}>
              {taring ? 'Tare…' : 'Tare / Nol'}
            </button>
          </div>
          <div className="panel-body">
            <Meter
              value={loadKg}
              min={0}
              max={loadCapacity}
              fillColor={loadOver ? 'var(--status-critical)' : 'var(--brand)'}
              trackColor="color-mix(in srgb, var(--brand) 16%, var(--bg-3))"
            >
              <div className="meter-center">
                <div className="v">{loadKg.toFixed(1)}</div>
                <div className="u">kg</div>
              </div>
            </Meter>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="hero-label">Kapasitas terpakai</div>
              <div className="row between" style={{ marginBottom: 6 }}>
                <span className="mono" style={{ fontWeight: 700, fontSize: 15, color: loadOver ? 'var(--status-critical)' : 'inherit' }}>
                  {loadPct}% dari {loadCapacity} kg
                </span>
              </div>
              <div className="spark-block">
                <div className="sb-head">
                  <span>Tren 8 menit</span>
                </div>
                <Spark data={loadSeries} color="var(--brand)" />
              </div>
            </div>
          </div>
        </section>

        {/* --- GPS + heading --- */}
        <section className="panel">
          <div className="panel-head">
            <div className="panel-icon">
              <Compass size={14} color="var(--brand)" />
            </div>
            <div>
              <div className="panel-title">Posisi & Arah</div>
              <div className="panel-sub">Sologood M10 GPS</div>
            </div>
            <div className="panel-head-spacer" />
            <StatusChip status={gps?.fix ? 'good' : 'neutral'}>{gps?.fix ? `Fix · ${gps?.satellites ?? '—'} sat` : 'No fix'}</StatusChip>
          </div>
          <div className="panel-body">
            <CompassRose headingDeg={gps?.heading_deg} hasFix={gps?.fix} />
            <div className="gps-readout">
              <div className="gps-row">
                <span className="k">Lintang</span>
                <span className="v">{gps?.lat != null ? gps.lat.toFixed(5) : '—'}</span>
              </div>
              <div className="gps-row">
                <span className="k">Bujur</span>
                <span className="v">{gps?.lon != null ? gps.lon.toFixed(5) : '—'}</span>
              </div>
              <div className="gps-row">
                <span className="k">Kecepatan</span>
                <span className="v">{gps?.speed_kn != null ? `${gps.speed_kn.toFixed(1)} kn` : '—'}</span>
              </div>
              <div className="gps-row">
                <span className="k">Arah</span>
                <span className="v">{gps?.heading_deg != null ? `${Math.round(gps.heading_deg)}°` : '—'}</span>
              </div>
              <div className="heading-note">Arah dari GPS (course), bukan kompas magnetik</div>
            </div>
          </div>
        </section>

        {/* --- Camera --- */}
        <section className="panel">
          <div className="panel-head">
            <div className="panel-icon">
              <Camera size={14} color="var(--brand)" />
            </div>
            <div>
              <div className="panel-title">Kamera Tangkapan</div>
              <div className="panel-sub">IMX135 (CSI)</div>
            </div>
            <div className="panel-head-spacer" />
            <StatusChip status={camFresh ? 'good' : 'neutral'}>{camFresh ? 'Live' : 'Tidak ada frame'}</StatusChip>
          </div>
          <div className="panel-body" style={{ paddingTop: 0 }}>
            <div className="camera-frame">
              {camSrc ? (
                <img src={camSrc} alt="Cuplikan kamera" />
              ) : (
                <div className="cam-empty">
                  <CameraOff size={22} style={{ marginBottom: 6, opacity: 0.5 }} />
                  <div>Menunggu kamera…</div>
                </div>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
