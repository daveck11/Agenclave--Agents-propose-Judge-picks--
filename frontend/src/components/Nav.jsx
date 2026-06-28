import { NavLink } from 'react-router-dom'

const LINKS = [
  { to: '/', label: 'Triage', end: true },
  { to: '/code-fix', label: 'Code-fix' },
  { to: '/workspace', label: 'Workspace' },
]

export default function Nav() {
  return (
    <nav className="nav">
      {LINKS.map((l) => (
        <NavLink
          key={l.to}
          to={l.to}
          end={l.end}
          className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
        >
          {l.label}
        </NavLink>
      ))}
    </nav>
  )
}
