import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.jsx'
import { AuthProvider } from './auth/AuthContext'
import { IssueProvider } from './context/IssueContext'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <IssueProvider>
          <App />
        </IssueProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
