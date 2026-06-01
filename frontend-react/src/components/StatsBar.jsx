import React, { useEffect, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || ''

const PILLS = [
  { icon: '👤', valKey: 'total_influencers', lbl: 'Fenomen',    fmt: v => v },
  { icon: '📊', valKey: 'avg_NFS',           lbl: 'Ort. NFS',   fmt: v => v?.toFixed(1) },
  { icon: '💬', valKey: 'avg_engagement',    lbl: 'Ort. Etkil.', fmt: v => v ? `%${v}` : '—' },
  { icon: '🤖', valKey: '_accuracy',         lbl: 'XGBoost',    fmt: () => '%83.2' },
  { icon: '🔗', valKey: 'total_influencers',  lbl: 'CF Matrisi', fmt: v => v ? `${v}×${v}` : '—' },
]

export default function StatsBar() {
  const [data, setData] = useState(null)

  useEffect(() => {
    fetch(`${API_BASE}/api/stats`)
      .then(r => r.json())
      .then(d => setData(d))
      .catch(() => {})
  }, [])

  return (
    <div className="stats-ribbon">
      {PILLS.map(p => (
        <div key={p.lbl} className="stat-pill">
          <span className="stat-pill-icon">{p.icon}</span>
          <div className="stat-pill-info">
            <div className="stat-pill-val">
              {data ? p.fmt(data[p.valKey]) : '…'}
            </div>
            <div className="stat-pill-lbl">{p.lbl}</div>
          </div>
        </div>
      ))}
    </div>
  )
}
