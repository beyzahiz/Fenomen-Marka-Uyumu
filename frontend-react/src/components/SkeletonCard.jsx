import React from 'react'

export default function SkeletonCard() {
  return (
    <div className="skeleton" style={{boxShadow:'var(--sh-sm)'}}>
      {/* header */}
      <div style={{display:'flex',gap:12,marginBottom:20}}>
        <div className="skel skel-rect" style={{width:38,height:38,flexShrink:0}}/>
        <div style={{flex:1}}>
          <div className="skel" style={{height:14,width:'52%',marginBottom:8}}/>
          <div style={{display:'flex',gap:6}}>
            <div className="skel" style={{height:18,width:56,borderRadius:99}}/>
            <div className="skel" style={{height:18,width:44,borderRadius:99}}/>
          </div>
        </div>
        <div className="skel skel-rect" style={{width:76,height:76,borderRadius:'50%',flexShrink:0}}/>
      </div>
      {/* divider */}
      <div className="skel" style={{height:1,borderRadius:0,marginBottom:16,opacity:.5}}/>
      {/* 2x2 grid */}
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'8px 16px',marginBottom:16}}>
        {[0,1,2,3].map(i=>(
          <div key={i}>
            <div style={{display:'flex',justifyContent:'space-between',marginBottom:6}}>
              <div className="skel" style={{height:10,width:28}}/>
              <div className="skel" style={{height:10,width:24}}/>
            </div>
            <div className="skel" style={{height:6}}/>
          </div>
        ))}
      </div>
      {/* stats */}
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:6}}>
        {[0,1,2,3].map(i=>(
          <div key={i} className="skel skel-rect" style={{height:50}}/>
        ))}
      </div>
    </div>
  )
}
