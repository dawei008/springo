import React from 'react'
import ReactDOM from 'react-dom/client'
import './styles/variables.css'
import './styles/global.css'
import './styles/components.css'
import App from './App'
import './devHook'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
