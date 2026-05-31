import React from 'react'

const ICONS = {
  beauty_fashion  : '💄',
  lifestyle       : '🌿',
  fitness_health  : '💪',
  food_gastronomy : '🍽️',
  technology      : '💻',
  gaming          : '🎮',
  travel          : '✈️',
  finance_business: '📈',
  entertainment   : '🎬',
  sports          : '⚽',
}

const LABELS = {
  beauty_fashion  : 'Beauty & Fashion',
  lifestyle       : 'Lifestyle',
  fitness_health  : 'Fitness & Health',
  food_gastronomy : 'Food & Gastronomy',
  technology      : 'Technology',
  gaming          : 'Gaming',
  travel          : 'Travel',
  finance_business: 'Finance & Business',
  entertainment   : 'Entertainment',
  sports          : 'Sports',
}

const COLORS = ['#7c6ef9', '#a78bfa', '#38bdf8']

export default function CampaignPanel({ closest, top3 }) {
  const maxW = top3[0]?.weight ?? 1

  return (
    <div className="camp-panel">
      <div className="camp-left">
        <div className="camp-lbl">AI Kampanya Analizi</div>
        <div className="camp-name">
          {ICONS[closest] ?? '🎯'}&nbsp;&nbsp;{LABELS[closest] ?? closest}
        </div>
        <div className="camp-sub">En uygun kampanya kategorisi</div>
      </div>

      <div className="camp-right">
        {top3.map((c, i) => (
          <div key={c.campaign} className="camp-bar-row">
            <div className="cb-name">
              {ICONS[c.campaign] ?? '·'}&nbsp;{LABELS[c.campaign] ?? c.campaign}
            </div>
            <div className="cb-track">
              <div
                className="cb-fill"
                style={{
                  width:      `${((c.weight / maxW) * 100).toFixed(1)}%`,
                  background: COLORS[i],
                }}
              />
            </div>
            <div className="cb-pct">{(c.weight * 100).toFixed(1)}%</div>
          </div>
        ))}
      </div>
    </div>
  )
}
