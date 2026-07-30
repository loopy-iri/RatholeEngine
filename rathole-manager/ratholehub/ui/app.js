const $=id=>document.getElementById(id);
let TOKEN=localStorage.getItem('rh_token')||'';
let SERVERS=[];
let LANG=localStorage.getItem('rh_lang')||'fa';

function t(k){return (DICT[LANG]&&DICT[LANG][k])||DICT.fa[k]||k;}
function applyStatic(){
 document.documentElement.lang=LANG; document.documentElement.dir=(LANG==='fa'?'rtl':'ltr');
}
function toggleLang(){LANG=(LANG==='fa'?'en':'fa');localStorage.setItem('rh_lang',LANG);applyStatic();shell();}
function confirmT(k,extra){return confirm(t(k)+(extra?(' '+extra):'')+' ?');}

function h(t){return (''+(t==null?'':t)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function toast(t){const e=$('toast');e.textContent=t;e.classList.add('show');clearTimeout(e._t);e._t=setTimeout(()=>e.classList.remove('show'),5000);}
async function api(m,p,b){const o={method:m,headers:{'Content-Type':'application/json'}};
 if(TOKEN)o.headers['Authorization']='Bearer '+TOKEN; if(b)o.body=JSON.stringify(b);
 const r=await fetch(p,o); let j={};try{j=await r.json()}catch(e){}
 if(r.status===401){TOKEN='';localStorage.removeItem('rh_token');shell();} return {status:r.status,j};}
function logout(){TOKEN='';localStorage.removeItem('rh_token');shell();}
function modal(html){let m=$('modal');if(!m){m=document.createElement('div');m.id='modal';m.className='modal';m.onclick=e=>{if(e.target===m)closeModal();};document.body.appendChild(m);}m.innerHTML='<div class="mbox">'+html+'</div>';m.style.display='flex';}
function closeModal(){const m=$('modal');if(m)m.style.display='none';}

// ---------- form modal (jaigozin prompt zanjire-i) ----------
// fields: [{id,label,type,val,ph,opts:[{v,t}],req}]  onOk(values)
function formModal(title,fields,onOk){
 const rows=fields.map(f=>{
  let inp;
  if(f.type==='select'){inp=`<select id="f_${f.id}">`+f.opts.map(o=>`<option value="${h(o.v)}"${o.v==(f.val||'')?' selected':''}>${h(o.t)}</option>`).join('')+`</select>`;}
  else{inp=`<input id="f_${f.id}" type="${f.type||'text'}" value="${h(f.val==null?'':f.val)}" placeholder="${h(f.ph||'')}">`;}
  return `<div class="row"><label>${h(f.label)}</label>${inp}</div>`;
 }).join('');
 modal(`<h3>${h(title)}</h3>${rows}<div class="row" style="margin-top:12px;justify-content:flex-end">
  <button class="gh" onclick="closeModal()">${t('cancel')}</button>
  <button class="g" id="f_ok">${t('save')}</button></div>`);
 setTimeout(()=>{const first=fields[0]&&$('f_'+fields[0].id);if(first)first.focus();},30);
 $('f_ok').onclick=()=>{
  const v={};let ok=true;
  fields.forEach(f=>{v[f.id]=($('f_'+f.id).value||'').trim();if(f.req&&!v[f.id])ok=false;});
  if(!ok){toast(t('fill'));return;}
  onOk(v);
 };
}
const PROF=[{v:'balanced',t:'balanced'},{v:'lossy',t:'lossy'},{v:'aggressive',t:'aggressive'}];

setInterval(()=>{const c=$('clock');if(c)c.textContent=new Date().toLocaleTimeString(LANG==='fa'?'fa-IR':'en-US');},1000);

// ---------- router (hash-based ta posht-e /hub/ ham kar konad) ----------
let OVS={};                                            // cache: name -> akharin overview
let VIEW=localStorage.getItem('rh_view')||'grid';      // chinesh dashboard: grid|list
let ROUTE={page:'dashboard',param:null};
function parseHash(){const hh=location.hash||'#/dashboard';
 let m=hh.match(/^#\/server\/([A-Za-z0-9_-]+)$/); if(m)return{page:'server',param:m[1]};
 m=hh.match(/^#\/(dashboard|routing|audit|settings)$/); return m?{page:m[1],param:null}:{page:'dashboard',param:null};}
function nav(hh){if(location.hash===hh){router();}else{location.hash=hh;}}
window.addEventListener('hashchange',()=>{if(TOKEN)router();});
function markNav(){document.querySelectorAll('.sitem').forEach(e=>{
 e.classList.toggle('active',e.dataset.pg===ROUTE.page);});}
async function router(){
 if(!TOKEN)return; ROUTE=parseHash(); markNav();
 await ensureServers();
 if(ROUTE.page==='server')renderServerPage(ROUTE.param);
 else if(ROUTE.page==='routing')renderRouting();
 else if(ROUTE.page==='audit')renderAuditPage();
 else if(ROUTE.page==='settings')renderSettingsPage();
 else renderDashboard();
}
async function ensureServers(){if(SERVERS.length)return;const {j}=await api('GET','api/servers');SERVERS=j||[];}
// sazegari ba code-haye ghadimi: refresh-e inventory + safhe-ye faal
async function loadAll(){SERVERS=[];await ensureServers();router();}
// vaghti overview miresad, faghat safhe-ye faal ra be-rooz kon
function onOv(n){
 if(ROUTE.page==='dashboard'){updateCard(n);
  // doctor-e iran vaziat-e tunnel-e node-ha ra moshakhas mikonad → kart-e node-ha ham berooz shavand
  if(fnd(n).role==='iran')SERVERS.filter(s=>s.role==='node').forEach(s=>updateCard(s.name));
  updateHubStrip();}
 else if(ROUTE.page==='server'&&ROUTE.param===n)renderServerPage(n);
 else if(ROUTE.page==='server'&&fnd(n).role==='iran'&&fnd(ROUTE.param).role==='node')renderServerPage(ROUTE.param);
 else if(ROUTE.page==='routing')scheduleGraph();
}
async function loadOv(n){const {j}=await api('GET','api/servers/'+n+'/overview');OVS[n]=j||{};onOv(n);}

function shell(){
 applyStatic();
 if(!TOKEN){document.body.classList.add('login');
  $('app').innerHTML=`<main id="page"><div class="card" style="min-width:300px"><div class="cbody"><h3>${t('login_title')}</h3>
   <div class="addbar"><input id="pw" type="password" placeholder="${t('pw_ph')}" style="min-width:220px">
   <button class="g" onclick="doLogin()">${t('login_btn')}</button></div><div id="msg" class="sub"></div></div></div></main>`;
  const p=$('pw'); if(p)p.addEventListener('keydown',e=>{if(e.key==='Enter')doLogin();}); return;}
 document.body.classList.remove('login');
 $('app').innerHTML=`<nav id="sb">
   <div class="logo">rathole<span>hub</span></div>
   <div class="sitem" data-pg="dashboard" onclick="nav('#/dashboard')"><span class="ic">▦</span><span>${t('nav_dash')}</span></div>
   <div class="sitem" data-pg="routing" onclick="nav('#/routing')"><span class="ic">◈</span><span>${t('nav_routing')}</span></div>
   <div class="sitem" data-pg="audit" onclick="nav('#/audit')"><span class="ic">≡</span><span>${t('audit')}</span></div>
   <div class="sitem" data-pg="settings" onclick="nav('#/settings')"><span class="ic">⚙</span><span>${t('settings')}</span></div>
   <div class="sfoot">
    <span class="clock" id="clock"></span>
    <label class="sw"><input type="checkbox" id="auto" checked> <span>${t('auto')}</span></label>
    <div class="btns"><button class="gh" onclick="toggleLang()">${LANG==='fa'?'EN':'فا'}</button>
    <button class="gh" onclick="refreshPage()">${t('refresh')}</button>
    <button class="s" onclick="logout()">${t('logout')}</button></div>
   </div></nav><main id="page"></main>`;
 router();
}
function refreshPage(){SERVERS=[];ensureServers().then(()=>{router();pollByPage();});}
// polling-e hoshmand: faghat overview-haye lazem baraye safhe-ye faal
function pollByPage(){
 if(!TOKEN)return;
 if(ROUTE.page==='server'&&ROUTE.param){loadOv(ROUTE.param);
  // vaziat-e tunnel-e node az doctor-e Iran miayad → overview-e Iran-ha ham lazem ast
  if(fnd(ROUTE.param).role==='node')SERVERS.filter(s=>s.role==='iran').forEach(s=>loadOv(s.name));}
 else if(ROUTE.page==='dashboard'||ROUTE.page==='routing'){SERVERS.forEach(s=>loadOv(s.name));}
 if(ROUTE.page==='dashboard')loadHubStatus();
}
async function doLogin(){const {status,j}=await api('POST','api/login',{password:$('pw').value});
 if(status===200){TOKEN=j.token;localStorage.setItem('rh_token',TOKEN);if(!location.hash)location.hash='#/dashboard';shell();}else{$('msg').textContent=t('pw_wrong');}}
function fnd(n){return SERVERS.find(s=>s.name===n)||{};}
function setDot(n,cls){const d=$('dot_'+n); if(d)d.className='dot '+cls;}

// ---------- vaziat-e vasl boodan-e tunnel-e node (az doctor-e serverhaye Iran) ----------
// doctor rooye Iran har node ra ok/warn mikonad; inja natije baraye yek server-e node
// jam mishavad: 'ok' (hameye service-ha vasl), 'warn' (hadaghal yeki ghat), ya null (namalum).
function nodeTunnelStatus(n){
 const ov=OVS[n]; if(!ov||ov.reachable===false)return null;
 const keys=[n].concat((ov.services||[]).map(x=>x.name));
 (ov.upstreams||[]).forEach(u=>(u.services||[]).forEach(x=>keys.push(x.name)));
 let seen=false,bad=false;
 SERVERS.filter(s=>s.role==='iran').forEach(s=>{
  const hn=(((OVS[s.name]||{}).health)||{}).nodes||{};
  keys.forEach(k=>{if(k in hn){seen=true;if(hn[k]==='warn')bad=true;}});
 });
 return seen?(bad?'warn':'ok'):null;
}
// ---------- badge-haye khoolase (moshtarak beyne kart va safhe-ye server) ----------
function headBadges(n,ov){
 const role=fnd(n).role;
 if(!ov||ov.reachable===false)return `<span class="badge b-bad">${t('no_ssh')}</span>`;
 let hb='';
 if(role==='iran'){const ok=(ov.health||{}).fail===0;
  hb=`<span class="badge ${ok?'b-ok':'b-bad'}">doctor ${(ov.health||{}).ok||0}/${((ov.health||{}).ok||0)+((ov.health||{}).fail||0)}</span>`;
  const k=ov.kcp||{}; hb+=k.enabled?` <span class="badge b-kcp">kcp ${h(k.profile||'')}${k.port?(' :'+h(k.port)):''}${k.stealth?' · QUIC':''}</span>`:' <span class="badge b-ws">ws/443</span>';
  const nz=ov.noise||{}; if(nz.enabled){hb+=` <span class="badge b-noise">noise${nz.port?(' :'+h(nz.port)):''}${nz.count?(' · '+h(nz.count)+' node'):''}</span>`;}
 }else{const m=ov.main_tunnel||(ov.kcp||{}).mode||'ws';
  hb=m==='noise'?`<span class="badge b-noise">tunnel noise</span>`:(m==='kcp'?`<span class="badge b-kcp">tunnel kcp ${h((ov.kcp||{}).profile||'')}</span>`:(m==='plain'?`<span class="badge b-plain">tunnel plain</span>`:'<span class="badge b-ws">tunnel ws/443</span>'));
  if((ov.noise||{}).enabled&&m!=='noise'){hb+=' <span class="badge b-noise">noise</span>';}
  const ts=nodeTunnelStatus(n);
  if(ts)hb+=` <span class="badge ${ts==='ok'?'b-ok':'b-bad'}">${ts==='ok'?t('tun_up'):t('tun_down')}</span>`;
 }
 hb+=verBadge(ov);
 return hb;
}
// badge-e noskhe: sabz=hamsan ba akharin (latest_version-e hub), zard=ghadimi-tar (niaz be apdit).
function latestVer(){return (HUBST&&HUBST.latest_version)||'';}
function verBadge(ov){
 const mv=((ov||{}).version||{}).manager||''; if(!mv)return '';
 const lv=latestVer(); const old=lv&&mv!==lv;
 return ` <span class="badge ${old?'b-bad':'b-ok'}" title="${old?t('ver_old'):t('ver_ok')}">v${h(mv)}${old?' → v'+h(lv):''}</span>`;
}
function ovDotCls(n,ov){
 if(!ov)return 'd-un';
 if(ov.reachable===false)return 'd-bad';
 if(fnd(n).role==='iran')return ((ov.health||{}).fail===0)?'d-ok':'d-bad';
 const ts=nodeTunnelStatus(n);
 return ts==='warn'?'d-bad':'d-ok';
}

// ---------- vaziat-e khod-e server-e hub (strip-e bala-ye dashboard) ----------
let HUBST=null;
function fmtDur(s){if(s==null)return '?';const d=Math.floor(s/86400),hh=Math.floor(s%86400/3600),mm=Math.floor(s%3600/60);
 return (d?d+'d ':'')+(hh?hh+'h ':'')+mm+'m';}
function fmtGB(b){return (b/1073741824).toFixed(1)+'G';}
async function loadHubStatus(){const {j}=await api('GET','api/hubstatus');HUBST=j||null;updateHubStrip();}
function updateHubStrip(){
 const box=$('hubstrip'); if(!box)return;
 const st=HUBST;
 if(!st){box.innerHTML=`<span class="sub">${t('loading')}</span>`;return;}
 let x=`<span class="badge b-role">${t('hub_box')}</span>`;
 const sv=st.services||{};
 Object.keys(sv).forEach(u=>{const ok=sv[u]==='active';
  x+=` <span class="badge ${ok?'b-ok':'b-bad'}">${h(u)} ${ok?'✓':'✗'}</span>`;});
 if(st.uptime!=null)x+=` <span class="sub mono">${t('hs_up')}: ${fmtDur(st.uptime)}</span>`;
 else x+=` <span class="sub mono">${t('hs_up')}(hub): ${fmtDur(st.hub_uptime)}</span>`;
 if(st.load)x+=` <span class="sub mono">${t('hs_load')}: ${st.load.join(' ')}</span>`;
 if(st.mem_total_kb){const used=st.mem_total_kb-(st.mem_avail_kb||0);
  x+=` <span class="sub mono">${t('hs_mem')}: ${(used/1048576).toFixed(1)}/${(st.mem_total_kb/1048576).toFixed(1)}G</span>`;}
 if(st.disk_total)x+=` <span class="sub mono">${t('hs_disk')}: ${fmtGB(st.disk_free)}/${fmtGB(st.disk_total)}</span>`;
 // khoolase-ye inventory: chand server up/down (az overview-haye cache-shode)
 let up=0,down=0,unk=0;
 SERVERS.forEach(s=>{const ov=OVS[s.name];
  if(!ov)unk++;else if(ov.reachable===false)down++;else up++;});
 x+=` <span class="badge ${down?'b-bad':'b-ok'}">${up}/${SERVERS.length} SSH</span>`;
 box.innerHTML=x;
}

// ---------- safhe: dashboard (grid/list kart-haye khoolase) ----------
function renderDashboard(){
 const pg=$('page'); if(!pg)return;
 pg.innerHTML=`<div class="ptitle"><h2>${t('nav_dash')}</h2><span style="flex:1"></span>
   <button class="g" id="updall" onclick="updateAll()">${t('upd_all')}</button>
   <div class="vswitch"><button id="vg" class="${VIEW==='grid'?'on':''}" onclick="setView('grid')">▦ ${t('view_grid')}</button>
   <button id="vl" class="${VIEW==='list'?'on':''}" onclick="setView('list')">☰ ${t('view_list')}</button></div></div>
  <div id="updpanel"></div>
  <div class="card" style="margin-top:0"><div class="cbody" id="hubstrip" style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:10px 16px"></div></div>
  <div class="card"><div class="cbody">
   <div class="addbar"><b>${t('add_server')}:</b>
   <input id="n" placeholder="${t('f_name')}" size="10"><select id="rl"><option value="iran">iran</option><option value="node">node</option></select>
   <input id="hh" placeholder="${t('f_host')}" size="14"><input id="uu" value="root" size="6"><input id="pp" value="22" size="4">
   <input id="sw" type="password" placeholder="${t('prov_pw')}" size="14">
   <select id="isv" title="${t('l_iran_srv')}"><option value="">${t('l_iran_srv')}?</option>${iranSrvOptions()}</select>
   <button class="g" onclick="provSrv()">${t('prov_btn')}</button>
   <button class="gh" onclick="addSrv()">${t('add_btn')}</button></div>
   <div class="sub" style="margin-top:6px">${t('prov_hint')}</div></div></div>
  <div id="servers" class="grid ${VIEW==='list'?'list':''}"></div>`;
 drawCards();
 updateHubStrip(); loadHubStatus();
 SERVERS.forEach(s=>{if(OVS[s.name])updateCard(s.name);loadOv(s.name);});
}
function setView(v){VIEW=v;localStorage.setItem('rh_view',v);
 const c=$('servers');if(c)c.classList.toggle('list',v==='list');
 const vg=$('vg'),vl=$('vl');if(vg)vg.classList.toggle('on',v==='grid');if(vl)vl.classList.toggle('on',v==='list');}
function drawCards(){
 const c=$('servers'); if(!c)return;
 if(!SERVERS.length){c.innerHTML=`<div class="card" style="margin:0"><div class="cbody empty">${t('no_servers')}</div></div>`;return;}
 c.innerHTML=SERVERS.map(s=>`<div class="scard" id="srv_${h(s.name)}" onclick="nav('#/server/${h(s.name)}')">
   <div class="top"><span class="dot d-un" id="dot_${h(s.name)}"></span>
    <span class="name">${h(s.name)}</span><span class="badge b-role">${h(s.role)}</span></div>
   <div class="host mono">${h(s.host)}:${s.ssh_port}</div>
   <div class="bstrip" id="hd_${h(s.name)}"><span class="sub">${t('loading')}</span></div>
   <div class="meta" id="mt_${h(s.name)}"><span class="qr"><button class="gh" onclick="event.stopPropagation();loadOv('${h(s.name)}')">↻</button></span></div>
  </div>`).join('');
}
function updateCard(n){
 const ov=OVS[n]; if(!ov)return;
 setDot(n,ovDotCls(n,ov));
 const hd=$('hd_'+n); if(hd)hd.innerHTML=headBadges(n,ov);
 const mt=$('mt_'+n); if(!mt)return;
 let meta='';
 if(ov.reachable===false){meta=`<span>${h((ov.error||'').split(String.fromCharCode(10))[0].slice(0,60))}</span>`;}
 else if(fnd(n).role==='iran'){meta=`<span>${(ov.nodes||[]).length} ${t('n_nodes')}</span>`;
  if((ov.game||[]).length)meta+=`<span>${ov.game.length} ${t('n_game')}</span>`;}
 else{meta=`<span>${(ov.services||[]).length} ${t('n_svcs')}</span>`;
  if((ov.upstreams||[]).length)meta+=`<span>${ov.upstreams.length} ${t('n_ups')}</span>`;
  if(ov.main_server)meta+=`<span class="mono">→ ${h(ov.main_server)}</span>`;}
 mt.innerHTML=meta+`<span class="qr"><button class="gh" onclick="event.stopPropagation();loadOv('${h(n)}')">↻</button></span>`;
}

// ---------- safhe: server (hameye amaliat-e ghadimi inja) ----------
function renderServerPage(n){
 const pg=$('page'); if(!pg)return; const s=fnd(n);
 if(!s.name){pg.innerHTML=`<div class="ptitle"><button class="back" onclick="nav('#/dashboard')">${LANG==='fa'?'→':'←'} ${t('back')}</button><h2>${t('srv_notfound')}</h2></div>`;return;}
 const ov=OVS[n];
 let head=`<div class="spage-head"><button class="back" onclick="nav('#/dashboard')">${LANG==='fa'?'→':'←'} ${t('back')}</button>
   <span class="dot ${ovDotCls(n,ov)}" id="dot_${h(n)}"></span>
   <span class="name" style="font-size:18px">${h(n)}</span><span class="badge b-role">${h(s.role)}</span>
   <span class="sub mono">${h(s.host)}:${s.ssh_port}</span><span id="hd_${h(n)}">${ov?headBadges(n,ov):''}</span>
   <span style="flex:1"></span>
   <div class="btns">
     <button class="gh" onclick="loadOv('${h(n)}')">↻</button>
     <button class="gh" onclick="showDetails('${h(n)}')">${t('details')}</button>
     ${s.role==='iran'?`<button class="g" onclick="statusModal('${h(n)}')">${t('status_btn')}</button>`:''}
     <button class="s" onclick="doDeploy('${h(n)}')">${t('update')}</button>
     <button class="s" onclick="run('${h(n)}','tune')">tune</button>
     <button class="gh" onclick="editServer('${h(n)}')">${t('edit_server')}</button>
     <button class="r" onclick="delSrvPage('${h(n)}')">${t('del_server')}</button>
   </div></div>`;
 let body;
 if(!ov){body=`<div class="empty">${t('loading')}</div>`;loadOv(n);}
 else if(ov.reachable===false){body=`<div class="sec"><div class="empty">${t('ssh_help')}<br><code>ssh-copy-id -i /root/.ssh/id_ed25519.pub root@${h(s.host)}</code><br><br>${h(ov.error||'')}</div></div>`;}
 else{body=(s.role==='iran'?renderIran(n,ov):renderNode(n,ov));}
 // baraye node: dot-haye vaziat az doctor-e Iran miayand — agar overview-e Iran-i nadarim, biar
 if(s.role==='node')SERVERS.filter(x=>x.role==='iran'&&!OVS[x.name]).forEach(x=>loadOv(x.name));
 pg.innerHTML=`<div class="spage">${head}<div id="body_${h(n)}">${body}</div></div>`;
}
async function delSrvPage(n){if(!confirm(t('cf_delsrv')+' ('+n+')'))return;await api('DELETE','api/servers/'+n);SERVERS=[];delete OVS[n];nav('#/dashboard');}
function tbl(cols){return '<table><tr>'+cols.map(c=>'<th>'+c+'</th>').join('')+'</tr>';}
function esc(s){return h(s);}

function renderIran(n,ov){
 // baraye dokme-ye «afzoodan be node»: overview-e node-haye kharej ra pishaz-dast biar
 // ta list-e maghsad (node/upstream) khali nabashad.
 SERVERS.filter(x=>x.role==='node'&&!OVS[x.name]).forEach(x=>loadOv(x.name));
 let s='<div id="det_'+n+'"></div>';
 s+=`<div class="sec"><h4>${t('domain_tls')} <button class="g" onclick="domainTls('${n}')">${t('manage')}</button></h4>
   <div class="empty">${t('domain_hint')}</div></div>`;
 s+=`<div class="sec"><h4>${t('ports_sec')} <button class="g" onclick="portsModal('${n}')">${t('manage')}</button></h4>
   <div class="empty">${t('ports_hint')}</div></div>`;
 // samt-e IRAN: inja «kodam hamel DAR DASTRAS ast» tanzim mishavad — har hamel yek
 // listener/core-e mostaghel darad، pas inja on/off-e mostaghel DORost ast.
 // entekhab-e in ke har NODE az kodam hamel estefade konad dar safhe-ye node ast (select).
 s+=`<div class="sec"><h4>${t('carriers_avail')}</h4>
   <div class="sub" style="margin-bottom:6px">${h(t('carriers_avail_hint'))}</div>
   <div class="btns"><span class="sub">${t('kcp_backbone')}</span>
   <button class="g" onclick="kcpOnIran('${n}')">${t('kcp_on')}</button>
   <button class="r" onclick="run('${n}','kcp_off')">${t('kcp_off')}</button>
   <button class="gh" onclick="run('${n}','kcp_show')">${t('show_key')}</button></div>
   <div class="btns" style="margin-top:6px"><span class="sub">${t('plain_mode')}</span>
   <button class="g" onclick="plainOnIran('${n}')">${t('plain_on')}</button>
   <button class="r" onclick="run('${n}','plain_off')">${t('plain_off')}</button>
   <button class="gh" onclick="run('${n}','plain_show')">${t('show_key')}</button></div>
   <div class="btns" style="margin-top:6px"><span class="sub">${t('noise_mode')}</span>
   <button class="g" onclick="noiseOnIran('${n}')">${t('noise_on')}</button>
   <button class="r" onclick="run('${n}','noise_off')">${t('noise_off')}</button>
   <button class="gh" onclick="run('${n}','noise_show')">${t('show_key')}</button>
   <button class="s" onclick="noiseNode('${n}','on')">${t('noise_node_on')}</button>
   <button class="s" onclick="noiseNode('${n}','off')">${t('noise_node_off')}</button></div>
   <div class="btns" style="margin-top:6px"><span class="sub">${t('bh_mode')}</span>
   <button class="g" onclick="bhOnIran('${n}')">${t('bh_on')}</button>
   <button class="r" onclick="run('${n}','backhaul_off')">${t('bh_off')}</button>
   <button class="gh" onclick="run('${n}','backhaul_show')">${t('show_key')}</button>
   <button class="gh" onclick="run('${n}','backhaul_status')">${t('status')}</button>
   <button class="gh" onclick="run('${n}','backhaul_logs')">${t('logs')}</button>
   <button class="s" onclick="bhNode('${n}','on')">${t('bh_node_on')}</button>
   <button class="s" onclick="bhNode('${n}','off')">${t('bh_node_off')}</button></div>
   ${bhUsageLine(ov)}
   <div class="btns" style="margin-top:10px">
   <button class="g" onclick="if(confirm(t('cf_reapply')))run('${n}','regen_full')">${t('reapply')}</button>
   <button class="s" onclick="if(confirm(t('cf_restart')))run('${n}','restart')">${t('restart_rathole')}</button></div>
   <div class="sub" style="margin-top:4px">${h(t('reapply_hint'))}</div></div>`;
 // VORODI-ha (ingress): in ha hamel-e tunnel NISTAND — ravesh-e vorood-e karbar hastand.
 s+=`<div class="sec"><h4>${t('ingress_sec')}</h4>
   <div class="sub" style="margin-bottom:6px">${h(t('ingress_hint'))}</div>
   <div class="btns"><span class="sub">${t('direct_mode')}</span>
   <button class="g" onclick="directOnIran('${n}')">${t('direct_on')}</button>
   <button class="r" onclick="run('${n}','direct_off')">${t('direct_off')}</button>
   <button class="gh" onclick="run('${n}','direct_show')">${t('show_key')}</button></div>
   <div class="btns" style="margin-top:6px"><span class="sub">${t('px_sec')}</span>
   <button class="g" onclick="pxAdd('${n}')">${t('px_add')}</button>
   <button class="gh" onclick="run('${n}','proxy_ls')">${t('px_ls')}</button>
   <button class="r" onclick="pxRm('${n}')">${t('px_rm')}</button></div>
   <div class="sub" style="margin-top:4px">${h(t('px_hint'))}</div>
   <div class="btns" style="margin-top:6px"><span class="sub">${t('fakeweb')}</span>

   <button class="g" onclick="fakewebStart('${n}')">${t('fw_start')}</button>
   <button class="s" onclick="run('${n}','fakeweb_stop')">${t('fw_stop')}</button>
   <button class="r" onclick="if(confirm(t('cf_fwrm')))run('${n}','fakeweb_rm')">${t('fw_rm')}</button></div></div>`;
 s+=`<div class="sec"><h4>${t('nodes_svcs')} <button class="g" onclick="addNode('${n}')">${t('add_node')}</button></h4>`;
 const nodes=ov.nodes||[];
 if(!nodes.length)s+=`<div class="empty">${t('no_nodes')}</div>`;
 else{ s+=tbl([t('c_name'),t('c_dport'),t('c_inbound'),t('c_api'),t('c_ops')]);
  const nnodes=(ov.noise||{}).nodes||[]; const hn=(ov.health||{}).nodes||{};
  nodes.forEach(d=>{ const isN=nnodes.indexOf(d.name)>=0;
   const st=hn[d.name]; const hdot=st?`<span class="dot ${st==='ok'?'d-ok':'d-bad'}" title="${st==='ok'?t('nd_up'):t('nd_down')}" style="margin-inline-end:6px"></span>`:'';
   const nbadge=` ${modeBadge(iranNodeMode(ov,d.name))}`;
   const csel=iranNodeCarrierSel(n,ov,d.name);
   s+=`<tr><td>${hdot}${esc(d.name)}${nbadge}</td><td class="mono">${esc(d.port)}</td><td class="mono">${esc(d.inbound)}</td><td class="mono">${esc(d.api)}</td>
   <td class="btns"><button class="gh" onclick="run('${n}','show_node',{name:'${esc(d.name)}'})">${t('show_token')}</button>
   <button class="g" onclick="wireNode('${n}','${esc(d.name)}')">${t('wire_to_node')}</button>
   <button class="gh" onclick="editNode('${n}','${esc(d.name)}')">${t('edit')}</button>
   <button class="gh" onclick="renameNode('${n}','${esc(d.name)}')">${t('rename')}</button>
   <button class="gh" onclick="if(confirmT('cf_rotate','${esc(d.name)}'))run('${n}','rotate_node',{name:'${esc(d.name)}'})">${t('rotate')}</button>
   ${csel}
   <button class="r" onclick="rmNode('${n}','${esc(d.name)}')">${t('remove')}</button></td></tr>`;});
  s+='</table>';}
 s+='</div>';
 s+=`<div class="sec"><h4>${t('game_svcs')} <button class="g" onclick="gameAdd('${n}')">${t('add_game')}</button> <button class="gh" onclick="gameCert('${n}')">${t('get_cert')}</button></h4>`;
 const g=ov.game||[];
 if(!g.length)s+=`<div class="empty">${t('no_game')}</div>`;
 else{ s+=tbl([t('c_name'),'SNI',t('c_data'),t('c_node_inb'),t('c_ops')]);
  g.forEach(d=>{s+=`<tr><td>${esc(d.name)}</td><td>${esc(d.sni)}</td><td>${esc(d.data)}</td><td>${esc(d.inbound)}</td>
   <td class="btns"><button class="r" onclick="run('${n}','game_rm',{name:'${esc(d.name)}'})">${t('remove')}</button></td></tr>`;});
  s+='</table>';}
 s+='</div>';
 return s;
}

// vaziat-e yek service-e node az doctor-e hameye Iran-ha ('ok'/'warn'/null)
function svcStatus(name){
 let st=null;
 SERVERS.filter(s=>s.role==='iran').forEach(s=>{
  const hn=(((OVS[s.name]||{}).health)||{}).nodes||{};
  if(name in hn){if(hn[name]==='warn')st='warn';else if(st===null)st='ok';}
 });
 return st;
}
function svcDot(name){
 const st=svcStatus(name);
 return st?`<span class="dot ${st==='ok'?'d-ok':'d-bad'}" title="${st==='ok'?t('nd_up'):t('nd_down')}" style="margin-inline-end:6px"></span>`:'';
}

// ---------- MODE-e daghigh-e har node az didgah-e Iran (manba-e vahed) ----------
// har node dar har lahze YEK mode darad. tartib-e olaviat: game (sni) > backhaul > noise > ws.
// az .transport-e khod-e node (ratholectl ls) mikhanim va baraye CLI-e ghadimi az
// ov.noise.nodes[] / ov.game[] fallback migirim ta hamishe daghigh bashad.
function iranNodeMode(ov,name){
 ov=ov||{};
 const nd=(ov.nodes||[]).find(x=>x&&x.name===name)||{};
 // olaviat-e GHATIE: game(SNI) > backhaul > noise > ws. game yek switch-e L4 rooye 443 ast
 // ke bar hame ghaleb ast, pas AVAL check mishavad (che az ov.game va che az sni-e khod-e node).
 if((ov.game||[]).some(x=>x&&x.name===name)||nd.sni)return 'game';
 if(nd.transport==='backhaul')return 'backhaul';
 if(nd.transport==='noise'||((ov.noise||{}).nodes||[]).indexOf(name)>=0)return 'noise';
 return 'ws';
}
// ---------- backhaul: 1:1 ast — neshan bede kodam node-ha rooyash hastand ----------
// backhaul YEK server + YEK token-e sarasari + YEK majmoue-ye ports darad. agar DO mashin-e
// kharej ba haman token vasl shavand sar-e channel-e kontrol daava mikonand va HAR DO ghat
// mishavand. neshane-ash inbound-e tekrari beyn-e node-haye backhaul ast.
function bhNodes(ov){
 return (((ov||{}).nodes)||[]).filter(x=>x&&x.transport==='backhaul');
}
function bhDupInbounds(ov){
 const seen={},dup=[];
 bhNodes(ov).forEach(x=>{const k=String(x.inbound||'');if(!k)return;
  if(seen[k]){if(dup.indexOf(k)<0)dup.push(k);}else seen[k]=1;});
 return dup;
}
function bhUsageLine(ov){
 const list=bhNodes(ov); if(!list.length)return '';
 const dup=bhDupInbounds(ov);
 let s=`<div class="sub" style="margin-top:6px">${h(t('bh_users'))}: `
      +list.map(x=>`<span class="badge b-backhaul">${h(x.name)}</span>`).join(' ')+'</div>';
 if(dup.length){
  s+=`<div class="sub" style="margin-top:4px;color:#f87171">⚠ ${h(t('bh_dup_warn').replace('%p',dup.join(', ')))}</div>`;
 }
 return s;
}

// badge-e mode ba class/rang-e hamsan ba baghye-ye UI.
function modeBadge(mode){
 const cls={ws:'b-ws',kcp:'b-kcp',plain:'b-plain',noise:'b-noise',backhaul:'b-backhaul',game:'b-game'}[mode]||'b-ws';
 return `<span class="badge ${cls}">${h(t('mode_'+mode))}</span>`;
}

function renderNode(n,ov){
 let s='<div id="det_'+n+'"></div>';
 // HAMEL-e tunnel: rooye node har panj dastur HAMAN motaghayer-e TUNNEL ra minevisand
 // (ratholenode: env_set TUNNEL kcp|plain|noise|backhaul|ws), pas ENHESARI ast — yek
 // select، na chand dokme-ye mostaghel. dokme-haye ghadimi be karbar tavahom-e tarkib
 // midadand dar hali ke akharin dastur bi-seda barande mishod.
 s+=`<div class="sec"><h4>${t('main_tunnel')} ${esc(ov.main_server||'?')} <button class="g" onclick="setMainSrv('${n}')">${t('set_main')}</button></h4>
   <div class="btns"><span class="sub">${t('carrier')}</span>${carrierSelect(n,ov)}
   <button class="s" onclick="run('${n}','restart')">${t('restart_tunnel')}</button>
   <button class="gh" onclick="run('${n}','logs')">${t('logs')}</button>
   <button class="gh" onclick="run('${n}','backhaul_status')">backhaul ${t('status')}</button>
   <button class="gh" onclick="run('${n}','backhaul_logs')">${t('bh_logs')}</button>
   <button class="gh" onclick="run('${n}','migrate')">${t('migrate')}</button></div>
   <div class="sub" style="margin-top:4px">${h(t('carrier_hint'))}</div>
   <div class="btns" style="margin-top:6px"><span class="sub">${t('watchdog')}</span>
   <button class="g" onclick="wdOn('${n}')">${t('wd_on')}</button>
   <button class="r" onclick="run('${n}','watchdog_off')">${t('wd_off')}</button>
   <button class="gh" onclick="run('${n}','watchdog_status')">${t('wd_status')}</button></div>
   <div class="btns" style="margin-top:6px"><span class="sub">${t('adaptive_mode')}</span>
   <button class="g" onclick="adaptiveOnNode('${n}')">${t('adaptive_on')}</button>
   <button class="r" onclick="run('${n}','adaptive_off')">${t('adaptive_off')}</button>
   <button class="gh" onclick="run('${n}','adaptive_status')">${t('adaptive_status')}</button>
   <button class="gh" onclick="run('${n}','adaptive_test')">${t('adaptive_test')}</button></div></div>`;
 s+=`<div class="sec"><h4>${t('svc_tunnel')} <button class="g" onclick="addSvc('${n}')">${t('add_svc')}</button></h4>`;
 const sv=ov.services||[];
 if(!sv.length)s+=`<div class="empty">${t('no_svc')}</div>`;
 else{s+=tbl([t('c_svc'),t('c_inbound'),t('c_ops')]);
  sv.forEach(d=>{s+=`<tr><td>${svcDot(d.name)}${esc(d.name)}</td><td>${esc(d.inbound)}</td>
   <td class="btns"><button class="r" onclick="rmSvc('${n}','${esc(d.name)}')">${t('remove')}</button></td></tr>`;});
  s+='</table>';}
 s+='</div>';
 s+=`<div class="sec"><h4>${t('upstreams')} <button class="g" onclick="upAdd('${n}')">${t('add_up')}</button></h4>
   <div class="sub" style="margin-bottom:6px">${h(t('upcarrier_hint'))}</div>`;
 const ups=ov.upstreams||[];
 if(!ups.length)s+=`<div class="empty">${t('no_up')}</div>`;
 ups.forEach(u=>{
  // badge az hamon manba-e vahed-e mode (mesl-e tunnel-e asli) — daghigh va hamrang.
  const kb=modeBadge(upCarrier(u));
  s+=`<div class="up"><div class="btns" style="align-items:center">
   <b>${esc(u.id)}</b> ${kb} <span class="sub">→ ${esc(u.server)}</span><span style="flex:1"></span>
   <span class="sub">${t('carrier')}</span>${upCarrierSelect(n,u)}
   <button class="s" onclick="run('${n}','upstream_restart',{id:'${esc(u.id)}'})">restart</button>
   <button class="gh" onclick="run('${n}','upstream_status',{id:'${esc(u.id)}'})">${t('status')}</button>
   <button class="gh" onclick="run('${n}','upstream_logs',{id:'${esc(u.id)}'})">${t('logs')}</button>
   <button class="g" onclick="upAddSvc('${n}','${esc(u.id)}')">${t('add_svc')}</button>
   <button class="r" onclick="upRm('${n}','${esc(u.id)}')">${t('del_up')}</button></div>`;
  if((u.services||[]).length){s+=tbl([t('c_svc'),t('c_inbound'),t('c_ops')]);u.services.forEach(x=>{s+=`<tr><td>${svcDot(x.name)}${esc(x.name)}</td><td>${esc(x.inbound)}</td>
   <td class="btns"><button class="r" onclick="upRmSvc('${n}','${esc(u.id)}','${esc(x.name)}')">${t('remove')}</button></td></tr>`;});s+='</table>';}
  s+='</div>';
 });
 s+='</div>';
 return s;
}

// ---------- safhe: routing (graph-e topology, SVG dasti bedoon lib) ----------
let _gTimer=null,_gDragging=false;
let GVIEW=localStorage.getItem('rh_gview')||'graph';     // namaye routing: graph|table
function scheduleGraph(){clearTimeout(_gTimer);_gTimer=setTimeout(()=>{if(ROUTE.page==='routing'&&!_gDragging){if(GVIEW==='console')drawConsole();else drawGraph();}},150);}
function setGView(v){GVIEW=v;localStorage.setItem('rh_gview',v);renderRouting();}
// tartib-e dasti-e box-ha (drag): dar localStorage mimanad
function gOrder(col){try{return JSON.parse(localStorage.getItem('rh_gorder_'+col)||'[]');}catch(e){return[];}}
function gResetOrder(){localStorage.removeItem('rh_gorder_iran');localStorage.removeItem('rh_gorder_node');drawGraph();toast(t('saved'));}
function gApplyOrder(names,col){ // sort-e stable: avval tartib-e save-shode, baghye ba tartib-e ghabli
 const ord=gOrder(col),idx={};ord.forEach((n,i)=>idx[n]=i);
 return names.map((n,i)=>({n,i})).sort((a,b)=>{
  const ia=(a.n in idx)?idx[a.n]:1e9+a.i, ib=(b.n in idx)?idx[b.n]:1e9+b.i; return ia-ib;
 }).map(x=>x.n);
}
function renderRouting(){
 const pg=$('page'); if(!pg)return;
 const isC=GVIEW==='console';
 pg.innerHTML=`<div class="ptitle"><h2>${t('nav_routing')}</h2><span style="flex:1"></span>
   <div class="vswitch"><button class="${GVIEW==='console'?'on':''}" onclick="setGView('console')">⚡ ${t('view_console')}</button>
   <button class="${GVIEW==='graph'?'on':''}" onclick="setGView('graph')">◈ ${t('view_graph')}</button>
   <button class="${GVIEW==='table'?'on':''}" onclick="setGView('table')">☰ ${t('view_table')}</button></div>
   ${GVIEW==='graph'?`<button class="gh" onclick="gResetOrder()">${t('g_reset')}</button>`:''}
   <button class="gh" onclick="pollByPage()">${t('refresh')}</button></div>
  ${GVIEW==='graph'?`<div class="legend"><b style="color:var(--tx)">${t('g_legend')}:</b>
   <span class="li"><span class="lw lw-ws"></span> ws/443</span>
   <span class="li"><span class="lw lw-kcp"></span> kcp</span>
   <span class="li"><span class="lw lw-noise"></span> noise</span>
   <span class="li"><span class="lw lw-plain"></span> plain</span>
   <span class="li"><span class="lw lw-bad"></span> ${t('e_bad')}</span></div>`:''}
  ${isC?`<div class="rc" id="rcwrap"></div>`:`<div class="gwrap" id="gwrap"></div>
  <div class="sub" style="margin-top:8px">${GVIEW==='graph'?(t('g_hint')+' '+t('g_drag')):t('g_hint')}</div>`}`;
 if(isC)drawConsole(); else drawGraph();
 SERVERS.forEach(s=>{if(!OVS[s.name])loadOv(s.name);});
}
// ---------- namaye console: vorodi (ingress) → router → khorooji (node) ----------
// ravesh-haye vorood-e karbar (ingress) mostaghel az transport-e reverse-tunnel-e node.
function ingressLanes(ov){
 const p=ov.plain||{},d=ov.direct||{},g=(ov.game||[]);
 return [
  {key:'tls',cls:'lane-tls',on:true,edit:null,title:t('ing_tls_t'),patt:t('ing_tls_p'),desc:t('ing_tls_d'),port:'443'},
  {key:'direct',cls:'lane-direct',on:!!d.enabled,editFn:'directOnIran',offAct:'direct_off',
   title:t('ing_direct_t'),patt:t('ing_direct_p'),desc:t('ing_direct_d'),port:d.port,header:d.header||'X-Cdn-Id'},
  {key:'plain',cls:'lane-plain',on:!!p.enabled,editFn:'plainOnIran',offAct:'plain_off',
   title:t('ing_plain_t'),patt:t('ing_plain_p'),desc:t('ing_plain_d'),port:p.port},
  {key:'sni',cls:'lane-sni',on:g.length>0,edit:null,title:t('ing_sni_t'),patt:'',desc:t('ing_sni_d'),count:g.length}
 ];
}
function laneHtml(n,ln){
 const st=ln.on?`<span class="badge b-ok">${t('rc_on')}</span>`:`<span class="badge b-bad">${t('rc_off')}</span>`;
 let act='';
 if(ln.editFn){
  act=`<button class="gh" onclick="${ln.editFn}('${h(n)}')">${ln.on?t('rc_edit'):t('rc_enable')}</button>`;
  if(ln.on&&ln.offAct)act+=`<button class="r" onclick="run('${h(n)}','${ln.offAct}')">${t('rc_disable')}</button>`;
 }
 const meta=(ln.port?` <span class="lp">:${h(ln.port)}</span>`:'')+(ln.header?` <span class="lp">${h(ln.header)}</span>`:'')
   +(ln.count!=null&&ln.key==='sni'?` <span class="lp">${ln.count} SNI</span>`:'');
 return `<div class="lane ${ln.cls} ${ln.on?'on':'off'}">
   <div class="lh"><span class="ldot"></span><span class="lt">${h(ln.title)}</span>${meta}${st}
    <span class="lact">${act}</span></div>
   ${ln.patt?`<div class="lh" style="margin-top:5px"><span class="lp">${h(ln.patt)}</span></div>`:''}
   <div class="ld">${h(ln.desc)}</div></div>`;
}
// recipe-ha: baraye har node, chegoone karbar (Xray/V2Ray) be an vasl mishavad — bar asas-e ingress-e roshan.
function iranDomain(iran,ov){
 const nn=(ov.nodes||[]);
 for(const d of nn){const m=/^https?:\/\/([^\/]+)/.exec(d.path||'');if(m)return m[1].replace(/:\d+$/,'');}
 return (fnd(iran).host)||'<domain>';
}
function nodeRecipes(iran,ov,node){
 const host=(fnd(iran).host)||'<IRAN_IP>',dom=iranDomain(iran,ov);
 const p=ov.plain||{},d=ov.direct||{};
 const out=[];
 out.push({tag:'ws/443',cls:'b-ws',lines:[[t('rc_addr'),dom],[t('rc_port'),'443'],[t('rc_wspath'),'/'+node.name],[t('rc_tls'),t('rc_yes')]]});
 if(d.enabled){out.push({tag:'direct',cls:'b-plain',lines:[[t('rc_addr'),host],[t('rc_port'),d.port||'8081'],
   [t('rc_wshost'),'myket.ir  ('+t('rc_hosthint')+')'],[t('rc_header'),(d.header||'X-Cdn-Id')+': '+node.name],[t('rc_tls'),t('rc_no')]]});}
 if(p.enabled){out.push({tag:'plain',cls:'b-plain',lines:[[t('rc_addr'),host],[t('rc_port'),p.port||'8880'],
   [t('rc_wspath'),'/'+node.name],[t('rc_tls'),t('rc_no')]]});}
 return out;
}
function recipeCopyText(node,r){return node+' · '+r.tag+'\\n'+r.lines.map(l=>l[0]+': '+l[1]).join('\\n');}
function drawConsole(){
 const w=$('rcwrap'); if(!w)return;
 const irans=SERVERS.filter(s=>s.role==='iran');
 if(!irans.length){w.innerHTML=`<div class="rc-empty">${t('rc_pick_iran')}</div>`;return;}
 let x='';
 irans.forEach(s=>{
  const ov=OVS[s.name];
  x+=`<div class="rcard"><div class="rc-head">
    <span class="dot ${ov?ovDotCls(s.name,ov):'d-un'}"></span>
    <span class="nm">${h(s.name)}</span><span class="hst">${h(s.host)}</span>
    <span style="flex:1"></span><span class="sub" style="font-size:11px">${t('rc_legend')}</span>
    <button class="gh" onclick="nav('#/server/${h(s.name)}')">${t('details')}</button></div>`;
  if(!ov){x+=`<div class="rc-empty" style="padding:14px">${t('loading')}</div></div>`;return;}
  if(ov.reachable===false){x+=`<div class="rc-empty" style="padding:14px"><span class="badge b-bad">${t('rc_unreach')}</span></div></div>`;return;}
  const lanes=ingressLanes(ov),nodes=ov.nodes||[];
  x+=`<div class="rc-body">
    <div class="rc-col"><h5>${t('rc_ingress')} <span class="cnt">${lanes.filter(l=>l.on).length}/${lanes.length}</span></h5>
      <p class="rc-sub">${t('rc_ingress_sub')}</p>${lanes.map(l=>laneHtml(s.name,l)).join('')}</div>
    <div class="rc-col"><h5>${t('rc_outputs')} <span class="cnt">${nodes.length}</span></h5>
      <p class="rc-sub">${t('rc_outputs_sub')}</p>`;
  if(!nodes.length)x+=`<div class="rc-empty">${t('rc_no_nodes')}</div>`;
  else{
   const nn=(ov.noise||{}).nodes||[],hn=(ov.health||{}).nodes||{};
   nodes.forEach(d=>{
    const isN=nn.indexOf(d.name)>=0,tr=isN?'noise':((ov.kcp||{}).enabled?'kcp':'ws');
    const trb=tr==='noise'?'b-noise':(tr==='kcp'?'b-kcp':'b-ws');
    const st=hn[d.name],dot=st?`<span class="dot ${st==='ok'?'d-ok':'d-bad'}"></span>`:'<span class="dot d-un"></span>';
    const recs=nodeRecipes(s.name,ov,d);
    x+=`<div class="onode ${st==='warn'?'off':''}"><div class="oh">${dot}<span class="onm">${h(d.name)}</span>
      <span class="sub" style="font-size:11px">${t('rc_transport')}:</span><span class="badge ${trb}">${tr}</span>
      <span class="otr sub" style="font-size:11px">→ :${h(d.port)}</span></div>`;
    recs.forEach((r,i)=>{
     const rid='rec_'+h(s.name)+'_'+h(d.name)+'_'+i;
     x+=`<div class="recipe"><div class="rl"><span class="rtag badge ${r.cls}">${t('rc_via')} ${h(r.tag)}</span>
       <button class="cpy" onclick="copyRecipe('${rid}')">⧉ ${t('rc_copy')}</button></div>
       <div id="${rid}" data-cp="${h(recipeCopyText(d.name,r))}">`;
     r.lines.forEach(l=>{x+=`<div class="rl"><span class="k">${h(l[0])}</span><span class="v">${h(l[1])}</span></div>`;});
     x+=`</div></div>`;
    });
    x+=`</div>`;
   });
  }
  x+=`</div></div></div>`;
 });
 w.innerHTML=x;
}
function copyRecipe(id){const el=$(id);if(!el)return;const txt=(el.getAttribute('data-cp')||'').replace(/\\n/g,'\n');
 navigator.clipboard&&navigator.clipboard.writeText(txt);toast(t('rc_copied'));}

// ---------- namaye jadval: har edge yek radif ----------
function drawRouteTable(){
 const w=$('gwrap'); if(!w)return;
 const M=buildGraphModel();
 if(!M.edges.length){w.innerHTML=`<div class="empty" style="padding:20px">${t('g_empty')}</div>`;return;}
 const rows=M.edges.slice().sort((a,b)=>(a.tgt.name+a.node).localeCompare(b.tgt.name+b.node));
 let x=`<div style="direction:${LANG==='fa'?'rtl':'ltr'};padding:4px 10px">`;
 x+=tbl([t('c_node'),t('c_upstream'),t('c_iran'),t('c_tunnel'),t('n_svcs'),t('c_status')]);
 rows.forEach(e=>{
  const tb=e.tunnel==='kcp'?'b-kcp':(e.tunnel==='noise'?'b-noise':(e.tunnel==='plain'?'b-plain':'b-ws'));
  const st=e.status==='warn'?`<span class="dot d-bad"></span> ${t('tun_down')}`
          :(e.status==='ok'?`<span class="dot d-ok"></span> ${t('tun_up')}`:`<span class="dot d-un"></span>`);
  const tgt=e.tgt.kind==='iran'
    ?`<a style="color:var(--ac);cursor:pointer" onclick="nav('#/server/${h(e.tgt.name)}')">${h(e.tgt.name)}</a>`
    :`${h(e.tgt.name)} <span class="sub">(${t('g_external')})</span>`;
  x+=`<tr><td><a style="color:var(--ac);cursor:pointer" onclick="nav('#/server/${h(e.node)}')">${h(e.node)}</a></td>
   <td class="mono">${h(e.label||'main')}</td><td>${tgt}</td>
   <td><span class="badge ${tb}">${h(e.tunnel)}</span></td>
   <td class="mono">${h(e.svcs.join(', ')||'-')}</td><td>${st}</td></tr>`;});
 x+='</table></div>';
 w.innerHTML=x;
}
// host-e yek "host:port" ra be name-e server-e iran dar inventory map mikonad
function matchIran(hostport,idmap){
 if(!hostport)return null;
 const hst=hostport.replace(/:\d+$/,'').toLowerCase();
 return idmap[hst]||null;
}
function buildGraphModel(){
 const irans=SERVERS.filter(s=>s.role==='iran'), nds=SERVERS.filter(s=>s.role==='node');
 // idmap: host/domain → name-e iran (domain az path-e nodes-e overview darmiayad)
 const idmap={};
 irans.forEach(s=>{idmap[(s.host||'').toLowerCase()]=s.name;
  const ov=OVS[s.name];
  ((ov&&ov.nodes)||[]).forEach(d=>{const m=/^https?:\/\/([^\/]+)/.exec(d.path||'');
   if(m)idmap[m[1].replace(/:\d+$/,'').toLowerCase()]=s.name;});});
 const edges=[],externals={};
 // fallback: agar host match nashod (masalan inventory IP darad vali node ba domain vasl ast),
 // az rooye esm-e service-haye moshtarak irane motenazer ra peyda kon.
 function svcFallback(svcNames){
  const hits=irans.filter(s=>{const ovn=((OVS[s.name]||{}).nodes||[]).map(x=>x.name);
   return svcNames.some(nm=>ovn.indexOf(nm)>=0);});
  return hits.length===1?hits[0].name:null;
 }
 function target(hostport,svcNames){
  const nm=matchIran(hostport,idmap); if(nm)return{kind:'iran',name:nm};
  const fb=svcFallback(svcNames||[]); if(fb)return{kind:'iran',name:fb};
  const hst=(hostport||'?').replace(/:\d+$/,'');
  externals[hst]=externals[hst]||{name:hst}; return{kind:'ext',name:hst};
 }
 nds.forEach(d=>{
  const ov=OVS[d.name]; if(!ov||ov.reachable===false)return;
  if(ov.main_server){edges.push({tgt:target(ov.main_server,(ov.services||[]).map(x=>x.name)),node:d.name,tunnel:ov.main_tunnel||'ws',
   svcs:(ov.services||[]).map(x=>x.name),label:''});}
  (ov.upstreams||[]).forEach(u=>{edges.push({tgt:target(u.server,(u.services||[]).map(x=>x.name)),node:d.name,tunnel:u.tunnel||'ws',
   svcs:(u.services||[]).map(x=>x.name),label:u.id});});
 });
 // vaziat-e har edge az doctor-e iran: agar HAR yeki az service-haye in edge kharab bashad → warn
 edges.forEach(e=>{
  e.svc=e.svcs.length;
  if(e.tgt.kind!=='iran')return;
  const hov=OVS[e.tgt.name]; const hn=((hov||{}).health||{}).nodes||{};
  const keys=e.svcs.concat([e.node]);
  if(keys.some(k=>hn[k]==='warn'))e.status='warn';
  else if(keys.some(k=>hn[k]==='ok'))e.status='ok';
 });
 return {irans,nds,edges,externals:Object.keys(externals)};
}
function drawGraph(){
 const w=$('gwrap'); if(!w)return;
 if(GVIEW==='table'){drawRouteTable();return;}
 const M=buildGraphModel();
 if(!M.irans.length&&!M.nds.length){w.innerHTML=`<div class="empty" style="padding:20px">${t('g_empty')}</div>`;return;}
 const anyOv=SERVERS.some(s=>OVS[s.name]);
 const BW=195,BH=60,GY=26,X=[26,300,606],WID=830;
 // sotoon-e node-ha ra bar asas-e iran-e mabda sort kon ta edge-ha kamtar ghat shavand
 const firstIran={};
 M.edges.forEach(e=>{if(!(e.node in firstIran))firstIran[e.node]=(e.tgt.kind==='iran'?e.tgt.name:'zz_'+e.tgt.name);});
 let nodeNames=M.nds.slice().sort((a,b)=>((firstIran[a.name]||'~')+a.name).localeCompare((firstIran[b.name]||'~')+b.name)).map(s=>s.name);
 nodeNames=gApplyOrder(nodeNames,'node');                      // tartib-e dasti (drag) oloviat darad
 const nodeCol=nodeNames.map(nm=>M.nds.find(s=>s.name===nm)).filter(Boolean);
 const iranNames=gApplyOrder(M.irans.map(s=>s.name),'iran');
 const iranCol=iranNames.map(nm=>{const s=M.irans.find(x=>x.name===nm);return{name:s.name,host:s.host,ext:false};})
   .concat(M.externals.map(hst=>({name:hst,host:'',ext:true})));
 // mokhtasat-e amoodi
 function place(list,x,hh){let y=46;const pos={};list.forEach(it=>{pos[it.name?it.name:it]={x,y,h:hh};y+=hh+GY;});return{pos,bot:y};}
 const pi=place(iranCol,X[1],BH+8), pn=place(nodeCol,X[2],BH);
 const H=Math.max(pi.bot,pn.bot,190)+14;
 // markaz-e amoodi baraye sotoon-e kootah-tar
 function recenter(p,bot){const off=(H-14-bot)/2;if(off>4)Object.values(p).forEach(o=>o.y+=off);}
 recenter(pi.pos,pi.bot);recenter(pn.pos,pn.bot);
 const uy=H/2-35;
 let sv=`<svg viewBox="0 0 ${WID} ${H}" xmlns="http://www.w3.org/2000/svg">`;
 sv+=`<text x="${X[0]+60}" y="24" text-anchor="middle" class="gcolhead">${t('g_users')}</text>`;
 sv+=`<text x="${X[1]+BW/2}" y="24" text-anchor="middle" class="gcolhead">${t('g_iran_col')}</text>`;
 sv+=`<text x="${X[2]+BW/2}" y="24" text-anchor="middle" class="gcolhead">${t('g_node_col')}</text>`;
 // --- edges: user → iran (dade-ye vorodi) ---
 const ucx=X[0]+120;
 iranCol.forEach(it=>{if(it.ext)return;const p=pi.pos[it.name];const y2=p.y+ (BH+8)/2;
  sv+=`<path class="edge e-user" d="M ${ucx} ${uy+35} C ${(ucx+X[1])/2} ${uy+35} ${(ucx+X[1])/2} ${y2} ${X[1]} ${y2}" marker-end="url(#arr)"/>`;});
 // --- edges: iran ← node (tunnel-haye barghashti) ---
 // taghsim-e noghat-e etesal rooye labe-ye har box baraye jelogiri az ham-poshani
 const outCnt={},inCnt={};
 M.edges.forEach(e=>{const k=e.tgt.name;outCnt[k]=(outCnt[k]||0)+1;inCnt[e.node]=(inCnt[e.node]||0)+1;});
 const outIdx={},inIdx={};
 let edgeSvg='',labSvg='';
 M.edges.forEach(e=>{
  const P1=pi.pos[e.tgt.name],P2=pn.pos[e.node]; if(!P1||!P2)return;
  outIdx[e.tgt.name]=(outIdx[e.tgt.name]||0)+1; inIdx[e.node]=(inIdx[e.node]||0)+1;
  const y1=P1.y+P1.h*outIdx[e.tgt.name]/(outCnt[e.tgt.name]+1);
  const y2=P2.y+P2.h*inIdx[e.node]/(inCnt[e.node]+1);
  const x1=X[1]+BW,x2=X[2],mx=(x1+x2)/2;
  const cls=e.status==='warn'?'e-bad':('e-'+(['ws','kcp','noise','plain'].indexOf(e.tunnel)>=0?e.tunnel:'ws'));
  const anim=(e.tunnel!=='ws'||e.status==='warn')?' flow':'';
  const dim=e.status==='warn'?'':''; // edge-e kharab ghermez mishavad, dim nemikonim
  edgeSvg+=`<path class="edge ${cls}${anim}${dim}" d="M ${x1} ${y1} C ${mx} ${y1} ${mx} ${y2} ${x2} ${y2}"/>`;
  // label-e vasat-e edge: [upstream-id ·] tunnel · svc
  const txt=(e.label?e.label+' · ':'')+e.tunnel+(e.svc?(' · '+e.svc):'');
  const tw=txt.length*6.6+14, lx=mx-tw/2, ly=(y1+y2)/2-9;
  labSvg+=`<g class="elab" onclick="nav('#/server/${h(e.node)}')"><rect x="${lx}" y="${ly}" width="${tw}" height="18" rx="9"/>`+
   `<text x="${mx}" y="${ly+13}" text-anchor="middle">${h(txt)}</text></g>`;
 });
 sv+=edgeSvg;
 // --- box: users ---
 sv+=`<g><rect class="gbox gbox-ext" x="${X[0]}" y="${uy}" width="120" height="70" rx="12"/>`;
 [[36,uy+26],[60,uy+20],[84,uy+26]].forEach(c=>{sv+=`<circle cx="${c[0]}" cy="${c[1]}" r="6" fill="#3b4c61"/><path d="M ${c[0]-9} ${c[1]+18} a 9 9 0 0 1 18 0" fill="#3b4c61"/>`;});
 sv+=`<text x="${X[0]+60}" y="${uy+60}" text-anchor="middle" class="gsub">${t('g_users')}</text></g>`;
 // --- box-haye iran ---
 iranCol.forEach(it=>{
  const p=pi.pos[it.name],hh=P=>p.y+P;
  const ov=OVS[it.name],off=!it.ext&&ov&&ov.reachable===false;
  const click=it.ext?'':` onclick="nav('#/server/${h(it.name)}')"`;
  const drag=it.ext?'':` data-gcol="iran" data-gname="${h(it.name)}"`;
  sv+=`<g${click}${drag}><rect class="gbox gbox-iran${it.ext?' gbox-ext':''}${off?' gbox-off':''}" x="${p.x}" y="${p.y}" width="${BW}" height="${p.h}" rx="10"><title>${h(it.ext?t('g_external'):it.name)}</title></rect>`;
  const dcls=it.ext?'#8ba0b6':(off?'var(--rd)':(ov?(((ov.health||{}).fail===0)?'var(--gr)':'var(--rd)'):'var(--yl)'));
  sv+=`<circle cx="${p.x+16}" cy="${hh(20)}" r="4.5" fill="${dcls}"/>`;
  sv+=`<text x="${p.x+28}" y="${hh(24)}" class="gtxt">${h(it.name.length>20?it.name.slice(0,19)+'…':it.name)}</text>`;
  if(it.ext){sv+=`<text x="${p.x+14}" y="${hh(44)}" class="gsub">${t('g_external')}</text>`;}
  else{sv+=`<text x="${p.x+14}" y="${hh(42)}" class="gsub">${h((it.host||'').slice(0,26))}</text>`;
   let inf=':443';
   if(ov){const k=ov.kcp||{},nz=ov.noise||{};inf=':443'+(k.enabled?(' · kcp'+(k.port?(' udp:'+k.port):'')):'')+(nz.enabled?(' · noise:'+(nz.port||'')):'');
    inf+=' · '+((ov.nodes||[]).length)+' '+t('n_nodes');}
   sv+=`<text x="${p.x+14}" y="${hh(58)}" class="gsub">${h(inf.slice(0,30))}</text>`;}
  sv+='</g>';});
 // --- box-haye node ---
 nodeCol.forEach(d=>{
  const p=pn.pos[d.name];const ov=OVS[d.name];const off=ov&&ov.reachable===false;
  const bad=M.edges.some(e=>e.node===d.name&&e.status==='warn');
  const dcls=off||bad?'var(--rd)':(ov?'var(--gr)':'var(--yl)');
  sv+=`<g onclick="nav('#/server/${h(d.name)}')" data-gcol="node" data-gname="${h(d.name)}"><rect class="gbox${off?' gbox-off':''}" x="${p.x}" y="${p.y}" width="${BW}" height="${p.h}" rx="10"><title>${h(d.name)}</title></rect>`;
  sv+=`<circle cx="${p.x+16}" cy="${p.y+20}" r="4.5" fill="${dcls}"/>`;
  sv+=`<text x="${p.x+28}" y="${p.y+24}" class="gtxt">${h(d.name.length>20?d.name.slice(0,19)+'…':d.name)}</text>`;
  const sub=(d.host||'')+(ov&&ov.services?(' · '+ov.services.length+' '+t('n_svcs')):'');
  sv+=`<text x="${p.x+14}" y="${p.y+44}" class="gsub">${h(sub.slice(0,30))}</text></g>`;});
 sv+=labSvg;
 sv+=`<defs><marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#3b4c61"/></marker></defs>`;
 sv+='</svg>';
 if(!anyOv)sv=`<div class="empty" style="padding:12px 16px 0">${t('g_loading')}</div>`+sv;
 w.innerHTML=sv;
 bindGraphDrag(w);
}
// ---------- drag-e amoodi-e box-ha (tartib dar localStorage) ----------
function bindGraphDrag(w){
 const svg=w.querySelector('svg'); if(!svg)return;
 svg.querySelectorAll('g[data-gname]').forEach(g=>{
  g.style.cursor='grab';
  g.addEventListener('pointerdown',ev=>{
   const col=g.dataset.gcol,name=g.dataset.gname;
   const vb=svg.viewBox.baseVal,scale=vb.height/svg.getBoundingClientRect().height;
   let moved=false;const y0=ev.clientY;
   const mv=e=>{const dy=(e.clientY-y0)*scale;
    if(!moved&&Math.abs(dy)>6){moved=true;_gDragging=true;g.style.cursor='grabbing';svg.style.userSelect='none';}
    if(moved)g.setAttribute('transform','translate(0,'+dy+')');};
   const up=e=>{
    document.removeEventListener('pointermove',mv);document.removeEventListener('pointerup',up);
    svg.style.userSelect='';_gDragging=false;
    if(!moved)return;                      // click-e sade → navigation-e aadi
    // click-e badi (ke browser bad az pointerup mifrestad) navigation nakonad
    g.addEventListener('click',ce=>{ce.stopPropagation();ce.preventDefault();},{capture:true,once:true});
    // tartib-e jadid: markaz-e box-e keshide-shode ra beyn-e baghye peyda kon
    const others=[...svg.querySelectorAll('g[data-gcol="'+col+'"]')].filter(x=>x!==g);
    const cy=el=>{const r=el.querySelector('rect');return parseFloat(r.getAttribute('y'))+parseFloat(r.getAttribute('height'))/2;};
    const myY=cy(g)+(e.clientY-y0)*scale;
    const order=others.map(x=>({n:x.dataset.gname,y:cy(x)}));
    order.push({n:name,y:myY});
    order.sort((a,b)=>a.y-b.y);
    localStorage.setItem('rh_gorder_'+col,JSON.stringify(order.map(x=>x.n)));
    drawGraph();
   };
   document.addEventListener('pointermove',mv);document.addEventListener('pointerup',up);
  });
 });
}

// ---------- safhe: audit / settings (ghablan modal boodand) ----------
async function renderAuditPage(){
 const pg=$('page'); if(!pg)return;
 pg.innerHTML=`<div class="ptitle"><h2>${t('audit')}</h2></div><div class="card" style="margin-top:0"><div class="cbody" id="auditbody"><div class="empty">${t('loading')}</div></div></div>`;
 const {j}=await api('GET','api/audit?limit=100');
 const box=$('auditbody'); if(!box)return;
 const rows=(j||[]);
 if(!rows.length){box.innerHTML=`<div class="empty">${t('no_audit')}</div>`;return;}
 let x=`<table><tr><th>${t('c_time')}</th><th>${t('c_user')}</th><th>server</th><th>${t('c_action')}</th><th>rc</th></tr>`;
 rows.forEach(e=>{const d=new Date((e.ts||0)*1000).toLocaleString(LANG==='fa'?'fa-IR':'en-US');
  x+=`<tr><td>${h(d)}</td><td class="mono">${h(e.user)}</td><td>${h(e.server)}</td><td class="mono">${h(e.action)}</td><td>${h(e.rc)}</td></tr>`;});
 box.innerHTML=x+'</table>';
}
async function renderSettingsPage(){
 const pg=$('page'); if(!pg)return;
 pg.innerHTML=`<div class="ptitle"><h2>${t('settings')}</h2></div><div class="card" style="margin-top:0"><div class="cbody" id="setbody"><div class="empty">${t('loading')}</div></div></div>`;
 const {j}=await api('GET','api/config');const c=j||{};
 const warn=c.insecure?`<div class="badge b-bad" style="margin-bottom:10px">${t('insecure')}</div>`:'';
 const box=$('setbody'); if(!box)return;
 box.innerHTML=`${warn}
  <div class="mbox" style="background:transparent;border:0;padding:0;min-width:0">
  <div class="row"><label>${t('l_apitoken')}</label><span class="sub mono">${h(c.api_token_hint||'')}</span></div>
  <div class="row"><label>${t('l_listen')}</label><span class="sub mono">${h(c.listen_host||'')}:${h(c.listen_port||'')}</span></div>
  <h3 style="margin-top:14px">${t('chpw')}</h3>
  <div class="row"><label>${t('l_curpw')}</label><input id="cpw" type="password"></div>
  <div class="row"><label>${t('l_newpw')}</label><input id="npw" type="password" placeholder="${t('pw_hint')}"></div>
  <div class="row"><button class="g" onclick="savePw()">${t('save_pw')}</button></div>
  <h3 style="margin-top:14px">${t('l_apitoken')}</h3>
  <div class="row"><button class="s" onclick="rotTok()">${t('rot_tok')}</button></div></div>`;
}

function outModal(title,text){var id='om_'+Math.random().toString(36).slice(2);modal('<h3>'+h(title)+'</h3><pre id="'+id+'" style="max-height:52vh;overflow:auto;white-space:pre-wrap;user-select:text;-webkit-user-select:text">'+h(text)+'</pre><div class="row" style="margin-top:10px"><button class="g" onclick="copyText(\''+id+'\')">'+t('copy_out')+'</button> <button class="gh" onclick="closeModal()">'+t('close')+'</button></div>');}
async function run(n,a,args){toast(t('running')+' '+a+' '+t('on')+' '+n+' …');
 const {j}=await api('POST','api/servers/'+n+'/action',{action:a,args:args||{}});
 const rc=(j&&typeof j.rc==='number')?j.rc:null;
 const ok=(rc===0), bad=(rc!==null&&rc!==0);
 const verdict=ok?('✓ '+t('ok_rc')):(bad?('✗ '+t('fail_rc')+' (rc='+rc+')'):'');
 const body=((j.cmd?('$ '+j.cmd+'\n'):'')+((j.out||'')+(j.err?('\n'+j.err):''))).trim();
 const full=((verdict?verdict+(body?'\n\n':''):'')+body)||JSON.stringify(j);
 if(bad){outModal(a+' ✗',full);}                                    // shekast: hamishe modal, ta gom nashavad
 else if(body&&(body.length>140||body.indexOf(String.fromCharCode(10))>=0)){outModal(a+' ✓',full);}
 else{toast(verdict+(body?(' — '+body):''));}
 loadOv(n);}
async function doDeploy(n){if(!confirm(t('cf_deploy')+' '+n+' ?'))return; run(n,'deploy');}
// apdit-e hamegani: hameye serverha ra YEKI-YEKI (tartibi) apdit mikonad va progress bar +
// vaziat-e har server ra live neshan midahad. deploy = install.sh --update (snapshot+rollback-e khodkar).
let UPD_BUSY=false;
async function updateAll(){
 if(UPD_BUSY)return;
 const list=SERVERS.slice();
 if(!list.length){toast(t('no_servers'));return;}
 if(!confirm(t('cf_upd_all')+' ('+list.length+')'))return;
 UPD_BUSY=true; const btn=$('updall'); if(btn){btn.disabled=true;}
 const panel=$('updpanel'); const total=list.length; let done=0, okc=0, failc=0;
 const rows=list.map(s=>`<div class="updrow" id="ur_${h(s.name)}"><span class="dot d-un"></span><b>${h(s.name)}</b> <span class="badge b-role">${h(s.role)}</span><span class="us" id="us_${h(s.name)}">${t('upd_wait')}</span></div>`).join('');
 if(panel)panel.innerHTML=`<div class="card"><div class="cbody">
   <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px"><b>${t('upd_all')}</b>
     <div class="pbar"><div class="pfill" id="pfill" style="width:0%"></div></div>
     <span id="pcnt" class="mono">0/${total}</span>
     <button class="gh" onclick="closeUpdPanel()" id="updclose" disabled>${t('close')}</button></div>
   ${rows}</div></div>`;
 for(const s of list){
  const us=$('us_'+s.name), dot=document.querySelector('#ur_'+CSS.escape(s.name)+' .dot');
  if(us)us.textContent=' — '+t('upd_running'); if(dot)dot.className='dot d-un';
  try{
   const {j}=await api('POST','api/servers/'+s.name+'/action',{action:'deploy',args:{}});
   const rc=(j&&typeof j.rc==='number')?j.rc:1;
   if(rc===0){okc++; if(dot)dot.className='dot d-ok';
     // baad az apdit noskhe-ye jadid ra bekhan
     await loadOv(s.name); const nv=((OVS[s.name]||{}).version||{}).manager||'?';
     if(us)us.textContent=' — ✓ '+t('upd_ok')+' (v'+nv+')';
   }else{failc++; if(dot)dot.className='dot d-bad';
     if(us)us.textContent=' — ✗ '+t('upd_fail')+' (rc='+rc+')';}
  }catch(e){failc++; if(dot)dot.className='dot d-bad'; if(us)us.textContent=' — ✗ '+t('upd_fail');}
  done++; const pct=Math.round(done*100/total);
  const pf=$('pfill'); if(pf)pf.style.width=pct+'%'; const pc=$('pcnt'); if(pc)pc.textContent=done+'/'+total;
 }
 UPD_BUSY=false; if(btn)btn.disabled=false;
 const cb=$('updclose'); if(cb)cb.disabled=false;
 toast(t('upd_done')+': ✓'+okc+' ✗'+failc);
 loadHubStatus();
}
function closeUpdPanel(){const p=$('updpanel'); if(p&&!UPD_BUSY)p.innerHTML='';}
async function showDetails(n){toast(t('loading_det'));
 const {j}=await api('GET','api/servers/'+n+'/details');
 outModal('details · '+n, j.text||JSON.stringify(j));}
// ---------- dashboard-e vaziat (mesl-e panel-e VPN): status --json ra ziba render mikonad ----------
function stDot(v){return '<span class="dot '+(v==='yes'?'d-ok':'d-bad')+'"></span>';}
async function statusModal(n){toast(t('loading'));
 const {j}=await api('POST','api/servers/'+n+'/action',{action:'status',args:{}});
 let d=null; try{d=JSON.parse(j&&j.out||'');}catch(e){}
 if(!d){outModal('status · '+n,((j&&j.cmd?'$ '+j.cmd+'\\n':'')+((j&&j.out)||'')+((j&&j.err)?'\\n'+j.err:'')).trim()||t('status_err'));return;}
 const P=d.ports||{}, C=d.cert||{}, S=d.services||{};
 const portRow=(port,lbl)=>port?`<tr><td class="mono">${h(String(port))}</td><td>${h(lbl)}</td></tr>`:'';
 const certLine=C.exists==='yes'
   ?`${stDot('yes')} ${t('st_cert_ok')} — ${h(C.expiry||'?')}`+(C.self_signed==='yes'?` <span class="badge" style="background:#7f1d1d">${t('st_selfsigned')}</span>`:'')
   :`${stDot('no')} <span style="color:#f87171">${t('st_cert_missing')}: ${h(C.fullchain||'')}</span>`;
 let nodes='';
 (d.nodes||[]).forEach(x=>{const sni=(x.sni&&x.sni!=='-');
   const url=sni?('SNI: '+h(x.sni)):('https://'+h(d.domain||'')+'/'+h(x.name));
   nodes+=`<tr><td class="mono">${h(x.name)}</td><td class="mono">${h(String(x.port))}</td><td class="mono">${h(String(x.inbound_port))}</td><td class="mono" style="font-size:12px">${url}</td></tr>`;});
 if(!nodes)nodes=`<tr><td colspan="4" class="sub">${t('st_no_nodes')}</td></tr>`;
 modal(`<h3>${t('status_btn')} · ${h(n)}</h3>
  <div class="row"><label>${t('st_domain')}</label><span class="mono">${h(d.domain||'—')}</span></div>
  <div class="row"><label>${t('st_ip')}</label><span class="mono">${h(d.public_ip||'?')}</span></div>
  <div class="row"><label>${t('st_transport')}</label><span class="mono">${h(d.transport||'')}</span></div>
  <h4 style="margin:12px 0 4px">${t('st_services')}</h4>
  <div class="mono">${stDot(S.rathole_server)} rathole-server &nbsp; ${stDot(S.nginx)} nginx (${S.nginx_config_ok==='yes'?t('st_ok'):'<span style=color:#f87171>'+t('st_bad')+'</span>'})${S.noise&&S.noise!=='off'?' &nbsp; '+stDot(S.noise)+' noise':''}</div>
  <h4 style="margin:12px 0 4px">${t('st_ports')}</h4>
  <table><tr><th>PORT</th><th></th></tr>
   ${portRow(443,'443 — '+t('st_p_443'))}
   ${portRow(P.control,t('st_p_control'))}
   ${portRow(P.fake,t('st_p_fake'))}
   ${portRow(P.sub,t('st_p_sub'))}
   ${d.sni_count>0?portRow(P.internal,t('st_p_internal')):''}
   ${portRow(P.plain,t('st_p_plain'))}
   ${portRow(P.direct,t('st_p_direct')+' ('+h(d.direct_header||'')+')')}
   ${portRow(P.hub,t('st_p_hub'))}
   ${portRow(P.noise,t('st_p_noise'))}
  </table>
  <h4 style="margin:12px 0 4px">${t('st_cert')}</h4>
  <div class="mono" style="font-size:13px">${certLine}</div>
  <h4 style="margin:12px 0 4px">${t('st_nodes')} (${(d.nodes||[]).length})</h4>
  <table><tr><th>NAME</th><th>PORT</th><th>INBOUND</th><th>USER URL</th></tr>${nodes}</table>
  <div class="row" style="margin-top:12px"><button class="gh" onclick="closeModal()">${t('close')}</button></div>`);}
function copyText(id){const el=$(id);if(!el)return;const x=el.textContent;
 if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(x).then(()=>toast(t('copied')),()=>toast('copy?'));}
 else{const r=document.createRange();r.selectNode(el);getSelection().removeAllRanges();getSelection().addRange(r);try{document.execCommand('copy');toast(t('copied'));}catch(e){toast('copy?');}}}
async function addSrv(){const b={name:$('n').value,role:$('rl').value,host:$('hh').value,ssh_user:$('uu').value,ssh_port:$('pp').value};
 const {status,j}=await api('POST','api/servers',b); if(status!==200){toast('error: '+(j.error||status));return;} $('n').value='';$('hh').value=''; loadAll();}
async function provSrv(){const b={name:$('n').value,role:$('rl').value,host:$('hh').value,ssh_user:$('uu').value,ssh_port:$('pp').value,ssh_password:$('sw').value,iran_server:($('isv')?$('isv').value:'')};
 if(!b.name||!b.host||!b.ssh_password){toast(t('fill'));return;}
 toast(t('provisioning'));
 const {status,j}=await api('POST','api/provision',b);
 const out=((j&&j.out)||'')+((j&&j.err)?('\n'+j.err):'');
 outModal(t('prov_btn')+' · '+b.name, out.trim()||JSON.stringify(j));
 if(status===200){$('n').value='';$('hh').value='';$('sw').value='';loadAll();}}

// ---------- form-based actions (bedoon prompt zanjire-i) ----------
// afzoodan-e node-e game (SNI): agar in AVALIN node-e SNI bashad، port 443 az L7 be
// nginx stream/L4 (ssl_preread) switch mishavad va vhost-e L7 (sait-e fik + control-e
// rathole + backhaul) be port-e dakheli montaghel mishavad. yani hameye node-haye aadi
// az masir-e jadid obor mikonand — SNI-e eshtebah = ghat-e hame. pas ghabl az an bepors.
function gameAdd(n){
 const ov=OVS[n]||{};
 const first=!((ov.game||[]).length);
 const normal=((ov.nodes||[]).length)||0;
 if(first && !confirm(t('cf_game_l4').replace('%n',String(normal)))) return;
 formModal(t('t_game_add'),[
  {id:'name',label:t('f_name'),ph:'gmtrk',req:1},
  {id:'inbound',label:t('l_inb_tls'),val:'8444',req:1},
  {id:'sni',label:t('l_sni'),ph:'gmtrk.l1t.ir',req:1}],
  v=>{closeModal();run(n,'game_add',v);});}
function gameCert(n){formModal(t('t_game_cert'),[
  {id:'sni',label:t('l_sni_cert'),req:1}],
  v=>{closeModal();run(n,'game_cert',v);});}

function domainTls(n){
 modal(`<h3>${t('domain_tls')} (${n})</h3>
 <div id="dt_list"><div class="empty">${t('loading')}</div></div>
 <div id="dt_domains"></div>
 <div class="row"><label>${t('dt_add')}</label><input id="dt_nd" placeholder="dom2.example.ir" style="min-width:140px"><input id="dt_nfc" placeholder="fullchain (optional)"><input id="dt_nkey" placeholder="privkey (optional)"><button class="g" onclick="dtAddDomain('${n}')">${t('dt_add_btn')}</button></div>
 <div class="row"><button class="s" onclick="run('${n}','tls_info');closeModal();">${t('dt_show')}</button>
   <span class="sub">${t('dt_hint')}</span></div>
 <div class="row"><label>${t('dt_domain')}</label><input id="dt_dom" placeholder="btli.ir">
   <button class="g" onclick="dtSet('${n}','domain','dt_dom')">${t('save')}</button></div>
 <div class="row"><label>${t('dt_fc')}</label><input id="dt_fc" placeholder="/root/cert/x/fullchain.pem">
   <button class="g" onclick="dtSet('${n}','fullchain','dt_fc')">${t('save')}</button></div>
 <div class="row"><label>${t('dt_key')}</label><input id="dt_key" placeholder="/root/cert/x/privkey.pem">
   <button class="g" onclick="dtSet('${n}','key','dt_key')">${t('save')}</button></div>
 <div class="row"><label>${t('dt_le')}</label><input id="dt_ledom" placeholder="dom.example.ir">
   <input id="dt_leem" placeholder="email (optional)">
   <button class="g" onclick="dtCert('${n}')">${t('dt_get')}</button></div>
 <h3 style="margin-top:14px">${t('ports_sec')}</h3>
 <div class="sub" style="margin-bottom:6px">${h(t('ports_hint'))}</div>
 <div id="dt_ports"><div class="empty">${t('loading')}</div></div>
 <div class="row" style="justify-content:flex-end;margin-top:10px">
   <button class="s" onclick="run('${n}','regen_full');closeModal();">${t('dt_apply')}</button>
   <button class="gh" onclick="closeModal()">${t('close')}</button></div>`);dtRefresh(n);}

async function dtLoadList(n){
 const {j}=await api('POST','api/servers/'+n+'/action',{action:'tls_certs',args:{}});
 const box=$('dt_list'); if(!box)return;
 const txt=(j&&j.out)||''; const rows=parseTable(txt,'DOMAIN|EXPIRY|ACTIVE|SNI');
 if(!rows.length){box.innerHTML=`<div class="empty">${t('dt_none')}</div>`;return;}
 let h2=`<div class="sub" style="margin:4px 0">${t('dt_list')}</div>`;
 h2+=`<table><tr><th>${t('dt_domain')}</th><th>${t('dt_expiry')}</th><th>${t('dt_active')}</th><th>SNI</th></tr>`;
 rows.forEach(p=>{const dom=h(p[0]||''),exp=h(p[1]||''),act=(p[2]||'')==='yes',sni=(p[3]||'')==='yes';
  h2+=`<tr><td>${dom}</td><td>${exp}</td><td>${act?('<span class="badge b-ok">'+t('dt_active')+'</span>'):''}</td><td>${sni?'SNI':''}</td></tr>`;});
 h2+='</table>';
 box.innerHTML=h2;
}
function parseTable(txt,header){const cols=header.split('|').length;const lines=(txt||'').split('\n').map(x=>x.trim());let hi=-1;for(let i=0;i<lines.length;i++){if(lines[i].toUpperCase().indexOf(header.toUpperCase())===0){hi=i;break;}}const start=hi>=0?hi+1:0;const dom=/^[A-Za-z0-9_*-]+(\.[A-Za-z0-9_*-]+)+$/;const out=[];for(let i=start;i<lines.length;i++){const l=lines[i];if(l.indexOf('|')<0)continue;const p=l.split('|');if(p.length<cols)continue;if(!dom.test((p[0]||'').trim()))continue;out.push(p);}return out;}
function dtRefresh(n){dtLoadDomains(n);dtLoadList(n);dtLoadPorts(n);}

// ---------- port-ha ----------
// se port ba `ratholectl set` avaz mishavand؛ baghi motealegh be halat-e khodeshan hastand
// (masalan plain/noise/backhaul port ra moghe-e roshan kardan migirand) va faghat neshan
// dade mishavand ta karbar tasvir-e kamel az port-ha dashte bashad.
const PORT_EDITABLE=[
 {key:'fake-port',    path:'fake',     ph:'8080'},
 {key:'sub-port',     path:'sub',      ph:'2096'},
 {key:'control-port', path:'control',  ph:'2333'},
];
const PATH_EDITABLE=[
 {key:'sub-path', path:'sub', ph:'sub'},
 {key:'hub-path', path:'hub', ph:'hub'},
];
const PORT_READONLY=[
 {path:'internal', k:'p_internal'},
 {path:'hub',      k:'p_hub'},
 {path:'plain',    k:'p_plain'},
 {path:'noise',    k:'p_noise'},
 {path:'backhaul', k:'p_backhaul'},
 {path:'direct',   k:'p_direct'},
];

function portsModal(n){
 modal(`<h3>${t('ports_sec')} (${n})</h3>
 <div class="sub" style="margin-bottom:6px">${h(t('ports_hint'))}</div>
 <div id="pt_ports"><div class="empty">${t('loading')}</div></div>
 <div class="row" style="justify-content:flex-end;margin-top:10px">
   <button class="s" onclick="run('${n}','regen_full');closeModal();">${t('dt_apply')}</button>
   <button class="gh" onclick="closeModal()">${t('close')}</button></div>`);
 dtLoadPorts(n);
}

async function dtLoadPorts(n){
 const box=$('pt_ports')||$('dt_ports'); if(!box)return;
 // agar cache khali bud, avval refresh kon ta port-ha neshan dade shavand
 if(!OVS[n]||!OVS[n].status||!OVS[n].status.ports){
   box.innerHTML=`<div class="empty">${t('loading')}...</div>`;
   await loadOv(n);
 }
 const ov=OVS[n]||{}; const ports=(ov.status&&ov.status.ports)||{};
 const paths=(ov.status&&ov.status.paths)||{};
 let x='';
 PORT_EDITABLE.forEach(p=>{
  const cur=ports[p.path];
  x+=`<div class="row"><label>${h(t('p_'+p.path))}</label>`
   + `<input id="pt_${p.path}" value="${cur==null?'':h(String(cur))}" placeholder="${p.ph}" style="max-width:110px">`
   + `<button class="g" onclick="dtSetPort('${n}','${p.key}','pt_${p.path}')">${t('save')}</button></div>`;
 });
 // masir-ha (path segment): sub/hub — yek kalame sade bedoon slash
 x+=`<div class="sub" style="margin:10px 0 4px">${h(t('paths_sec'))}</div>`;
 PATH_EDITABLE.forEach(p=>{
  const cur=paths[p.path]||p.ph;
  x+=`<div class="row"><label>${h(t('pth_'+p.path))}</label>`
   + `<span class="sub mono" style="align-self:center">/</span>`
   + `<input id="pth_${p.path}" value="${h(String(cur))}" placeholder="${p.ph}" style="max-width:140px">`
   + `<button class="g" onclick="dtSetPath('${n}','${p.key}','pth_${p.path}')">${t('save')}</button></div>`;
 });
 const ro=PORT_READONLY.filter(p=>ports[p.path]!=null)
   .map(p=>`${h(t(p.k))}: <b>${h(String(ports[p.path]))}</b>`).join(' · ');
 x+=`<div class="sub" style="margin-top:6px">${ro||t('ports_none')}</div>`;
 box.innerHTML=x;
}

// masir-ha faghat yek segment-e sade (harf/adad/_/-) — slash dar ratholectl ham rad mishavad.
function dtSetPath(n,key,id){
 const el=$(id); if(!el)return;
 const v=(el.value||'').trim().replace(/^\/+|\/+$/g,'');
 if(!/^[A-Za-z0-9_-]{1,40}$/.test(v)){toast(t('pth_bad'));return;}
 closeModal();
 run(n,'set_config',{key,value:v});
}

// ghabl az ersal tadakhol-e port ra check mikonim — nginx/rathole ba do sherkat rooye yek
// port bala nemiayand va peyda kardanash az log sakht ast.
function dtSetPort(n,key,id){
 const el=$(id); if(!el)return;
 const v=(el.value||'').trim();
 if(!/^[0-9]{1,5}$/.test(v)||+v<1||+v>65535){toast(t('p_bad'));return;}
 const ov=OVS[n]||{}; const ports=(ov.status&&ov.status.ports)||{};
 const mine=({'fake-port':'fake','sub-port':'sub','control-port':'control'})[key];
 const clash=Object.keys(ports).find(k=>k!==mine&&ports[k]!=null&&String(ports[k])===v);
 if(clash&&!confirm(t('p_clash').replace('%s',clash).replace('%p',v)))return;
 if(v==='443'&&!confirm(t('p_443')))return;
 closeModal();
 run(n,'set_config',{key,value:v});
}
async function dtApi(n,action,args){const {j}=await api('POST','api/servers/'+n+'/action',{action,args:args||{}});
 const out=((j&&j.cmd?('$ '+j.cmd+'\n'):'')+(((j&&j.out)||'')+((j&&j.err)?('\n'+j.err):''))).trim();if(out)toast(out);loadOv(n);return j;}
async function dtLoadDomains(n){
 const {j}=await api('POST','api/servers/'+n+'/action',{action:'domain_ls',args:{}});
 const box=$('dt_domains'); if(!box)return;
 const txt=(j&&j.out)||''; const rows=parseTable(txt,'DOMAIN|FULLCHAIN|KEY|PRIMARY');
 if(!rows.length){box.innerHTML='';return;}
 let x=`<div class="sub" style="margin:4px 0">${t('dt_served')}</div><table><tr><th>${t('dt_domain')}</th><th>${t('dt_kind')}</th><th></th></tr>`;
 rows.forEach(p=>{const dom=h(p[0]||'');const prim=(p[3]||'')==='yes';
  x+=`<tr><td>${dom}</td><td>${prim?('<span class="badge b-role">'+t('dt_primary')+'</span>'):('<span class="badge b-kcp">'+t('dt_extra')+'</span>')}</td><td>${prim?'':('<button class="g" onclick="dtMakePrimary(\''+n+'\',\''+dom+'\')">'+t('dt_makeprimary')+'</button> '+'<button class="r" onclick="dtRmDomain(\''+n+'\',\''+dom+'\')">'+t('remove')+'</button>')}</td></tr>`;});
 x+='</table>'; box.innerHTML=x;
}
async function dtAddDomain(n){const d=($('dt_nd').value||'').trim();if(!d){toast(t('fill'));return;}
 const fc=($('dt_nfc').value||'').trim(),key=($('dt_nkey').value||'').trim();
 const a={domain:d}; if(fc&&key){a.fullchain=fc;a.key=key;}else{a.certbot=1;}
 await dtApi(n,'domain_add',a); domainTls(n);}
async function dtRmDomain(n,d){if(!confirm(t('remove')+' '+d+' ?'))return; await dtApi(n,'domain_rm',{domain:d}); domainTls(n);}
async function dtMakePrimary(n,d){if(!confirm(t('dt_mp_confirm')+' '+d+' ?'))return; await dtApi(n,'domain_primary',{domain:d}); domainTls(n);}

function dtSet(n,key,id){const v=($(id).value||'').trim();if(!v){toast(t('fill'));return;}closeModal();run(n,'set_config',{key,value:v});}
function dtCert(n){const d=($('dt_ledom').value||'').trim();if(!d){toast(t('fill'));return;}
 const e=($('dt_leem').value||'').trim();const a={domain:d};if(e)a.email=e;closeModal();run(n,'tls_cert',a);}

function addNode(n){formModal(t('t_add_node'),[
  {id:'name',label:t('l_node_name'),req:1},
  {id:'inbound',label:t('l_xray_inb'),req:1},
  {id:'api_port',label:t('l_api_opt')}],
  v=>{closeModal();const a={name:v.name,inbound:v.inbound};if(v.api_port)a.api_port=v.api_port;run(n,'add_node',a);});}
function rmNode(n,name){if(confirm(t('cf_delnode')+' ('+name+')'))run(n,'rm_node',{name});}
function addSvc(n){formModal(t('t_add_svc'),[
  {id:'name',label:t('f_name'),req:1},
  {id:'token',label:t('l_token'),req:1},
  {id:'inbound',label:t('l_inbound'),req:1}],
  v=>{closeModal();run(n,'add_svc',v);});}
function rmSvc(n,name){if(confirm(t('cf_delsvc')+' ('+name+')'))run(n,'rm_svc',{name});}
function upAdd(n){formModal(t('t_up_add'),[
  {id:'id',label:t('l_up_id'),ph:'iran2',req:1},
  {id:'server',label:t('l_up_srv'),ph:'rp02.example.ir:443',req:1}],
  v=>{closeModal();run(n,'upstream_add',v);});}
function upAddSvc(n,id){formModal(t('t_up_addsvc')+' ('+id+')',[
  {id:'name',label:t('f_name'),req:1},
  {id:'token',label:t('l_token'),req:1},
  {id:'inbound',label:t('l_inbound'),req:1}],
  v=>{closeModal();run(n,'upstream_add_svc',{id,name:v.name,token:v.token,inbound:v.inbound});});}
function upRm(n,id){if(confirm(t('cf_delup')+' ('+id+') ?'))run(n,'upstream_rm',{id});}
function upRmSvc(n,id,name){if(confirm(t('cf_delupsvc')+' ('+id+'/'+name+') ?'))run(n,'upstream_rm_svc',{id,name});}
function fakewebStart(n){formModal(t('t_fw'),[

  {id:'port',label:t('l_fw_port')}],
  v=>{closeModal();run(n,'fakeweb_start',v.port?{port:v.port}:{});});}
function wdOn(n){formModal(t('t_wd'),[
  {id:'interval',label:t('l_wd_iv'),val:'60',req:1}],
  v=>{closeModal();run(n,'watchdog_on',{interval:v.interval||'60'});});}
function adaptiveOnNode(n){formModal(t('t_adaptive_node'),[
  {id:'interval',label:t('l_adaptive_iv'),val:'30',req:1},
  {id:'failures',label:t('l_adaptive_fa'),val:'3',req:1},
  {id:'recoveries',label:t('l_adaptive_re'),val:'5',req:1}],
  v=>{closeModal();run(n,'adaptive_on',{interval:v.interval||'30',failures:v.failures||'3',recoveries:v.recoveries||'5'});});}
function kcpOnIran(n){formModal(t('t_kcp_iran'),[
  {id:'port',label:t('l_udp'),val:'443',req:1},
  {id:'profile',label:t('l_profile'),type:'select',val:'balanced',opts:PROF}],
  v=>{closeModal();run(n,'kcp_on',{port:v.port,profile:v.profile||'balanced'});});}
function plainOnIran(n){formModal(t('t_plain_iran'),[
  {id:'port',label:t('l_plain_port'),val:'8880',req:1}],
  v=>{closeModal();run(n,'plain_on',{port:v.port});});}
function directOnIran(n){formModal(t('t_direct_iran'),[
  {id:'port',label:t('l_direct_port'),val:'8081',req:1},
  {id:'header',label:t('l_direct_header'),val:'X-Cdn-Id',req:1}],
  v=>{closeModal();run(n,'direct_on',{port:v.port,header:v.header});});}
function plainOnNode(n){formModal(t('t_plain_node'),[
  {id:'remote',label:t('l_plain_remote'),ph:'5.202.4.40:8880',req:1}],
  v=>{closeModal();run(n,'plain_on',{remote:v.remote});});}
function noiseOnIran(n){formModal(t('t_noise_iran'),[
  {id:'port',label:t('l_noise_port'),val:'2334',req:1}],
  v=>{closeModal();run(n,'noise_on',{port:v.port});});}
function noiseNode(n,act){formModal(t(act==='on'?'noise_node_on':'noise_node_off'),[
  {id:'name',label:t('c_name'),req:1}],
  v=>{closeModal();run(n,act==='on'?'noise_node_on':'noise_node_off',{name:v.name});});}
// autofill-e noise: az server Iran remote+pubkey ra migirad
async function noiseAutofill(iranName){
 if(!iranName){return;}
 toast(t('autofilling'));
 const {j}=await api('GET','api/servers/'+iranName+'/noiseconnect');
 if(!j||!j.ok){toast(t('autofail'));return;}
 if($('f_remote'))$('f_remote').value=j.remote||'';
 if($('f_pubkey'))$('f_pubkey').value=j.pubkey||'';
 if($('f_pattern')&&j.pattern)$('f_pattern').value=j.pattern;
 toast(t('autofilled'));
}
function noiseNodeFields(){
 const irs=iranServers();
 const f=[];
 if(irs.length){f.push({id:'iran',label:t('l_autofill'),type:'select',val:irs[0].name,
   opts:irs.map(s=>({v:s.name,t:s.name+' ('+s.host+')'}))});}
 f.push({id:'remote',label:t('l_noise_remote'),ph:'5.202.4.40:2334',req:1});
 f.push({id:'pubkey',label:t('l_noise_key'),req:1});
 f.push({id:'pattern',label:t('l_noise_pattern'),val:'Noise_NK_25519_ChaChaPoly_BLAKE2s'});
 return f;
}
function noiseOnNode(n){formModal(t('t_noise_node'),noiseNodeFields(),
  v=>{closeModal();run(n,'noise_on',{remote:v.remote,pubkey:v.pubkey,pattern:v.pattern||''});});
 const sel=$('f_iran');
 if(sel){sel.onchange=()=>noiseAutofill(sel.value);
   const box=sel.closest('.row');
   if(box){const b=document.createElement('button');b.className='s';b.textContent='↻';
     b.title=t('l_autofill');b.onclick=e=>{e.preventDefault();noiseAutofill(sel.value);};box.appendChild(b);}
   noiseAutofill(sel.value);
 }}

// ---- backhaul (core-e SMUX posht-e nginx/443) ----
// samt-e Iran transport-e BEDOON-e TLS migirad (nginx TLS ra terminate mikonad),
// samt-e node transport-e TLS-dar — in do amdan yeki nistand.
const BH_SRV_TR=[{v:'wsmux',t:'wsmux (mux)'},{v:'ws',t:'ws (bedoon mux)'}];
const BH_CLI_TR=[{v:'wssmux',t:'wssmux (mux)'},{v:'wss',t:'wss (bedoon mux)'}];
function bhOnIran(n){formModal(t('t_bh_iran'),[
  {id:'port',label:t('l_bh_port'),val:'3080',req:1},
  {id:'transport',label:t('l_bh_tr_srv'),type:'select',val:'wsmux',opts:BH_SRV_TR},
  {id:'profile',label:t('l_bh_prof'),type:'select',val:'balanced',opts:PROF}],
  v=>{closeModal();run(n,'backhaul_on',{port:v.port,transport:v.transport||'wsmux',profile:v.profile||'balanced'});});}
function bhNode(n,act){formModal(t(act==='on'?'bh_node_on':'bh_node_off'),[
  {id:'name',label:t('c_name'),req:1}],
  v=>{closeModal();run(n,act==='on'?'backhaul_node_on':'backhaul_node_off',{name:v.name});});}
// autofill-e backhaul: az server Iran domain+token+transport+profile ra migirad ta token dasti copy nashavad.
async function bhAutofill(iranName){
 if(!iranName){return;}
 toast(t('autofilling'));
 const {j}=await api('GET','api/servers/'+iranName+'/backhaulconnect');
 if(!j||!j.ok){toast(t('autofail'));return;}
 if($('f_domain'))$('f_domain').value=j.domain||'';
 if($('f_token'))$('f_token').value=j.token||'';
 if($('f_transport')&&j.transport)$('f_transport').value=j.transport;
 if($('f_profile')&&j.profile)$('f_profile').value=j.profile;
 toast(t('autofilled'));
}
function bhNodeFields(){
 const irs=iranServers();
 const f=[];
 if(irs.length){f.push({id:'iran',label:t('l_autofill'),type:'select',val:irs[0].name,
   opts:irs.map(s=>({v:s.name,t:s.name+' ('+s.host+')'}))});}
 f.push({id:'domain',label:t('l_bh_domain'),ph:'example.com',req:1});
 f.push({id:'token',label:t('l_bh_token'),req:1});
 f.push({id:'transport',label:t('l_bh_tr_cli'),type:'select',val:'wssmux',opts:BH_CLI_TR});
 f.push({id:'profile',label:t('l_bh_prof'),type:'select',val:'balanced',opts:PROF});
 return f;
}
// ============ reverse-proxy-e gheyre-tunnel ============
// /<name>/ rooye haman 443 be yek upstream-e delkhah. esm ba node-ha moshtarak ast
// (har do dar map-e /<name>) — samt-e ratholectl har do jahat check mishavad.
function pxAdd(n){formModal(t('t_px_add'),[
  {id:'name',label:t('px_name'),ph:'grafana',req:1},
  {id:'upstream',label:t('px_up'),ph:'http://127.0.0.1:3000',req:1}],
  v=>{
   if(!/^[A-Za-z0-9_-]{1,40}$/.test(v.name)){toast(t('px_bad_name'));return;}
   if(!/^https?:\/\/[A-Za-z0-9._-]{1,255}:[0-9]{1,5}$/.test(v.upstream)){toast(t('px_bad_up'));return;}
   closeModal();run(n,'proxy_add',{name:v.name,upstream:v.upstream});
  });}

function pxRm(n){formModal(t('t_px_rm'),[{id:'name',label:t('px_name'),req:1}],
  v=>{closeModal();run(n,'proxy_rm',{name:v.name});});}

// ============ HAMEL-e tunnel (carrier) — enhesari ============
// rooye node har panj halat HAMAN motaghayer-e TUNNEL ra minevisand، pas dar har lahze
// daghighan YEKI faal ast. in select haman vaghiat ra neshan midahad va avaz kardanash
// yek amal-e HEDAYAT-SHODE ast: parametrha khodkar az server Iran gerefte mishavand va
// (baraye noise/backhaul) samt-e Iran ham hamahang mishavad.
const CARRIERS=['ws','kcp','plain','noise','backhaul'];

function nodeCarrier(ov){
 const c=((ov||{}).main_tunnel||'ws');
 return CARRIERS.indexOf(c)>=0?c:'ws';
}

function carrierSelect(n,ov){
 const cur=nodeCarrier(ov);
 const opts=CARRIERS.map(c=>`<option value="${c}"${c===cur?' selected':''}>${h(t('carrier_'+c))}</option>`).join('');
 return `<select id="car_${n}" onchange="setCarrier('${n}',this.value,'${cur}')">${opts}</select>`;
}

// avaz kardan-e hamel. har halat form/parametr-e khodash ra darad؛ 'ws' bazgasht be
// pishfarz ast va faghat halat-e feli ra khamoosh mikonad.
function setCarrier(n,next,cur){
 if(next===cur)return;
 const sel=$('car_'+n);
 const revert=()=>{if(sel)sel.value=cur;};
 if(!confirm(t('carrier_confirm').replace('%s',t('carrier_'+next)))){revert();return;}
 switch(next){
   case 'ws':       run(n,carrierOffAction(cur)); break;
   case 'kcp':      kcpOnNode(n); break;
   case 'plain':    plainOnNode(n); break;
   case 'noise':    noiseOnNode(n); break;
   case 'backhaul': bhOnNode(n); break;
   default: revert();
 }
}

// bargasht be ws: har halat dastur-e off-e khodash ra darad.
function carrierOffAction(cur){
 return ({kcp:'kcp_off',plain:'plain_off',noise:'noise_off',backhaul:'backhaul_off'})[cur]||'kcp_off';
}

// ============ HAMEL-e per-UPSTREAM (mesl-e tunnel-e asli, vali baraye har upstream) ============
// har upstream yek server-e Iran-e mostaghel ast va TUNNEL-e khodash ra dar up_env darad،
// pas daghighan mesl-e tunnel-e asli ENHESARI ast: yek select، na chand dokme.
// backhaul inja NIST — backhaul yek core-e joda-ye 1:1 ast (yek token/yek ports baraye kol-e
// server-e Iran) va per-upstream mani nemidahad.
const UP_CARRIERS=['ws','kcp','plain','noise'];

function upCarrier(u){
 const c=((u||{}).tunnel||'ws');
 return UP_CARRIERS.indexOf(c)>=0?c:'ws';
}
function upCarrierSelect(n,u){
 const cur=upCarrier(u), id='upcar_'+n+'__'+u.id;
 const opts=UP_CARRIERS.map(c=>`<option value="${c}"${c===cur?' selected':''}>${h(t('carrier_'+c))}</option>`).join('');
 return `<select id="${id}" title="${h(t('carrier'))}" onchange="setUpCarrier('${n}','${esc(u.id)}',this.value,'${cur}')">${opts}</select>`;
}
// avaz kardan-e hamel-e yek upstream. har halat form/parametr-e khodash ra darad؛
// 'ws' bazgasht be pishfarz ast va har hamel-e digar ra khamoosh mikonad.
function setUpCarrier(n,id,next,cur){
 if(next===cur)return;
 const sel=$('upcar_'+n+'__'+id);
 const revert=()=>{if(sel)sel.value=cur;};
 if(!confirm(t('upcarrier_confirm').replace('%s',t('carrier_'+next)).replace('%n',id))){revert();return;}
 switch(next){
   case 'ws':    run(n,'upstream_ws',{id}); break;
   case 'kcp':   upKcpOn(n,id); break;
   case 'plain': upPlainOn(n,id); break;
   case 'noise': upNoiseOn(n,id); break;
   default: revert();
 }
}
// plain baraye upstream: faghat adres-e HTTP-e sade-ye an server-e Iran lazem ast.
function upPlainOn(n,id){formModal(t('t_plain_node')+' ('+id+')',[
  {id:'remote',label:t('l_plain_remote'),ph:'5.202.4.40:8880',req:1}],
  v=>{closeModal();run(n,'upstream_plain_on',{id,remote:v.remote});});}
// noise baraye upstream: hamon field-ha va autofill-e tunnel-e asli.
function upNoiseOn(n,id){formModal(t('t_noise_node')+' ('+id+')',noiseNodeFields(),
  v=>{closeModal();run(n,'upstream_noise_on',{id,remote:v.remote,pubkey:v.pubkey,pattern:v.pattern||''});});
 const sel=$('f_iran');
 if(sel){sel.onchange=()=>noiseAutofill(sel.value);
   const box=sel.closest('.row');
   if(box){const b=document.createElement('button');b.className='s';b.textContent='↻';
     b.title=t('l_autofill');b.onclick=e=>{e.preventDefault();noiseAutofill(sel.value);};box.appendChild(b);}
   noiseAutofill(sel.value);
 }}

// ============ MODE-e per-node SAMT-e IRAN (select mesl-e node) ============
// rooye Iran faghat noise/backhaul PER-NODE hastand (har node .transport-e khodash ra
// darad). kcp/plain HAMEL-e SARASARI-ye server-e Iran hastand (yek listener/core baraye
// hame), pas inja nemiayand va toggle-e sarasari-e khodeshan ra negah midarand. game ham
// transport nist — yek service-e L4-e joda (SNI) ast. pas select-e per-node = {ws,noise,backhaul}.
const IRAN_NODE_CARRIERS=['ws','noise','backhaul'];

// select-e per-node baraye node-haye Iran. baraye node-haye game (L4) select bi-mani ast.
function iranNodeCarrierSel(iran,ov,name){
 const mode=iranNodeMode(ov,name);
 if(mode==='game')return `<span class="badge b-game">${h(t('mode_game'))}</span>`;
 const cur=(mode==='noise'||mode==='backhaul')?mode:'ws';
 const id='icar_'+iran+'__'+name;
 const opts=IRAN_NODE_CARRIERS.map(c=>`<option value="${c}"${c===cur?' selected':''}>${h(t('carrier_'+c))}</option>`).join('');
 return `<select id="${id}" title="${h(t('carrier'))}" onchange="setIranNodeCarrier('${iran}','${esc(name)}',this.value,'${cur}')">${opts}</select>`;
}

// avaz kardan-e transport-e YEK node samt-e Iran. faghat action-haye mojood-e allow-list ra
// seda mizanad (noise_node_on/off, backhaul_node_on/off). YADAVARI: in nim-e Iran ast —
// samt-e node ham bayad hamon hamel bashad (carrierSelect-e safhe-ye node).
function setIranNodeCarrier(iran,name,next,cur){
 if(next===cur)return;
 const sel=$('icar_'+iran+'__'+name);
 const revert=()=>{if(sel)sel.value=cur;};
 if(!confirm(t('icarrier_confirm').replace('%s',t('carrier_'+next)).replace('%n',name))){revert();return;}
 switch(next){
   case 'ws':       run(iran, cur==='backhaul'?'backhaul_node_off':'noise_node_off',{name}); break;
   case 'noise':    run(iran,'noise_node_on',{name}); break;
   case 'backhaul': run(iran,'backhaul_node_on',{name}); break;
   default: revert();
 }
}

function bhOnNode(n){formModal(t('t_bh_node'),bhNodeFields(),
  v=>{closeModal();run(n,'backhaul_on',{domain:v.domain,token:v.token,transport:v.transport||'wssmux',profile:v.profile||'balanced'});});
 const sel=$('f_iran');
 if(sel){sel.onchange=()=>bhAutofill(sel.value);
   const box=sel.closest('.row');
   if(box){const b=document.createElement('button');b.className='s';b.textContent='↻';
     b.title=t('l_autofill');b.onclick=e=>{e.preventDefault();bhAutofill(sel.value);};box.appendChild(b);}
   bhAutofill(sel.value);
 }}

// list-e serverhaye Iran (baraye autofill-e KCP)
function iranServers(){return SERVERS.filter(s=>s.role==='iran');}
// gozine-haye <option> baraye entekhab-e server Iran (host be onvan value)
function iranSrvOptions(){return iranServers().map(s=>`<option value="${h(s.host)}">${h(s.name)} (${h(s.host)})</option>`).join('');}
// tunnel-e asli (main) ye node ra be yek server Iran vasl kon (SERVER=domain:443)
// mohem: dar halat-e pishfarz (ws+TLS) node bayad be DOMAIN-e omoomi vasl shavad, na host/IP-e
// SSH-e inventory — chon ratholenode az SERVER ham remote_addr va ham SNI ra misazad. pas
// entekhab az roo-ye NAM-e server Iran ast va maghsad-e daghigh (domain) ra az server migirim.
function setMainSrv(n){
 const irs=iranServers();
 if(!irs.length){toast(t('no_iran'));return;}
 const f=[{id:'iran',label:t('l_iran_srv'),type:'select',val:irs[0].name,
   opts:irs.map(s=>({v:s.name,t:s.name+' ('+s.host+')'}))}];
 formModal(t('set_main'),f,async v=>{
  const iran=(v.iran||'').trim(); if(!iran){toast(t('fill'));return;}
  closeModal();
  toast(t('autofilling'));
  // domain-e vaghei (ba cert-e mokhtabetesh) ra az server Iran begir, na host-e inventory
  const {j}=await api('GET','api/servers/'+iran+'/mainconnect');
  if(!j||!j.ok||!j.server){toast(t('autofail'));return;}
  run(n,'set_server',{server:j.server});
 });
}
// sim-keshi: yek node-e Iran (name/token/inbound) ra rooye yek node-e kharej (ya upstream-esh)
// be-onvan service ezafe kon. maghsadha: hameye node-ha + upstream-hayeshan; anha ke tunnel-eshan
// be hamin Iran vasl ast ba ✓ neshan dade va default entekhab mishavand.
function wireTargets(iranHost){
 const opts=[]; let def='';
 SERVERS.filter(s=>s.role==='node').forEach(s=>{
  const ov=OVS[s.name]; if(!ov||ov.reachable===false)return;
  const ms=String(ov.main_server||'');
  const hit=iranHost && (ms===iranHost || ms.split(':')[0]===iranHost);
  opts.push({v:s.name+'|', t:(hit?'✓ ':'')+s.name+' — main ('+(ms||'?')+')'});
  if(hit && !def)def=s.name+'|';
  (ov.upstreams||[]).forEach(u=>{
   const us=String(u.server||''); const uh=us && (us===iranHost || us.split(':')[0]===iranHost);
   opts.push({v:s.name+'|'+u.id, t:(uh?'✓ ':'')+s.name+' ▸ upstream '+u.id+' ('+(us||'?')+')'});
   if(uh && !def)def=s.name+'|'+u.id;
  });
 });
 return {opts, def:def||(opts[0]&&opts[0].v)||''};
}
async function wireNode(iranName,nodeName){
 const s=SERVERS.find(x=>x.name===iranName)||{}; const iranHost=s.host||'';
 const {opts,def}=wireTargets(iranHost);
 if(!opts.length){toast(t('no_node_dst'));return;}
 formModal(t('wire_title')+' · '+nodeName,
   [{id:'dst',label:t('l_dst_node'),type:'select',val:def,opts}],
   async v=>{
    const parts=(v.dst||'').split('|'); const dst=parts[0], up=parts[1]||'';
    if(!dst){toast(t('fill'));return;}
    closeModal();
    toast(t('autofilling'));
    // 1) token/inbound-e vaghei-ye node-e Iran ra begir (token dar 'ls' mask ast)
    const {j}=await api('GET','api/servers/'+iranName+'/nodeconnect/'+nodeName);
    if(!j||!j.ok){toast(t('wire_fail'));outModal(t('wire_title'),(j&&(j.error||j.raw))||'?');return;}
    // 2) rooye node-e kharej (ya upstream-esh) be-onvan service ezafe kon
    if(up)run(dst,'upstream_add_svc',{id:up,name:j.name,token:j.token,inbound:j.inbound});
    else  run(dst,'add_svc',{name:j.name,token:j.token,inbound:j.inbound});
   });
}
// autofill: az server Iran-e entekhab-shode remote/key/profile-e daghigh ra migirad
async function kcpAutofill(iranName){
 if(!iranName){return;}
 toast(t('autofilling'));
 const {j}=await api('GET','api/servers/'+iranName+'/kcpconnect');
 if(!j||!j.ok){toast(t('autofail'));return;}
 if($('f_remote'))$('f_remote').value=j.remote||'';
 if($('f_key'))$('f_key').value=j.key||'';
 if($('f_profile')&&j.profile)$('f_profile').value=j.profile;
 toast(t('autofilled'));
}
function kcpNodeFields(){
 const irs=iranServers();
 const f=[];
 if(irs.length){f.push({id:'iran',label:t('l_autofill'),type:'select',val:irs[0].name,
   opts:irs.map(s=>({v:s.name,t:s.name+' ('+s.host+')'}))});}
 f.push({id:'remote',label:t('l_remote'),ph:'5.202.4.40:443',req:1});
 f.push({id:'key',label:t('l_key'),req:1});
 f.push({id:'profile',label:t('l_profile'),type:'select',val:'balanced',opts:PROF});
 return f;
}
function kcpOnNode(n){formModal(t('t_kcp_node'),kcpNodeFields(),
  v=>{closeModal();run(n,'kcp_on',{remote:v.remote,key:v.key,profile:v.profile||'balanced'});});
 // dokme-ye autofill + trigger ba taghir-e select
 const sel=$('f_iran');
 if(sel){sel.onchange=()=>kcpAutofill(sel.value);
   const box=sel.closest('.row');
   if(box){const b=document.createElement('button');b.className='s';b.textContent='↻';
     b.title=t('l_autofill');b.onclick=e=>{e.preventDefault();kcpAutofill(sel.value);};box.appendChild(b);}
   kcpAutofill(sel.value); // avvalin bar khodkar por kon
 }}
function upKcpOn(n,id){formModal(t('t_kcp_up')+' ('+id+')',kcpNodeFields(),
  v=>{closeModal();run(n,'upstream_kcp_on',{id,remote:v.remote,key:v.key,profile:v.profile||'balanced'});});
 const sel=$('f_iran');
 if(sel){sel.onchange=()=>kcpAutofill(sel.value);
   const box=sel.closest('.row');
   if(box){const b=document.createElement('button');b.className='s';b.textContent='↻';
     b.onclick=e=>{e.preventDefault();kcpAutofill(sel.value);};box.appendChild(b);}
   kcpAutofill(sel.value);
 }}


function editNode(n,name){formModal(t('t_edit_node')+' ('+name+')',[
  {id:'inbound',label:t('l_inb_new')},
  {id:'api_port',label:t('l_api_new')}],
  v=>{const a={name};if(v.inbound)a.inbound=v.inbound;if(v.api_port)a.api_port=v.api_port;
   if(!a.inbound&&!a.api_port){toast(t('nochg'));return;}closeModal();run(n,'edit_node',a);});}
function renameNode(n,name){formModal(t('t_rename'),[
  {id:'new',label:t('l_new_name'),val:name,req:1}],
  v=>{if(v.new===name){closeModal();return;}closeModal();run(n,'rename_node',{old:name,new:v.new});});}
function editServer(n){const s=fnd(n);formModal(t('t_edit_srv')+' ('+n+')',[
  {id:'host',label:t('f_host'),val:s.host,req:1},
  {id:'ssh_user',label:t('f_user'),val:s.ssh_user||'root',req:1},
  {id:'ssh_port',label:t('f_port'),val:s.ssh_port||'22',req:1}],
  async v=>{const {status,j}=await api('PUT','api/servers/'+n,{host:v.host,ssh_user:v.ssh_user,ssh_port:v.ssh_port});
   if(status!==200){toast('error: '+(j.error||status));return;}closeModal();toast(t('saved'));loadAll();});}

async function savePw(){const cur=$('cpw').value,nw=$('npw').value;if(!nw){toast(t('need_newpw'));return;}const {status,j}=await api('POST','api/config',{current_password:cur,new_password:nw});if(status!==200){toast('error: '+(j.error||status));return;}toast(t('pw_changed'));$('cpw').value='';$('npw').value='';}
async function rotTok(){if(!confirm(t('cf_rottok')))return;const {status,j}=await api('POST','api/config',{rotate_token:true});if(status!==200){toast('error: '+(j.error||status));return;}TOKEN=j.api_token;localStorage.setItem('rh_token',TOKEN);toast(t('tok_applied'));renderSettingsPage();}
// refresh-e khodkar: faghat overview-haye safhe-ye faal (server SSH kamtar mikhorad)
setInterval(()=>{if($('auto')&&$('auto').checked&&TOKEN)pollByPage();},20000);
shell();
