/* 同源数据接入仅用于本机服务；会话内版式源文件不执行联网取数。 */
(()=>{
  const root=document.getElementById('market-flow-replay');
  const button=root.querySelector('.refresh-live');
  const status=root.querySelector('.live-status');
  let timer=null;
  async function poll(){
    clearTimeout(timer);
    let delay=60000;
    try{
      const response=await fetch('/api/snapshot',{cache:'no-store'});
      if(!response.ok)throw new Error('snapshot unavailable');
      const snapshot=await response.json();
      if(snapshot.app!=='industry-review-local-v1')throw new Error('unexpected server');
      document.dispatchEvent(new CustomEvent('industry:data',{detail:snapshot}));
      button.disabled=snapshot.refreshing;
      button.textContent=snapshot.refreshing?'更新中…':'立即更新';
      if(snapshot.refreshing)delay=2000;
    }catch(error){
      status.textContent='本机服务连接中断 · 保留当前画面及原数据时间';
      button.disabled=false;
    }
    timer=setTimeout(poll,delay);
  }
  button.addEventListener('click',async()=>{
    button.disabled=true;button.textContent='更新中…';
    try{await fetch('/api/refresh',{method:'POST'});}finally{await poll();}
  });
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});
  poll();
})();
