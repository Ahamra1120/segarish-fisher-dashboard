import { useEffect, useRef, useState } from 'react'

// Connects to backend's /ws (relative URL -- works both under the Vite
// dev proxy and same-origin in production), with auto-reconnect and
// exponential backoff. `envelope` is backend's { connected, stale,
// fetched_at, data } -- connected/stale describe the backend<->
// sensor-service link; `wsConnected` here separately tracks the
// browser<->backend link, so the UI can tell the two apart if needed.
export function useSocket() {
  const [envelope, setEnvelope] = useState({ connected: false, stale: true, fetched_at: 0, data: null })
  const [wsConnected, setWsConnected] = useState(false)
  const retryDelay = useRef(1000)

  useEffect(() => {
    let ws
    let closedByUs = false
    let retryTimer

    function connect() {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
      ws = new WebSocket(`${proto}//${location.host}/ws`)

      ws.onopen = () => {
        setWsConnected(true)
        retryDelay.current = 1000
      }
      ws.onmessage = (evt) => {
        try {
          setEnvelope(JSON.parse(evt.data))
        } catch {
          // ignore malformed frame
        }
      }
      ws.onclose = () => {
        setWsConnected(false)
        if (!closedByUs) {
          retryTimer = setTimeout(connect, retryDelay.current)
          retryDelay.current = Math.min(retryDelay.current * 1.6, 15000)
        }
      }
      ws.onerror = () => ws.close()
    }

    connect()
    return () => {
      closedByUs = true
      clearTimeout(retryTimer)
      ws && ws.close()
    }
  }, [])

  return { envelope, wsConnected }
}
