import { createContext, useContext, useState } from 'react'

// Holds the "current issue" so the Triage page can hand an issue + its triage
// result off to the Code-fix page without a round-trip through the URL.
const IssueContext = createContext(null)

export function IssueProvider({ children }) {
  const [current, setCurrent] = useState({ title: '', body: '', triage: null })

  // Replace the whole current issue (used for the Triage -> Code-fix hand-off).
  function setIssue({ title = '', body = '', triage = null }) {
    setCurrent({ title, body, triage })
  }

  // Update just the editable text (used by the Code-fix form).
  function patchIssue(partial) {
    setCurrent((c) => ({ ...c, ...partial }))
  }

  function clearIssue() {
    setCurrent({ title: '', body: '', triage: null })
  }

  return (
    <IssueContext.Provider
      value={{ current, setIssue, patchIssue, clearIssue }}
    >
      {children}
    </IssueContext.Provider>
  )
}

export function useIssue() {
  const ctx = useContext(IssueContext)
  if (!ctx) throw new Error('useIssue must be used within an IssueProvider')
  return ctx
}
