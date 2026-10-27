/* 固定通信专栏独立跟踪；主看板回看或Top10换榜不改变本观察池。 */
(()=>{
  const root=document.getElementById('market-flow-replay'),panel=root.querySelector('.communications-section');
  const cfg=JSON.parse(root.querySelector('#communications-config').textContent);
  let model=null,chosen=cfg.items[0].id,snapshot=null;
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num=(v,suffix='')=>Number.isFinite(v)?`${v>0?'+':''}${v.toFixed(2)}${suffix}`:'—';
  const tone=v=>!Number.isFinite(v)?'muted':v>0?'positive':'negative';
  const dateLabel=t=>t?String(t).replace('T',' ').slice(5,16):'时间缺测';
  const rows=()=>model?.items?.length?model.items:cfg.items.map(item=>({...item,latest:{},stats:{},days:[],assessment:{label:'等待行情',tone:'muted',reason:'固定观察名单已载入，正在等待真实行情。'}}));
  function current(row){return Boolean(row.as_of?.startsWith(model?.target_date||'INVALID'));}
  function timely(row){
    if(!current(row))return false;
    const phase=snapshot?.market_session?.phase;
    if(phase==='trading')return new Date(snapshot.server_time)-new Date(row.as_of)<600000;
    if(['closed','preopen','closed_today'].includes(phase))return row.as_of.slice(11,16)>='15:00';
    return true;
  }
  function detail(){
    const row=rows().find(r=>r.id===chosen)||rows()[0];
    if(!row)return;
    panel.querySelectorAll('[data-communication]').forEach(el=>{
      const selected=el.dataset.communication===row.id;el.closest('tr').classList.toggle('selected',selected);el.setAttribute('aria-pressed',String(selected));
    });
    const funds=row.latest||{};
    const dates=model?.dates||[];
    const cells=dates.map(day=>{
      const value=(row.days||[]).find(d=>d.date===day)||{};
      return `<div class="comm-day"><time datetime="${esc(day)}">${esc(day.slice(5).replace('-','/'))}</time><strong class="${tone(value.pct_change)}">${num(value.pct_change,'%')}</strong><span class="${tone(value.main_net_inflow_yi)}">${num(value.main_net_inflow_yi)}</span></div>`;
    }).join('');
    const stocks=(row.stocks||[]).map(stock=>{
      const stale=!stock.as_of?.startsWith(model?.target_date||'INVALID');
      return `<a href="https://quote.eastmoney.com/${stock.code.startsWith('6')?'sh':'sz'}${esc(stock.code)}.html" target="_blank" rel="noopener noreferrer" title="${esc(stock.as_of||'报价未返回')}"><span>${esc(stock.name)} <small>${esc(stock.code)}</small></span><span>${Number.isFinite(stock.price)?stock.price.toFixed(2):'—'} <b class="${tone(stock.pct)}">${num(stock.pct,'%')}</b></span><small>${dateLabel(stock.as_of)}${stale?' · 缓存/缺测':''}</small></a>`;
    }).join('');
    panel.querySelector('.comm-detail').innerHTML=`<div class="comm-observation"><h3>${esc(row.name)} <span class="muted">${esc(row.role)}</span></h3><p>${esc(row.assessment?.reason||'等待数据')}</p><p class="comm-fund-split">${['xl','lg','md','sm'].map((key,i)=>`${['超大','大单','中单','小单'][i]} <b class="${tone(funds[key])}">${num(funds[key])}</b>`).join('　')}</p><div class="comm-days" aria-label="${esc(row.name)}最近5个交易日涨幅和主力净额">${cells||'<span class="muted">历史数据待获取</span>'}</div></div><div class="comm-research"><h3>持续投入前，跟踪什么</h3><p>${esc(row.watch)}</p><p class="muted">观察风险：${esc(row.risk)}</p><a class="comm-source" href="${esc(row.source_url)}" target="_blank" rel="noopener noreferrer">产业资料：${esc(row.source_title)} ↗</a></div><div class="comm-stock-list"><h3>代表股观察 <span class="muted">非推荐组合</span></h3>${stocks}</div>`;
    panel.querySelector('.comm-detail').dataset.focusId=row.id;
  }
  function render(incoming){
    snapshot=incoming||snapshot;
    model=snapshot?.sections?.communications?.data||null;
    const section=snapshot?.sections?.communications;
    const list=rows(),valid=list.filter(timely),flows=valid.filter(r=>Number.isFinite(r.latest?.main));
    panel.dataset.sourceAsOf=section?.as_of||'';
    const sectionCached=section&&!['ok','cached_close'].includes(section.status);
    const stale=list.filter(r=>r.quote_status!=='ok'||!timely(r));
    const times=valid.map(r=>r.as_of).sort();
    panel.querySelector('.comm-asof').textContent=times.length?`行情 ${dateLabel(times[0])}${times.at(-1).slice(11,16)!==times[0].slice(11,16)?'—'+times.at(-1).slice(11,16):''}${stale.length?' · '+stale.length+'方向缓存/缺测':sectionCached?' · 缓存':''}`:'固定名单 · 行情待获取或更新';
    const historyFull=list.filter(r=>r.stats?.flow_coverage===5&&r.stats?.pct_coverage===5).length;
    panel.querySelector('.comm-summary').innerHTML=valid.length?`<strong>${valid.filter(r=>r.pct>0).length}/${list.length}</strong> 方向上涨　<strong>${flows.filter(r=>r.latest.main>0).length}/${flows.length}</strong> 有资金数据的方向净流入　<span class="muted">5日价资均完整：${historyFull}/${list.length} · ${snapshot?.market_session?.phase==='trading'||snapshot?.market_session?.phase==='lunch'?'含今日盘中':'按各日已获取行情'} · 刷新不改变关注名单</span>`:'固定跟踪六条产业链方向，不要求进入当日涨幅Top10。';
    const ranked=list.filter(r=>current(r)&&Number.isFinite(r.stats?.pct_5d)).slice().sort((a,b)=>b.stats.pct_5d-a.stats.pct_5d);
    const full=list.filter(r=>timely(r)&&r.stats?.pct_coverage===5&&r.stats?.flow_coverage===5);
    const improving=full.filter(r=>r.stats.pct_5d>0&&r.stats.flow_5d>0);
    panel.querySelector('.comm-relative').textContent=full.length===list.length&&full.every(r=>r.stats.pct_5d<0&&r.stats.flow_5d<0)?'观察结论：六个方向的5日价格与资金仍偏弱，当日回流先按修复观察；持续投入前，等待多日资金与价格同步改善。':improving.length?`5日价格与资金同向改善：${improving.map(r=>r.name).join('、')}；继续核实产业兑现及回踩承接。`:ranked.length?`同一5日窗口内相对抗跌或较强：${ranked.slice(0,2).map(r=>`${r.name} ${num(r.stats.pct_5d,'%')}`).join(' / ')}；价格与资金尚未形成一致的持续信号。`:'5日历史尚不完整，暂不排列持续性强弱；单日资金流入只作为观察线索。';
    panel.querySelector('.comm-table tbody').innerHTML=list.map(row=>{
      const stats=row.stats||{},value=row.latest?.main;
      return `<tr data-focus-row="${esc(row.id)}" data-asof="${esc(row.as_of||'')}"><td><button class="comm-select" type="button" data-communication="${esc(row.id)}" title="行情 ${esc(row.as_of||'未获取')}">${esc(row.name)}</button><small>${esc(row.role)}${row.quote_status==='cached'?' · 缓存':''}</small></td><td class="${tone(row.pct)}">${num(row.pct,'%')}</td><td class="${tone(value)}">${num(value)}</td><td class="${tone(stats.pct_5d)}">${num(stats.pct_5d,'%')}<small>${stats.pct_coverage??0}/5日</small></td><td class="${tone(stats.flow_5d)}">${num(stats.flow_5d)}<small>${stats.flow_coverage??0}/5日</small></td><td>${Number.isFinite(stats.inflow_days)?stats.inflow_days+'/5':'—'}</td><td><span class="comm-state ${esc(!timely(row)?'muted':row.assessment?.tone||'muted')}">${!timely(row)?'行情待更新':esc(row.assessment?.label||'等待行情')}</span></td></tr>`;
    }).join('');
    panel.querySelector('.comm-scope').textContent=cfg.classification+' 5日累计涨幅按日收益复合计算；资金按日净额相加，任一天缺测则累计值显示“—”。';
    panel.querySelector('.comm-health').textContent=sectionCached?'本轮使用已保存行情及原数据时间，不把缓存解释为最新信号。':stale.length?'部分方向使用已核验缓存，保留原行情时间；点击方向查看明细。':'点击方向查看四档资金、5日明细与产业观察点。';
    if(!globalThis.INDUSTRY_LIVE_MODE)panel.querySelector('.comm-health').textContent+=' 当前为静态快照，不自动刷新。';
    detail();
  }
  panel.querySelector('.comm-table').addEventListener('click',event=>{const button=event.target.closest('[data-communication]');if(button){chosen=button.dataset.communication;detail();}});
  document.addEventListener('industry:data',event=>render(event.detail));
  render(JSON.parse(root.querySelector('#industry-market-data').textContent));
})();
