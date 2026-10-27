    function mountRanking(root,sectionKey){
      const page=document.getElementById('market-flow-replay'),flowOnly=sectionKey==='fund_concepts';
      if(!globalThis.d3){if(!flowOnly)page.querySelector('.clock').textContent='图表未加载';return;}
      const d=globalThis.d3;
      const fundModel=globalThis.IndustryFundReplay;
      const live=flowOnly||!globalThis.INDUSTRY_DEMO_MODE,continuous=Boolean(globalThis.INDUSTRY_LIVE_MODE);
      let liveSnapshot=null;
      let news=JSON.parse(page.querySelector('#industry-news-data').textContent);
      let history=JSON.parse(page.querySelector('#industry-history-data').textContent);
      let breadth=JSON.parse(page.querySelector('#industry-breadth-data').textContent);
      const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
      function renderNews(){
      if(flowOnly)return;
      const checked=new Date(news.checked_at);
      root.querySelector('.news-asof').textContent=`${news.window_label} · ${live?'获取至':'核验至'} ${new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(checked)} 北京时间`;
      ['domestic','overseas'].forEach(region=>{
        root.querySelector(`[data-region="${region}"] .news-list`).innerHTML=news.items.filter(n=>n.region===region).slice(0,3).map(n=>`<article class="news-item"><div class="news-meta"><time datetime="${esc(n.published_at)}">${esc(n.published_label)}</time><span class="news-tag">${esc(n.category)}</span><span>${esc(n.source)}</span></div><a href="${esc(n.url)}" target="_blank" rel="noopener noreferrer">${esc(n.title)}</a><p>${esc(n.summary)}</p></article>`).join('');
      });
      }
      renderNews();
      const definitions=[
        ['CPO概念',[0,18,45,52,43,36,45,56],7.5,'#a51f34',null],
        ['PCB',[0,4,12,20,16,22,29,38],6.8,'#bf4656','6 2'],
        ['存储芯片',[0,9,14,12,10,17,24,28],5.6,'#8b172b','2 2'],
        ['固态电池',[0,-5,-1,7,11,12,14,18],3.8,'#d06c78','8 3 2 3'],
        ['创新药',[0,-1,-4,-8,-9,-7,-11,-15],3.4,'#6e6b67','6 2'],
        ['AI芯片',[0,10,14,4,-5,-13,-18,-22],5.0,'#44413e','2 2'],
        ['商业航天',[0,-12,-18,-16,-22,-28,-33,-38],4.2,'#77736d','8 3 2 3'],
        ['液冷服务器',[0,-9,-24,-31,-39,-45,-48,-54],6.1,'#171717',null],
        ['人形机器人',[0,5,11,15,17,19,24,32],4.6,'#a63b4a','4 3'],
        ['铜缆高速连接',[0,-3,-8,-12,-15,-18,-20,-25],3.0,'#494846','9 3'],
        ['先进封装',[0,3,7,10,12,14,16,20],2.6,'#b04a58',null],
        ['稀土永磁',[0,-1,-3,-7,-8,-11,-13,-16],2.2,'#65615d','2 2'],
        ['光刻机',[0,2,4,7,8,9,11,13],1.8,'#b85663','5 2'],
        ['机器人执行器',[0,1,3,5,6,9,11,14],1.4,'#a86771',null],
        ['合成生物',[0,-1,-4,-6,-7,-9,-10,-12],1.2,'#8a8680','6 2']
      ];
      const positions=[0,25,55,90,120,155,200,240];
      const interp=(vals,t)=>{let j=1;while(j<positions.length-1&&positions[j]<t)j++;const f=(t-positions[j-1])/(positions[j]-positions[j-1]);return vals[j-1]+(vals[j]-vals[j-1])*f;};
      let sectors=live?[]:definitions.map((v,j)=>({id:j,name:v[0],pct:v[2],color:v[3],dash:v[4],values:Array.from({length:241},(_,i)=>{
        const noise=(Math.sin(i*.22+j)+.45*Math.sin(i*.53+j*2))*Math.sin(Math.PI*i/240)*1.2;
        const main=interp(v[1],i)+noise;
        const xl=main*.64+Math.sin(i/37+j)*i/240*2.2;
        const lg=main-xl;
        const md=-main*.38+Math.sin(i/45+j)*i/240*1.5;
        return {t:i,main,xl,lg,md,sm:-main-md};
      })}));
      let minute=240,selected=0,playing=false,frame=null,lastTick=0,elapsed=0,closingReplay=false;
      let fundReview=false,fundLimit=240,fundSection=null,fundDay='',fundDrag=false;
      const styles=new Map();
      function styleFor(id){
        if(!styles.has(id)){const item=definitions[styles.size%definitions.length];styles.set(id,{color:item[3],dash:item[4]});}
        return styles.get(id);
      }
      const pctAt=(s,t=minute)=>live?s.pct:s.pct*t/240+Math.sin(Math.PI*t/240)*Math.sin(s.id*1.3)*2.2;
      let ranked=[];
      const rankThemes=()=>{const t=closingReplay?240:minute;ranked=[...sectors].sort((a,b)=>(flowOnly?(b.ranking_main??b.latest?.main??-Infinity)-(a.ranking_main??a.latest?.main??-Infinity):pctAt(b,t)-pctAt(a,t))||String(a.id).localeCompare(String(b.id))).slice(0,10);if(ranked.length&&!ranked.some(s=>s.id===selected))selected=ranked[0].id;};
      const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
      const num=v=>Number.isFinite(v)?(v>0?'+':'')+v.toFixed(2):'—';
      const fundAt=s=>live?fundModel.at(s.fundPoints,minute,fundReview):s.values[minute];
      const plotThrough=s=>live?fundModel.through(s.fundPoints,minute,fundReview):s.values.filter(v=>v.t<=minute);
      const time=t=>{const m=t<=120?570+t:780+t-120;return String(Math.floor(m/60)).padStart(2,'0')+':'+String(m%60).padStart(2,'0');};
      const elSvg=root.querySelector('.main-plot');
      function breadthChart(){
        if(flowOnly)return;
        const el=root.querySelector('.breadth-plot'),width=el.getBoundingClientRect().width,height=190;
        const svg=d.select(el).attr('viewBox',`0 0 ${width} ${height}`);svg.selectAll('*').remove();
        const rows=(breadth.items||[]).slice(-30),left=54,right=8,top=20,bottom=30;
        if(!rows.length){svg.append('text').attr('x',left).attr('y',60).text('暂无已获取的涨跌家数记录');return;}
        const max=d.max(rows.flatMap(v=>[v.up,v.down]).filter(Number.isFinite))||1;
        const x=d.scaleBand().domain(rows.map(v=>v.date)).range([left,width-right]).padding(.22);
        const y=d.scaleLinear().domain([-max*1.08,max*1.08]).nice().range([height-bottom,top]);
        svg.append('rect').attr('data-chart-frame','').attr('x',left).attr('y',top).attr('width',width-left-right).attr('height',height-bottom-top).attr('fill','none').attr('stroke','#d9d5ce').attr('stroke-width',.6);
        for(const value of y.ticks(4)){
          svg.append('line').attr('x1',left).attr('x2',width-right).attr('y1',y(value)).attr('y2',y(value)).attr('stroke',value===0?'#9e9992':'#e6e2dc').attr('stroke-width',.6);
          svg.append('text').attr('x',left-7).attr('y',y(value)+3).attr('text-anchor','end').text(Math.abs(value));
        }
        rows.forEach(v=>{
          if(!Number.isFinite(v.up)||!Number.isFinite(v.down)){svg.append('text').attr('x',x(v.date)+x.bandwidth()/2).attr('y',y(0)-5).attr('text-anchor','middle').text('缺');return;}
          svg.append('rect').attr('class','breadth-up').attr('data-date',v.date).attr('x',x(v.date)).attr('width',x.bandwidth()).attr('y',y(v.up)).attr('height',y(0)-y(v.up)).attr('fill','var(--mf-red)').attr('opacity',.8);
          svg.append('rect').attr('class','breadth-down').attr('data-date',v.date).attr('x',x(v.date)).attr('width',x.bandwidth()).attr('y',y(0)).attr('height',y(-v.down)-y(0)).attr('fill','var(--mf-ink)').attr('opacity',.8);
        });
        const tickCount=width<480?4:8,indices=new Set(Array.from({length:tickCount},(_,i)=>Math.round(i*(rows.length-1)/(tickCount-1))));
        rows.forEach((v,i)=>{if(indices.has(i))svg.append('text').attr('x',x(v.date)+x.bandwidth()/2).attr('y',height-12).attr('text-anchor',i===0?'start':i===rows.length-1?'end':'middle').text(v.date.slice(5).replace('-','/'));});
        svg.append('text').attr('class','axis-title').attr('data-axis','y').attr('x',left).attr('y',11).text('上涨 ↑ / 下跌 ↓ · 家');
        svg.append('text').attr('class','axis-title').attr('data-axis','x').attr('x',width-right).attr('y',height-1).attr('text-anchor','end').text('交易日');
        const guide=svg.append('line').attr('y1',top).attr('y2',height-bottom).attr('stroke','#77736e').attr('stroke-width',1).attr('stroke-dasharray','2 2');
        const show=v=>{
          const observed=v.observed_at?` · ${v.observed_at.slice(11,16)}统计`:'';
          root.querySelector('.breadth-detail').innerHTML=`<span>${esc(v.date)}${v.provisional?' · 盘中':''}${observed}</span><span class="positive">上涨 ${v.up??'缺测'}</span><span>下跌 ${v.down??'缺测'}</span><span class="muted">平盘 ${v.flat??'—'}</span>`;
          guide.attr('x1',x(v.date)+x.bandwidth()/2).attr('x2',x(v.date)+x.bandwidth()/2);
        };
        const hit=svg.append('rect').attr('data-chart-hit','').attr('x',left).attr('y',top).attr('width',width-left-right).attr('height',height-top-bottom).attr('fill','transparent');
        hit.on('pointermove click',event=>{const px=d.pointer(event,el)[0];show(rows[Math.max(0,Math.min(rows.length-1,Math.floor((px-left)/(width-right-left)*rows.length)))]);});
        hit.on('pointerleave',()=>show(rows[rows.length-1]));show(rows[rows.length-1]);
        const last=rows[rows.length-1];
        root.querySelector('.breadth-source').textContent=`沪深A股 · 历史为收盘统计，最新日按数据源时间展示 · ${rows[0].date}—${last.date}${breadth.missing?` · ${breadth.missing}日缺测`:''} · 来源：乐咕乐股及已归档统计`;
      }
      function mainChart(){
        const width=elSvg.getBoundingClientRect().width,height=live&&!sectors.some(s=>s.fundPoints.length)?74:244;
        const left=43,top=14,bottom=30;
        const svg=d.select(elSvg).attr('viewBox',`0 0 ${width} ${height}`);svg.selectAll('*').remove();
        const all=sectors.flatMap(s=>(live?s.fundPoints:s.values).map(v=>v.main)).filter(Number.isFinite);
        if(!all.length){svg.append('text').attr('x',12).attr('y',55).text('概念榜或资金轨迹暂不可用 · 自动重试');return;}
        const visible=ranked.map((s,i)=>({s,j:s.id,rank:i+1,record:fundAt(s)})).filter(v=>Number.isFinite(v.record.main));
        const probe=svg.append('text').attr('class','end-label').attr('visibility','hidden');
        const labelRoom=Math.max(70,width-left-52-16);
        const measured=ranked.map((s,i)=>{
          let name=s.name;
          const largest=(live?s.fundPoints:s.values).reduce((a,v)=>Math.abs(v.main)>Math.abs(a)?v.main:a,0);
          const label=()=>`${String(i+1).padStart(2,'0')} ${name} ${num(largest)}*`;
          probe.text(label());
          while(probe.node().getComputedTextLength()>labelRoom&&name.length>3){name=name.endsWith('…')?name.slice(0,-2)+'…':name.slice(0,-1)+'…';probe.text(label());}
          return {id:s.id,name,width:probe.node().getComputedTextLength()};
        });
        visible.forEach(v=>{v.text=`${String(v.rank).padStart(2,'0')} ${measured.find(m=>m.id===v.s.id).name} ${num(v.record.main)}${v.record.kind==='quote'?'*':''}`;});
        probe.remove();
        const right=Math.min(width-left-52,Math.max(width<380?100:124,...measured.map(v=>v.width+16)));
        elSvg.dataset.plotStart=left;elSvg.dataset.plotEnd=width-right;elSvg.dataset.plotTop=top;elSvg.dataset.plotBottom=height-bottom;
        const x=d.scaleLinear().domain([0,240]).range([left,width-right]);
        const extent=d.extent(all),low=Math.min(0,extent[0]),high=Math.max(0,extent[1]),pad=Math.max((high-low)*.1,.1);
        const y=d.scaleLinear().domain([low-pad,high+pad]).nice().range([height-bottom,top]);
        const clipId='mf-flow-clip-'+sectionKey;svg.append('defs').append('clipPath').attr('id',clipId).append('rect').attr('x',left).attr('y',top).attr('width',Math.max(0,width-right-left)).attr('height',height-bottom-top);
        for(const value of y.ticks(5)){svg.append('line').attr('x1',left).attr('x2',width-right).attr('y1',y(value)).attr('y2',y(value)).attr('stroke',value===0?'#9e9992':'#e6e2dc').attr('stroke-width',value===0?1:0.6);svg.append('text').attr('x',left-7).attr('y',y(value)+3).attr('text-anchor','end').text(value>0?'+'+value:value);}
        const xticks=width<380?[0,120,240]:[0,60,120,180,240];
        xticks.forEach(t=>{svg.append('line').attr('x1',x(t)).attr('x2',x(t)).attr('y1',top).attr('y2',height-bottom).attr('stroke','#eeeae4').attr('stroke-width',.6);svg.append('text').attr('x',x(t)).attr('y',height-10).attr('text-anchor',t===0?'start':t===240?'end':'middle').text(t===120?'11:30/13:00':time(t));});
        const line=d.line().x(v=>x(v.t)).y(v=>y(v.main)).curve(d.curveLinear);
        if(visible.length){
          const chunks=s=>live?fundModel.segments(plotThrough(s)):[plotThrough(s)];
          [visible.reduce((a,b)=>a.record.main>b.record.main?a:b),visible.reduce((a,b)=>a.record.main<b.record.main?a:b)].forEach(({s})=>{chunks(s).filter(v=>v.length>1).forEach(values=>svg.append('path').attr('d',d.area().x(v=>x(v.t)).y0(y(0)).y1(v=>y(v.main))(values)).attr('clip-path',`url(#${clipId})`).attr('fill',s.color).attr('opacity',.055));});
          visible.forEach(({s})=>{const pieces=chunks(s);svg.append('path').attr('data-sector',s.id).attr('class','fund-curve').attr('d',pieces.filter(values=>values.length>1).map(values=>line(values)).join('')).attr('clip-path',`url(#${clipId})`).attr('fill','none').attr('stroke',s.color).attr('stroke-width',selected===s.id?2.5:1.5).attr('stroke-dasharray',live?null:s.dash);pieces.filter(values=>values.length===1).forEach(values=>svg.append('circle').attr('class','fund-sample').attr('data-sector',s.id).attr('cx',x(values[0].t)).attr('cy',y(values[0].main)).attr('r',1.6).attr('fill',s.color).attr('opacity',.5));});
        }
        svg.append('line').attr('x1',x(minute)).attr('x2',x(minute)).attr('y1',top).attr('y2',height-bottom).attr('stroke','#8b857e').attr('stroke-dasharray','3 4').attr('stroke-width',.7);
        const labels=visible.map(v=>({...v,value:v.record.main,py:y(v.record.main)})).sort((a,b)=>a.py-b.py);
        const gap=18;labels.forEach((v,i)=>{v.ly=Math.max(v.py,top+6,i?labels[i-1].ly+gap:top+6);});
        const excess=labels.length?labels[labels.length-1].ly-(height-bottom-3):0;if(excess>0){labels[labels.length-1].ly-=excess;for(let i=labels.length-2;i>=0;i--)labels[i].ly=Math.min(labels[i].ly,labels[i+1].ly-gap);}
        labels.forEach(v=>{
          const at=x(v.record.t??minute);
          svg.append('circle').attr('cx',at).attr('cy',v.py).attr('r',selected===v.j?3.5:2.5).attr('fill',v.record.kind==='quote'?'var(--mf-paper)':v.s.color).attr('stroke',v.s.color).attr('stroke-width',1);
          svg.append('text').attr('class','end-label').attr('data-sector',v.s.id).attr('data-fund-value',v.value).attr('data-record-asof',v.record.as_of||'').attr('data-fund-kind',v.record.kind||'series').attr('x',Math.min(x(minute)+11,width-right+11)).attr('y',v.ly+4).style('fill',v.s.color).text(v.text).append('title').text(`${v.s.name} ${num(v.value)}亿元 · ${v.record.as_of||time(v.record.t)}${v.record.kind==='quote'?' · 报价采样，非完整分钟轨迹':''}`);
        });
        svg.append('text').attr('x',left).attr('y',9).text('亿元');
      }
      function metrics(){
        if(flowOnly)return;
        if(live){liveMetrics();return;}
        const f=minute/240;const pct=interp([0,-.5,-1.3,-1.8,-1.2,.3,.8,1.2],minute);
        const names=['上证指数','深证成指','创业板指','沪深300','中证1000','科创50'];const base=[3600,11300,2600,4000,6500,1300];
        root.querySelector('.metrics').innerHTML=names.map((name,j)=>{const change=pct*(1+j*.27);return `<div class="metric"><div class="metric-name">${name}</div><div class="metric-value">${(base[j]*(1+change/100)).toFixed(2)}</div><span class="${change>=0?'positive':'negative'}">${num(change)}%</span><svg class="index-spark" data-index="${j}" role="img" aria-label="${name}当日分时涨跌示意"></svg></div>`;}).join('');
        root.querySelectorAll('.index-spark').forEach(el=>{const j=Number(el.dataset.index),width=el.getBoundingClientRect().width,height=31;
          const values=Array.from({length:241},(_,t)=>({t,v:interp([0,-.5,-1.3,-1.8,-1.2,.3,.8,1.2],t)*(1+j*.27)}));
          const ex=d.extent(values,v=>v.v),x=d.scaleLinear().domain([0,240]).range([1,width-10]),y=d.scaleLinear().domain([ex[0]-.2,ex[1]+.2]).range([height-2,2]);
          const svg=d.select(el).attr('viewBox',`0 0 ${width} ${height}`);svg.append('line').attr('x1',1).attr('x2',width-10).attr('y1',y(0)).attr('y2',y(0)).attr('stroke','#d9d5ce').attr('stroke-width',.6);
          svg.append('path').attr('d',d.area().x(v=>x(v.t)).y0(y(0)).y1(v=>y(v.v))(values.slice(0,minute+1))).attr('fill','#a51f34').attr('opacity',.07);
          svg.append('path').attr('d',d.line().x(v=>x(v.t)).y(v=>y(v.v))(values.slice(0,minute+1))).attr('stroke',pct>=0?'#a51f34':'#292725').attr('stroke-width',1.3).attr('fill','none');
        });
        const up=Math.round(2500+1500*f+500*Math.sin(f*5));
        root.querySelector('.tape').innerHTML=`<span>沪深成交额<b>${Math.round(19500*f)}</b> 亿元</span><span>上涨<b class="positive">${up}</b></span><span>下跌<b>${5000-up}</b><span class="breadth" aria-label="上涨占比${Math.round(up/50)}%"><span style="width:${up/50}%"></span></span></span><span>涨停 / 跌停<b>${Math.round(80*f)} / ${Math.round(12*f)}</b></span><span class="demo">模拟数值</span>`;
      }
      function liveMetrics(){
        const state=liveSnapshot?.sections||{},indices=state.indices?.data?.items||[];
        const codes=['sh000001','sz399001','sz399006','sh000300','sh000852','sh000688'];
        const names=['上证指数','深证成指','创业板指','沪深300','中证1000','科创50'];
        root.querySelector('.metrics').innerHTML=codes.map((code,j)=>{
          const item=indices.find(v=>v.id===code);
          return `<div class="metric"><div class="metric-name">${names[j]}</div><div class="metric-value">${Number.isFinite(item?.price)?item.price.toFixed(2):'—'}</div><span class="${item?.pct>=0?'positive':'negative'}">${num(item?.pct)}${Number.isFinite(item?.pct)?'%':''}</span><svg class="index-spark" data-index="${j}" role="img" aria-label="${names[j]}真实分时；无数据时留空"></svg></div>`;
        }).join('');
        root.querySelectorAll('.index-spark').forEach(el=>{
          const item=indices.find(v=>v.id===codes[Number(el.dataset.index)]),points=item?.points||[];
          const width=el.getBoundingClientRect().width,height=31,svg=d.select(el).attr('viewBox',`0 0 ${width} ${height}`);
          if(!points.length)return;
          const extent=d.extent(points,v=>v.v),pad=Math.max(.05,(extent[1]-extent[0])*.1),x=d.scaleLinear().domain([0,240]).range([1,width-5]),y=d.scaleLinear().domain([Math.min(0,extent[0])-pad,Math.max(0,extent[1])+pad]).range([height-2,2]);
          svg.append('line').attr('x1',1).attr('x2',width-5).attr('y1',y(0)).attr('y2',y(0)).attr('stroke','#d9d5ce').attr('stroke-width',.6);
          svg.append('path').attr('d',d.line().x(v=>x(v.t)).y(v=>y(v.v))(points)).attr('fill','none').attr('stroke',item.pct>=0?'var(--mf-red)':'var(--mf-ink)').attr('stroke-width',1.3);
        });
        const b=state.breadth?.data||{},amount=state.indices?.data?.turnover_yi;
        const count=v=>Number.isFinite(v)?String(v):'—';
        root.querySelector('.tape').innerHTML=`<span>沪深成交额<b>${Number.isFinite(amount)?amount.toFixed(0):'—'}</b> 亿元</span><span>上涨<b class="positive">${count(b.up)}</b></span><span>下跌<b>${count(b.down)}</b></span><span>平盘<b>${count(b.flat)}</b></span><span>涨停 / 跌停<b>${count(b.limit_up)} / ${count(b.limit_down)}</b></span><span class="muted">指数 ${esc(state.indices?.as_of?.replace('T',' ').slice(5,16)||'暂不可用')}${state.indices?.status==='cached_close'?' · 收盘缓存':state.indices?.status!=='ok'?' · 缓存或缺测':''}</span>`;
      }
      function table(){
        if(!ranked.length){root.querySelector('.fund-table tbody').innerHTML='<tr><td colspan="7" class="panel-state">概念榜取数暂不可用，自动重试；不以行业榜或模拟值代替。</td></tr>';return;}
        const maxPct=Math.max(...ranked.map(s=>Math.abs(pctAt(s))),.001);
        root.querySelector('.fund-table tbody').innerHTML=ranked.map((s,i)=>{
          const v=fundAt(s),pct=pctAt(s),note='';
          return `<tr class="${s.id===selected?'selected':''}" data-sector="${s.id}" data-fund-value="${Number.isFinite(v.main)?v.main:''}" data-record-asof="${esc(v.as_of||'')}" data-fund-kind="${v.kind||'series'}"><td><span class="rank-no" style="color:${s.color}">${String(i+1).padStart(2,'0')}</span><button class="name-button" type="button" data-sector="${s.id}">${esc(s.name)}</button>${note?`<span class="record-note">${esc(note)}</span>`:''}</td><td class="pct-cell ${pct>=0?'positive':'negative'}"><i class="pct-fill" style="width:${Math.abs(pct)/maxPct*100}%;background:${pct>=0?'#a51f34':'#292725'}"></i><span class="pct-value">${num(pct)}%</span></td>${['main','xl','lg','md','sm'].map(k=>`<td class="${!Number.isFinite(v[k])?'muted':v[k]>=0?'positive':'negative'}">${num(v[k])}</td>`).join('')}</tr>`;
        }).join('');
      }
      let historyKey='';
      function historyTable(){
        const key=(ranked.map(s=>s.id).join(',')||'empty')+(live?(liveSnapshot?.completed_at||liveSnapshot?.attempted_at||'initial'):'');
        if(key===historyKey)return;
        historyKey=key;
        const dates=history.dates.slice(-5);
        const maxPct=Math.max(...ranked.flatMap(s=>(history.boards.find(b=>b.id===s.id)?.days||[]).filter(v=>dates.includes(v.date)&&Number.isFinite(v.pct_change)).map(v=>Math.abs(v.pct_change))),.001);
        const missingFunds=live?history.boards.reduce((count,b)=>count+b.days.filter(v=>dates.includes(v.date)&&!Number.isFinite(v.main_net_inflow_yi)).length,0):0;
        const missingPct=live?history.boards.reduce((count,b)=>count+b.days.filter(v=>dates.includes(v.date)&&!Number.isFinite(v.pct_change)).length,0):0;
        root.querySelector('.history-note').textContent=live?`${dates[0]||'—'}—${history.as_of||'—'} · 当前Top10回看；历史列为收盘值，当日列随盘中快照更新。${missingPct||missingFunds?`源缺测：${missingPct?'涨跌幅'+missingPct+'格、':''}${missingFunds?'资金'+missingFunds+'格':''}，均显示“—”。`:'缺测显示“—”。'}`:`${dates[0]}—${history.as_of} · 当前Top10名单回看；模拟收盘日值，不随分时回放变化。`;
        root.querySelector('.history-table').innerHTML='<thead><tr><th scope="col">排名 / 板块</th>'+dates.map(date=>`<th scope="col" class="${date===history.as_of?'history-latest':''}"><time datetime="${esc(date)}">${esc(date.slice(5).replace('-','/'))}</time></th>`).join('')+'</tr></thead><tbody>'+ranked.map((s,i)=>{
          const board=history.boards.find(b=>b.id===s.id);
          return `<tr data-history-sector="${s.id}"><th class="board-cell" scope="row"><span class="rank-no">${String(i+1).padStart(2,'0')}</span><span class="history-board-name">${esc(s.name)}</span></th>${dates.map(date=>{const v=board.days.find(v=>v.date===date)||{pct_change:null,main_net_inflow_yi:null};return `<td data-date="${esc(date)}" style="background:color-mix(in srgb,var(${v.pct_change>=0?'--mf-red':'--mf-ink'}) ${Number.isFinite(v.pct_change)?(3+Math.abs(v.pct_change)/maxPct*9).toFixed(1):0}%,transparent)"><span class="history-pct ${v.pct_change>=0?'positive':'negative'}">${num(v.pct_change)}${Number.isFinite(v.pct_change)?'%':''}</span><span class="history-flow ${v.main_net_inflow_yi>=0?'positive':'negative'}">${num(v.main_net_inflow_yi)}</span></td>`;}).join('')}</tr>`;
        }).join('')+(!ranked.length?'<tr><td colspan="6" class="panel-state">概念榜暂未取到，等待数据源恢复后显示当前Top10的5日矩阵。</td></tr>':'')+'</tbody>';
      }
      function render(){
        rankThemes();
        const fundClock=minute===120?'11:30 / 13:00':time(Math.floor(minute));
        root.dataset.fundView=live&&fundReview?'review':'latest';
        root.dataset.fundSourceAsOf=fundSection?.as_of||'';
        root.querySelector('.rank-scope').textContent=live?(flowOnly?'与05同一Top10 / 亿元':'与02同一Top10 / 亿元'):closingReplay?'收盘Top10回看 / 亿元':'当前涨幅Top10 / 亿元';
        root.querySelector('.rank-list-scope').textContent=live?(ranked.length?`${fundReview?'资金回看':'资金截至'} ${fundClock}`:'概念榜暂不可用'):closingReplay?'收盘排名 / 亿元':'当前排名 / 亿元';
        if(live&&flowOnly&&fundSection?.as_of){
          const rankedAt=fundSection.as_of.slice(11,16),cached=!['ok','cached_close'].includes(fundSection.status);
          root.querySelector('.rank-scope').textContent=`${rankedAt}${cached?'榜单缓存':'榜序'} / 亿元`;
          root.querySelector('.rank-list-scope').textContent=`榜序 ${rankedAt} · ${fundReview?'回看':'资金至'} ${fundClock}`;
        }
        if(!live)root.querySelector('.clock').textContent=time(minute);root.querySelector('.scrubber').value=minute;
        root.querySelector('.fund-time').textContent=(live&&fundDay?fundDay.slice(5)+' ':'')+fundClock;
        const pending=live&&fundReview&&liveSnapshot?.sections?.[sectionKey]?.retrieved_at!==fundSection?.retrieved_at;
        root.querySelector('.fund-view-state').textContent=live?(fundReview?pending?' · 回看（新快照已到，返回最新查看）':' · 回看，榜单固定':' · 最新记录'):'';
        root.querySelector('.pct-snapshot-time').textContent=live?`${flowOnly?'资金榜':'涨跌幅'}：${fundSection?.as_of?.replace('T',' ').slice(5,19)||'未提供时间'}快照，不随回看变化`:'';
        const noTrace=live?ranked.filter(s=>!s.values.some(v=>v.kind!=='quote')).map(s=>s.name):[];
        const gaps=live?ranked.filter(s=>fundModel.segments(s.fundPoints).length>1).map(s=>s.name):[];
        root.querySelector('.fund-missing-note').textContent=live?`每个板块一条轨迹；*及空心点为真实报价。${noTrace.length?`仅报价、分钟分时未返回：${noTrace.join('、')}。`:''}${gaps.length?`仍有资金记录缺口：${gaps.join('、')}；缺段留白，自动补取。`:'已取得记录按相邻交易分钟连接。'}`:'';
        const chosen=ranked.find(s=>s.id===selected);
        root.querySelector('.focus-line').innerHTML=chosen?`<span>${esc(chosen.name)}</span><strong class="${fundAt(chosen).main>=0?'positive':'negative'}">${num(fundAt(chosen).main)} 亿</strong><span class="muted">当日累计主力净额</span>`:'<span class="panel-state">概念榜取数暂不可用 · 不显示模拟排名</span>';
        mainChart();metrics();table();historyTable();
      }
      function pause(){playing=false;cancelAnimationFrame(frame);root.querySelector('.play').textContent='播放回放';}
      function step(now){if(!playing)return;if(!lastTick)lastTick=now;elapsed+=now-lastTick;lastTick=now;const limit=live?fundLimit:240,advance=Math.floor(elapsed/(reduce?250:80));if(advance){minute=Math.min(limit,minute+advance);elapsed-=advance*(reduce?250:80);render();}if(minute>=limit){pause();return;}frame=requestAnimationFrame(step);}
      function seek(value){pause();if(live)fundReview=true;minute=Math.max(0,Math.min(live?fundLimit:240,Number(value)));render();}
      root.querySelector('.play').addEventListener('click',()=>{
        if(playing){pause();return;}
        if(live){if(!fundReview||minute>=fundLimit)minute=Math.floor(Math.min(...sectors.flatMap(s=>s.fundPoints.filter(v=>v.rawMinute<=fundLimit).map(v=>v.t))));fundReview=true;}
        else if(minute===240){closingReplay=true;minute=0;}
        playing=true;lastTick=0;elapsed=0;root.querySelector('.play').textContent='暂停';render();frame=requestAnimationFrame(step);
      });
      root.querySelector('.scrubber').addEventListener('input',e=>seek(e.target.value));
      root.querySelector('.end').addEventListener('click',()=>{pause();if(live){fundReview=false;applySnapshot(liveSnapshot);}else{closingReplay=false;minute=240;render();}});
      function pointerMinute(event){const [x]=d.pointer(event,elSvg),start=Number(elSvg.dataset.plotStart),end=Number(elSvg.dataset.plotEnd);return Math.round((x-start)/(end-start)*240);}
      elSvg.addEventListener('pointerdown',event=>{
        if(event.button!==0||root.querySelector('.scrubber').disabled)return;
        const [x,y]=d.pointer(event,elSvg);
        if(x<Number(elSvg.dataset.plotStart)||x>Number(elSvg.dataset.plotEnd)||y<Number(elSvg.dataset.plotTop)||y>Number(elSvg.dataset.plotBottom))return;
        fundDrag=true;elSvg.setPointerCapture(event.pointerId);event.preventDefault();seek(pointerMinute(event));
      });
      elSvg.addEventListener('pointermove',event=>{if(fundDrag)seek(pointerMinute(event));});
      elSvg.addEventListener('pointerup',event=>{if(fundDrag){seek(pointerMinute(event));fundDrag=false;if(elSvg.hasPointerCapture(event.pointerId))elSvg.releasePointerCapture(event.pointerId);}});
      elSvg.addEventListener('pointercancel',()=>{fundDrag=false;});
      root.querySelector('.fund-table tbody').addEventListener('click',e=>{const button=e.target.closest('[data-sector]');if(button){selected=live?button.dataset.sector:Number(button.dataset.sector);render();}});
      document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();});
      function adoptFunds(snapshot){
        fundSection=snapshot.sections?.[sectionKey]||{};
        fundDay=fundSection.as_of?.slice(0,10)||'';
        sectors=(fundSection.data?.items||[]).map(s=>({...s,...styleFor(s.id),fundPoints:fundModel.prepare(s)}));
        root.classList.toggle('funds-missing',!sectors.some(s=>s.fundPoints.length));
        fundLimit=Math.min(240,Math.ceil(fundModel.limit(sectors)));minute=fundLimit;
        root.querySelector('.scrubber').max=240;
        const hasPoints=sectors.some(s=>s.fundPoints.length),hasHistory=sectors.some(s=>new Set(s.fundPoints.map(v=>v.t)).size>1);
        root.querySelector('.scrubber').disabled=!hasPoints;root.querySelector('.play').disabled=!hasHistory;
        const dates=(snapshot.breadth_history?.items||breadth.items||[]).slice(-5).map(v=>v.date);
        history={dates,as_of:dates.at(-1),boards:sectors.map(s=>({id:s.id,name:s.name,days:dates.map(date=>{
          const day=(s.days||[]).find(v=>v.date===date)||{date,pct_change:null,main_net_inflow_yi:null};
          return s.as_of?.startsWith(date)?{date,pct_change:s.pct,main_net_inflow_yi:fundModel.at(s.fundPoints,fundLimit,false).main}:day;
        })}))};
        historyKey='';
      }
      function applySnapshot(snapshot){
        liveSnapshot=snapshot;
        breadth=snapshot.breadth_history||breadth;
        const section=snapshot.sections?.[sectionKey];
        if(fundReview&&section?.as_of&&fundDay&&section.as_of.slice(0,10)!==fundDay){pause();fundReview=false;}
        if(!fundReview||!fundSection)adoptFunds(snapshot);
        if(flowOnly){render();return;}
        if(snapshot.sections?.news?.data){news=snapshot.sections.news.data;renderNews();}
        const observed=snapshot.sections?.indices?.as_of||snapshot.sections?.breadth?.as_of;
        root.querySelector('.market-date').textContent=observed?.slice(0,10)||'等待行情';
        const session=snapshot.market_session;
        const closingView=['closed','preopen','closed_today'].includes(session?.phase);
        const completeClose=closingView&&observed?.startsWith(session.expected_date)&&observed.slice(11,16)>='15:00';
        root.querySelector('.clock').textContent=completeClose?'收盘':observed?.slice(11,16)||'—';
        const current=new Date(snapshot.server_time||Date.now());
        const currentDay=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(current);
        const hm=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hour12:false}).format(current);
        const weekday=new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Shanghai',weekday:'short'}).format(current);
        const trading=!['Sat','Sun'].includes(weekday)&&((hm>='09:30'&&hm<='11:30')||(hm>='13:00'&&hm<='15:00'));
        const recent=observed?.startsWith(currentDay)&&current-new Date(observed)<300000&&snapshot.sections?.indices?.status==='ok';
        root.querySelector('.market-state').textContent=completeClose?`${session.label} · 最近交易日`:session?.phase==='closed'?'休市 · 行情缓存未完整':session?.phase==='lunch'?'午间休市 · 午盘快照':trading?(recent?'盘中行情':'行情延迟 / 缓存'):'最近已获取行情';
        if(session?.expected_date&&observed&&!observed.startsWith(session.expected_date))root.querySelector('.market-state').textContent=`行情缓存 · 应为 ${session.expected_date}`;
        const missing=Object.entries(snapshot.sections||{}).filter(([,v])=>!['ok','cached_close'].includes(v.status)).map(([k])=>({indices:'指数',breadth:'涨跌家数',concepts:'涨幅榜',fund_concepts:'资金榜',communications:'通信专栏',news:'快讯'}[k]||k));
        const cachedClose=Object.values(snapshot.sections||{}).some(v=>v.status==='cached_close');
        root.querySelector('.live-status').textContent=continuous?`本机服务在线 · 每60秒检查${cachedClose?' · 读取最近收盘缓存':''}${snapshot.refreshing?' · 更新中':''}${missing.length?' · '+missing.join('、')+'缓存或缺测':''}`:'静态行情快照 · 持续更新请打开本机实时看板';
        if(!continuous){
          root.querySelector('.market-state').textContent='静态快照 · 不自动刷新';
          root.querySelector('.live-status').textContent=`静态快照：行情截至 ${observed?.replace('T',' ').slice(0,16)||'未提供'}。盘中请点“打开盘中看板”。`;
        }
        breadthChart();render();
      }
      new ResizeObserver(()=>{mainChart();metrics();breadthChart();}).observe(root);
      if(live){
        root.classList.add('live-mode');
        root.classList.toggle('snapshot-mode',!continuous);
        if(!flowOnly){
        root.querySelector('.market-subtitle').textContent='市场宽度 / 通信细分观察 / 概念Top10与资金 / 国内外快讯';
        root.querySelector('.refresh-live').hidden=!continuous;
        root.querySelector('.live-link').hidden=continuous;
        root.querySelector('.news-section .scope-note').textContent='快讯按来源发布时间展示；点击标题查看原文。获取时间与行情时间分别标注。';
        root.querySelector('footer .demo').textContent='公开数据快照 · 各区块按自身数据时间展示，缺测不填模拟值。';
        }
        root.querySelector('.end').textContent='返回最新';
        root.querySelector('.play').setAttribute('aria-label',flowOnly?'播放资金流入榜分时回看':'播放资金分时回看');
        root.querySelectorAll('[aria-label*="模拟"],[aria-label*="示意"]').forEach(el=>el.setAttribute('aria-label',el.getAttribute('aria-label').replace(/模拟|示意/g,'行情')));
        document.addEventListener('industry:data',event=>applySnapshot(event.detail));
        applySnapshot(JSON.parse(page.querySelector('#industry-market-data').textContent));
      }else{breadthChart();render();}
      if(!live&&globalThis.Tweak){const opts={accent:'#a51f34'};const tweak=new Tweak({container:root,onChange:()=>root.style.setProperty('--mf-red',opts.accent)});tweak.addColorPicker(opts,'accent',{label:'版式强调色',reference:'--mf-red'});}
    }
    mountRanking(document.getElementById('market-flow-replay'),'concepts');
    mountRanking(document.querySelector('#market-flow-replay .flow-ranking'),'fund_concepts');
