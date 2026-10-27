import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import App from './App'
import { SharedRoundPage } from './components/SharedRoundPage'

const sharedMatch = window.location.pathname.match(/^\/s\/([^/]+)\/?$/)
const root = createRoot(document.getElementById('root')!)

if (sharedMatch) {
  root.render(
    <StrictMode>
      <SharedRoundPage token={sharedMatch[1]} />
    </StrictMode>,
  )
} else {
  root.render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}
