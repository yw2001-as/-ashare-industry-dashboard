/* 只选择已观测记录；不插值，不把最新快照反填到更早的时刻。 */
(()=>{
  const fields=['main','xl','lg','md','sm'];
  const missing=()=>Object.fromEntries(fields.map(key=>[key,null]));
  function minuteOf(asOf){
    const match=String(asOf||'').match(/T(\d{2}):(\d{2})(?::(\d{2}))?/);
    if(!match)return null;
    const value=Number(match[1])*60+Number(match[2])+Number(match[3]||0)/60;
    if(value<570)return null;
    return value<=690?value-570:value<780?120:value-780+120;
  }
  function prepare(board){
    const day=String(board.as_of||'').slice(0,10);
    let rows=(board.values||[]).filter(row=>Number.isFinite(row.t)&&row.t>=0&&row.t<=240&&Number.isFinite(row.main)&&(!day||!row.as_of||row.as_of.startsWith(day)))
      .map(row=>{const raw=minuteOf(row.as_of);return {...row,t:row.kind==='quote'&&raw!==null?Math.min(240,raw):row.t,kind:row.kind||'series',rawMinute:raw??row.rawMinute};}).sort((a,b)=>a.t-b.t||String(a.as_of||'').localeCompare(String(b.as_of||'')));
    const minutes=rows.filter(row=>row.kind==='series');
    if(minutes.length){
      const covered=new Set(minutes.map(row=>Math.floor(row.t+1e-7)));
      rows=rows.filter(row=>row.kind==='series'||!covered.has(Math.floor(row.t+1e-7)));
    }
    rows.sort((a,b)=>a.t-b.t||String(a.as_of||'').localeCompare(String(b.as_of||'')));
    const rawMinute=minuteOf(board.as_of);
    if(rawMinute!==null&&Number.isFinite(board.latest?.main)&&(!rows.length||board.as_of>rows.at(-1).as_of&&rawMinute>rows.at(-1).t))rows.push({...board.latest,t:Math.min(240,rawMinute),rawMinute,as_of:board.as_of,kind:'quote'});
    return rows;
  }
  function through(points,minute,review=false){
    return points.filter(row=>row.t<=minute&&(row.kind!=='quote'||!review||row.rawMinute<=minute));
  }
  function at(points,minute,review=false){
    const rows=through(points,minute,review);
    return rows.length?rows[rows.length-1]:{...missing(),t:null,as_of:null,kind:'missing'};
  }
  function limit(boards){
    return Math.min(240,Math.max(0,...boards.flatMap(board=>(board.fundPoints||[]).map(row=>row.t))));
  }
  function segments(points){
    const result=[];
    for(const row of points){
      const last=result.at(-1),prev=last?.at(-1);
      // 按交易分钟桶判断相邻，兼容分钟线接带秒的真实报价；缺少整分钟仍断开。
      if(!prev||Math.floor(row.t+1e-7)-Math.floor(prev.t+1e-7)>1)result.push([row]);else last.push(row);
    }
    return result;
  }
  const api={minuteOf,prepare,through,at,limit,segments};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  if(typeof globalThis!=='undefined')globalThis.IndustryFundReplay=api;
})();
