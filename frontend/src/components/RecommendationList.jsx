// Renders the triage `recommendations` array. Each recommendation has a `kind`
// that drives its visual treatment:
//   action  -> neutral/default suggestion
//   proceed -> accent (good to advance to Stage 2)
//   caution -> warn (something to watch before proceeding)
//   info    -> muted background note
const KIND_META = {
  action: { cls: 'rec-action', icon: '•' },
  proceed: { cls: 'rec-proceed', icon: '→' },
  caution: { cls: 'rec-caution', icon: '!' },
  info: { cls: 'rec-info', icon: 'i' },
}

export default function RecommendationList({ recommendations }) {
  if (!Array.isArray(recommendations) || recommendations.length === 0) return null

  return (
    <div className="rec-list">
      <span className="stage-label">Recommendations</span>
      {recommendations.map((rec, i) => {
        const meta = KIND_META[rec.kind] || KIND_META.action
        return (
          <div className={`rec-card ${meta.cls}`} key={`${rec.title}-${i}`}>
            <span className="rec-icon">{meta.icon}</span>
            <div className="rec-text">
              <div className="rec-title">{rec.title}</div>
              {rec.detail && <div className="rec-detail">{rec.detail}</div>}
            </div>
          </div>
        )
      })}
    </div>
  )
}
