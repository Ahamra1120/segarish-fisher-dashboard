import { Fish, Navigation, Scale, Wind } from 'lucide-react'
import { useClock } from './hooks/useClock.js'
import { useSocket } from './hooks/useSocket.js'

// Numbers-only dashboard: no gauges, sparklines, compass graphic, camera
// feed, or connection/status badges -- just the current reading for each
// sensor, plain and centered. Data still comes over the same /ws feed;
// what changed is only how it's rendered. See README "Manual input" for
// how to drive these numbers by hand (POST /manual) instead of the
// simulator.
const fmt1 = (v) => (v != null ? Number(v).toFixed(1) : '—')
const fmt2 = (v) => (v != null ? Number(v).toFixed(2) : '—')
const fmt5 = (v) => (v != null ? Number(v).toFixed(5) : '—')
const fmtInt = (v) => (v != null ? Math.round(v) : '—')

export default function App() {
  const { envelope } = useSocket()
  const now = useClock()

  const data = envelope.data || {}
  const gas = data.gas
  const load = data.load
  const gps = data.gps

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
          </div>
          <div className="stat-body">
            <div className="stat-main">
              <span className="stat-num">{fmtInt(gas?.ppm_est)}</span>
              <span className="stat-unit">ppm est.</span>
            </div>
            <div className="stat-rows">
              <div className="stat-row">
                <span className="k">Tegangan</span>
                <span className="v">{gas?.voltage != null ? `${fmt2(gas.voltage)} V` : '—'}</span>
              </div>
              <div className="stat-row">
                <span className="k">Level</span>
                <span className="v">{gas?.level ?? '—'}</span>
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
          </div>
          <div className="stat-body">
            <div className="stat-main">
              <span className="stat-num">{fmt1(load?.kg)}</span>
              <span className="stat-unit">kg</span>
            </div>
            <div className="stat-rows">
              <div className="stat-row">
                <span className="k">Status</span>
                <span className="v">{load?.tared == null ? '—' : load.tared ? 'Sudah tare' : 'Belum tare'}</span>
              </div>
            </div>
          </div>
        </section>

        {/* --- GPS + heading --- */}
        <section className="panel panel-wide">
          <div className="panel-head">
            <div className="panel-icon">
              <Navigation size={14} color="var(--brand)" />
            </div>
            <div>
              <div className="panel-title">Posisi &amp; Arah</div>
              <div className="panel-sub">Sologood M10 GPS -- arah dari GPS (course), bukan kompas magnetik</div>
            </div>
          </div>
          <div className="stat-body">
            <div className="stat-rows stat-rows-grid">
              <div className="stat-row">
                <span className="k">Lintang</span>
                <span className="v">{fmt5(gps?.lat)}</span>
              </div>
              <div className="stat-row">
                <span className="k">Bujur</span>
                <span className="v">{fmt5(gps?.lon)}</span>
              </div>
              <div className="stat-row">
                <span className="k">Kecepatan</span>
                <span className="v">{gps?.speed_kn != null ? `${fmt1(gps.speed_kn)} kn` : '—'}</span>
              </div>
              <div className="stat-row">
                <span className="k">Arah</span>
                <span className="v">{gps?.heading_deg != null ? `${fmtInt(gps.heading_deg)}°` : '—'}</span>
              </div>
              <div className="stat-row">
                <span className="k">Satelit</span>
                <span className="v">{gps?.satellites ?? '—'}</span>
              </div>
              <div className="stat-row">
                <span className="k">Fix</span>
                <span className="v">{gps?.fix == null ? '—' : gps.fix ? 'Ya' : 'Tidak'}</span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
