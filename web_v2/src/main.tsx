import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import App from './App'
import { SharedRoundPage } from './components/SharedRoundPage'

const sharedToken = window.location.pathname.startsWith('/s/')
  ? window.location.pathname.slice('/s/'.length).split('/')[0]
  : null
const root = createRoot(document.getElementById('root')!)

if (sharedToken !== null) {
  root.render(
    <StrictMode>
      <SharedRoundPage token={sharedToken} />
    </StrictMode>,
  )
} else {
  root.render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}
