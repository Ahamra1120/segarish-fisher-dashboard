import { useMockData } from './useMockData.js'
import { useSocket } from './useSocket.js'

// VITE_DEMO_MODE is a build-time flag (Vite inlines import.meta.env.* as
// a literal at build time and dead-code-eliminates the unused branch),
// so this condition never actually changes across renders -- only one
// of the two hooks below ever exists in the compiled bundle, which is
// what makes the "conditional" hook call below safe despite how it
// looks. Set VITE_DEMO_MODE=true in the deploy target's env (e.g.
// Vercel project settings) for a backend-less preview with demo data;
// leave it unset for the real Pi build, which talks to backend's /ws.
const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true'

export function useLiveData() {
  if (DEMO_MODE) {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const data = useMockData()
    return { data, demo: true }
  }
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const { envelope } = useSocket()
  return { data: envelope.data, demo: false }
}
