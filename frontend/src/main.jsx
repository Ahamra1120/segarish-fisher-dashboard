import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'

// Plus Jakarta Sans, self-hosted via @fontsource (files land in the built
// bundle, not fetched from Google Fonts at runtime) -- this page still has
// to render with zero internet access on the Pi. See README "No CDN, no
// map tiles -- why".
import '@fontsource/plus-jakarta-sans/500.css'
import '@fontsource/plus-jakarta-sans/600.css'
import '@fontsource/plus-jakarta-sans/700.css'
import '@fontsource/plus-jakarta-sans/800.css'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
