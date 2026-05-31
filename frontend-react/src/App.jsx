import React, { useState } from 'react'
import axios from 'axios'
import InfluencerCard from './components/InfluencerCard'
import CampaignPanel  from './components/CampaignPanel'
import SkeletonCard   from './components/SkeletonCard'
import StatsBar       from './components/StatsBar'
import './App.css'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:5001'

const SORTS = [
  { key:'final_score',  label:'En uygun' },
  { key:'sfs',          label:'İçerik uyumu' },
  { key:'NFS',          label:'Performans' },
  { key:'cfs',          label:'Kampanya uyumu' },
  { key:'fake_followers_risk', label:'Düşük risk', mode:'risk' },
]

const TECHS = ['SBERT Semantik', 'Turkish BERT Duygu', 'XGBoost', 'Item-based CF', 'K-Means']

const sourceBonus = source => source === 'instagram' ? 3 : 0
const numericValue = value => Number.isFinite(Number(value)) ? Number(value) : 0
const sortValue = (item, sort) => {
  const finalScore = numericValue(item.final_score)
  const bonus = sourceBonus(item.data_source)
  if (sort.mode === 'risk') {
    return (100 - numericValue(item.fake_followers_risk)) * 0.65 + finalScore * 0.35 + bonus
  }
  if (sort.key === 'final_score') return finalScore + bonus
  return numericValue(item[sort.key]) * 0.65 + finalScore * 0.35 + bonus
}

export default function App() {
  const [brandText, setBrandText] = useState('')
  const [topN,      setTopN]      = useState(10)
  const [results,   setResults]   = useState([])
  const [meta,      setMeta]      = useState(null)
  const [loading,   setLoading]   = useState(false)
  const [error,     setError]     = useState('')
  const [sortKey,   setSortKey]   = useState('final_score')
  const [onlyInstagram, setOnlyInstagram] = useState(false)

  const run = async () => {
    if (!brandText.trim()) { setError('Marka metni zorunludur.'); return }
    setLoading(true); setError(''); setResults([]); setMeta(null)
    try {
      const { data } = await axios.post(`${API_BASE}/recommend`, {
        brand_text: brandText,
        top_n: Math.max(1, Math.min(50, topN)),
      })
      if (data.success) {
        setResults(data.recommendations || [])
        setMeta({ closest: data.closest_campaign, top3: data.top3_campaigns || [] })
        setSortKey('final_score')
        setOnlyInstagram(false)
      } else setError(data.error || 'Eşleştirme başarısız.')
    } catch (e) {
      setError(e.response?.data?.error || 'Sunucu bağlantı hatası.')
    } finally { setLoading(false) }
  }

  const activeSort = SORTS.find(s => s.key === sortKey) || SORTS[0]
  const visibleResults = onlyInstagram
    ? results.filter(item => item.data_source === 'instagram')
    : results

  const sorted = [...visibleResults].sort((a, b) => {
    return sortValue(b, activeSort) - sortValue(a, activeSort)
  })

  return (
    <>
      {/* ── Top bar ── */}
      <header className="topbar">
        <div className="tb-brand">
          <div className="tb-logo">✦</div>
          Fenomen–Marka Eşleştirme
        </div>
        <div className="tb-badge">TÜBİTAK 2209-A</div>
      </header>

      {/* ── Stats ribbon ── */}
      <StatsBar />

      {/* ── Search hero ── */}
      <section className="search-section">
        <div className="search-inner">
          <div className="search-eyebrow">
            <span className="eyebrow-dot" />
            AI Destekli · Canlı Demo
          </div>

          <h1 className="hero-title">
            Marka Metninden<br />
            <em>Fenomen Keşfet</em>
          </h1>

          <p className="hero-desc">
            Kampanya metninizi yazın; yapay zeka en uygun fenomenleri sıralasın.
          </p>

          <div className="tech-chips">
            {TECHS.map(t => <span key={t} className="tech-chip">{t}</span>)}
          </div>

          <div className="search-box">
            <textarea
              rows={4}
              placeholder="Markanızın kampanya metnini buraya yazın...  (Ctrl+Enter ile ara)"
              value={brandText}
              onChange={e => setBrandText(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && e.ctrlKey && run()}
            />
            <div className="search-footer">
              <span className="hint"><kbd>Ctrl</kbd> + <kbd>Enter</kbd> ile ara</span>
              <div className="n-control">
                <span>Sonuç:</span>
                <input
                  type="number" min={1} max={50} value={topN}
                  onChange={e => setTopN(Math.max(1, Math.min(50, +e.target.value)))}
                />
              </div>
              <button className="cta-btn" onClick={run} disabled={loading}>
                {loading ? <><span className="spinner" />Analiz ediliyor</> : 'Fenomen Bul'}
              </button>
            </div>
            {error && <p className="err-msg">⚠ {error}</p>}
          </div>
        </div>
      </section>

      {/* ── Results ── */}
      <main className="main">
        {meta && <CampaignPanel {...meta} />}

        {loading && (
          <div className="cards-grid">
            {Array.from({ length: Math.min(topN, 6) }).map((_, i) => <SkeletonCard key={i} />)}
          </div>
        )}

        {!loading && sorted.length > 0 && (
          <>
            <div className="sort-bar">
              <div className="sort-heading">
                <span className="sort-label">Önerileri göster</span>
                <span className="sort-sub">Karar kriterine göre sıralayın veya sadece gerçek Instagram verilerini görün.</span>
              </div>
              {SORTS.map(o => (
                <button
                  key={o.key}
                  className={`sort-chip${sortKey === o.key ? ' active' : ''}`}
                  onClick={() => setSortKey(o.key)}
                >
                  {o.label}
                </button>
              ))}
              <button
                className={`sort-chip source-toggle${onlyInstagram ? ' active' : ''}`}
                onClick={() => setOnlyInstagram(v => !v)}
              >
                Sadece Instagram
              </button>
              <span className="res-count"><b>{sorted.length}</b> / {results.length} fenomen</span>
            </div>

            <div className="cards-grid">
              {sorted.map((inf, idx) => (
                <InfluencerCard
                  key={inf.influencer_name}
                  rank={idx + 1}
                  data={inf}
                />
              ))}
            </div>
          </>
        )}
      </main>
    </>
  )
}
