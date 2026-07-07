import { createContext, useContext, useEffect, useState } from 'react'

// Holds the "current issue" so the Triage page can hand an issue + its triage
// result off to the Code-fix page. Persisted to localStorage so the title/body
// (and triage result) survive a page refresh.
const IssueContext = createContext(null)
const STORAGE_KEY = 'agenclave_issue'
// fixtureId is set when the issue was loaded from a practice-bug fixture; the
// Code-fix run passes it so the agents get shown the file and are verified.
// runResult holds the last Code-fix pipeline result so it survives switching
// sections (it is cleared only by the Clear button, not by navigation).
const EMPTY = { title: '', body: '', triage: null, fixtureId: null, runResult: null }

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return { ...EMPTY, ...JSON.parse(raw) }
  } catch {
    /* ignore corrupt/unavailable storage */
  }
  return EMPTY
}

export function IssueProvider({ children }) {
  const [current, setCurrent] = useState(load)

  // Persist across refreshes.
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(current))
    } catch {
      /* ignore */
    }
  }, [current])

  // Replace the whole current issue (used for the Triage -> Code-fix hand-off).
  // A fresh issue starts with no run result.
  function setIssue({ title = '', body = '', triage = null, fixtureId = null }) {
    setCurrent({ title, body, triage, fixtureId, runResult: null })
  }

  // Update just the editable text (used by the Code-fix form).
  function patchIssue(partial) {
    setCurrent((c) => ({ ...c, ...partial }))
  }

  // Keep (or clear) the last Code-fix run result across section switches.
  function setRunResult(runResult) {
    setCurrent((c) => ({ ...c, runResult }))
  }

  // Clear the issue and forget it (the Clear button on both pages).
  function clearIssue() {
    setCurrent(EMPTY)
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      /* ignore */
    }
  }

  return (
    <IssueContext.Provider
      value={{ current, setIssue, patchIssue, setRunResult, clearIssue }}
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
