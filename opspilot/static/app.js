'use strict';
let key = '';
let ws = null;
let me = null;
let reconnectTimer = null;
let reconnectAttempts = 0;
let socketGeneration = 0;
const $ = (selector) => document.querySelector(selector);
const safe = (text) => String(text ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function notify(message, good=false) {
  const el = $('#alert'); el.textContent = message; el.className = 'alert visible' + (good ? ' success' : '');
}
async function api(path, options={}) {
  if (!key) throw Error('Enter an API key and connect.');
  const response = await fetch(path, {...options, headers: {'X-API-Key': key, ...(options.body ? {'Content-Type':'application/json'} : {}), ...(options.headers || {})}});
  if (!response.ok) {
    let detail; try { detail = (await response.json()).detail; } catch { detail = response.statusText; }
    throw Error(`${response.status}: ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`);
  }
  if (options.raw) return response;
  return response.json();
}
const state = {summary:{},tasks:[]};
function bars(container, data, hues) {
  const entries = Object.entries(data || {});
  if (!entries.length) { $(container).innerHTML = '<p class="placeholder">No data yet</p>'; return; }
  const max = Math.max(1, ...entries.map(x => x[1]));
  $(container).innerHTML = entries.map(([name,n],i) => `<div><div class="bar-item-head"><span>${safe(name)}</span><span>${n}</span></div><div class="bar-track"><div class="bar-fill ${hues[i%hues.length]}" style="width:${100*n/max}%"></div></div></div>`).join('');
}
function render(snapshot) {
  state.summary = snapshot.summary; state.tasks = snapshot.tasks;
  $('#metric-total').textContent = state.summary.total_tasks;
  $('#metric-open').textContent = state.summary.status.open || 0;
  $('#metric-events').textContent = state.summary.events;
  $('#metric-approvals').textContent = state.summary.pending_approvals;
  bars('#status-bars', state.summary.status, ['', 'teal']);
  bars('#priority-bars', state.summary.priority, ['teal', 'orange', 'red']);
  $('#tasksCount').textContent = `${state.tasks.length} visible`;
  $('#taskRows').innerHTML = state.tasks.length ? state.tasks.map(t => `<tr><td>${safe(t.title)}</td><td><span class="pill ${safe(t.priority)}">${safe(t.priority)}</span></td><td><span class="pill ${safe(t.status)}">${safe(t.status)}</span></td><td>${safe(t.source)}</td><td>${t.status === 'open' && me?.role !== 'viewer' ? `<button class="button ghost tiny" data-complete="${safe(t.id)}">Request completion</button>` : '—'}</td></tr>`).join('') : '<tr><td colspan="5" class="placeholder">No tasks yet. Create or sync one.</td></tr>';
}
async function refresh() {
  if (!key) return;
  const [summary,tasks] = await Promise.all([api('/api/summary'),api('/api/tasks')]);
  render({summary,tasks});
  await loadIntegrations();
  if (me?.role === 'owner') await loadGovernance();
}
function setLiveStatus(label, isOnline=false) {
  const indicator = $('#connection');
  indicator.textContent = `● ${label}`;
  indicator.classList.toggle('online', isOnline);
}
function stopLive() {
  socketGeneration += 1;
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (ws) {
    const old = ws;
    ws = null;
    old.onclose = null; // User-initiated disconnect must not trigger reconnection.
    old.close();
  }
}
function scheduleReconnect(generation) {
  if (generation !== socketGeneration || !key || !me) return;
  const delay = Math.min(15000, 1000 * (2 ** Math.min(reconnectAttempts, 4)));
  reconnectAttempts += 1;
  setLiveStatus('Reconnecting');
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    openLive(generation);
  }, delay);
}
function openLive(generation) {
  if (generation !== socketGeneration || !key || !me) return;
  setLiveStatus(reconnectAttempts ? 'Reconnecting' : 'Connecting');
  let socket;
  try {
    socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/live`);
  } catch {
    scheduleReconnect(generation);
    return;
  }
  ws = socket;
  socket.onopen = () => {
    if (generation !== socketGeneration || socket !== ws) return;
    // Keep the API key out of the WebSocket URL and browser history.
    socket.send(JSON.stringify({api_key: key}));
    setLiveStatus('Authenticating');
  };
  socket.onmessage = (event) => {
    if (generation !== socketGeneration || socket !== ws) return;
    let frame;
    try { frame = JSON.parse(event.data); } catch { return; }
    if (frame.type === 'snapshot') {
      render(frame);
      reconnectAttempts = 0;
      setLiveStatus('Live', true); // Only show Live after an authenticated snapshot arrives.
    }
  };
  socket.onerror = () => {
    if (generation === socketGeneration && socket === ws) setLiveStatus('Connection error');
  };
  socket.onclose = (event) => {
    if (generation !== socketGeneration || socket !== ws) return;
    ws = null;
    if (event.code === 1008) {
      setLiveStatus('Authentication failed');
      notify('Live connection authentication rejected. Reconnect the workspace.');
      return;
    }
    scheduleReconnect(generation);
  };
}
function startLive() {
  stopLive();
  reconnectAttempts = 0;
  openLive(socketGeneration);
}
async function connect() {
  const incoming = $('#apiKey').value.trim();
  if (!incoming) return notify('Enter an API key.');
  stopLive();
  key = incoming;
  try {
    me = await api('/api/me'); $('#identity').textContent = `${me.org_id} · ${me.role}`;
    notify(`Connected as ${me.name}`, true); await refresh(); startLive();
  } catch (e) {key = ''; me = null; setLiveStatus('Disconnected'); notify(e.message);}
}
function disconnect() {
  key = ''; me = null; $('#apiKey').value=''; $('#identity').textContent='No workspace';
  stopLive(); setLiveStatus('Disconnected'); notify('Disconnected. Refresh to clear displayed metrics.',true);
  window.location.reload();
}
async function loadIntegrations() {
  const list = await api('/api/integrations');
  $('#integrationsList').innerHTML = list.length ? list.map(i => `<div class="integration-item"><div><strong>${safe(i.name)}</strong><small>${safe(i.kind)} · Cursor ${i.cursor} · ${safe(i.id.slice(0,8))}</small></div>${me?.role === 'viewer' ? '' : i.kind === 'csv_upload' ? `<button data-csv="${safe(i.id)}" class="button ghost tiny">Import CSV</button>` : `<button data-sync="${safe(i.id)}" class="button ghost tiny">Sync now</button>`}</div>`).join('') : '<p class="placeholder">No connectors yet. Add the demo connector to start a sync.</p>';
}
async function loadGovernance() {
  const [approvals,audits] = await Promise.all([api('/api/approvals'), api('/api/audit')]);
  $('#approvalsList').innerHTML = approvals.filter(a=>a.status==='pending').map(a => `<div class="approval-item"><div><strong>${safe(a.tool)}</strong><small>${safe(a.actor)} · ${safe(a.arguments)}</small></div><div class="approval-buttons"><button data-review="approve" data-id="${safe(a.id)}" class="button primary tiny">Approve</button><button data-review="reject" data-id="${safe(a.id)}" class="button ghost tiny">Reject</button></div></div>`).join('') || '<p class="placeholder">No pending approvals.</p>';
  $('#auditList').innerHTML = audits.slice(0,12).map(a=>`<div class="audit-item"><strong>${safe(a.tool)} · ${safe(a.outcome)}</strong><small>${safe(a.actor)} · ${safe(a.created_at)}</small></div>`).join('') || '<p class="placeholder">No activity yet.</p>';
}
$('#connect').addEventListener('click', connect);
$('#apiKey').addEventListener('keydown', (e)=>{if(e.key==='Enter')connect();});
$('#disconnect').addEventListener('click', disconnect);
$('#taskForm').addEventListener('submit', async(e)=>{e.preventDefault();try{const t=await api('/api/tasks',{method:'POST',body:JSON.stringify({title:$('#taskTitle').value,priority:$('#taskPriority').value})});$('#taskTitle').value='';notify(`Created task ${t.id.slice(0,8)}`,true);await refresh();}catch(err){notify(err.message);}});
$('#agentForm').addEventListener('submit',async(e)=>{e.preventDefault();$('#agentResult').textContent='Running agents...';try{const result=await api('/api/agent/run',{method:'POST',body:JSON.stringify({objective:$('#objective').value})});$('#agentResult').textContent=JSON.stringify(result,null,2);await refresh();}catch(err){$('#agentResult').textContent=err.message;}});
$('#addIntegration').addEventListener('click',async()=>{try{await api('/api/integrations',{method:'POST',body:JSON.stringify({name:'Demo Ticket Pipeline'})});notify('Connector registered',true);await refresh();}catch(err){notify(err.message);}});
$('#addCsvIntegration').addEventListener('click',async()=>{try{await api('/api/integrations',{method:'POST',body:JSON.stringify({name:'Spreadsheet Intake',kind:'csv_upload'})});notify('Spreadsheet source registered',true);await refresh();}catch(err){notify(err.message);}});
let selectedCsvIntegration = null;
$('#csvFile').addEventListener('change',async(e)=>{const file=e.target.files[0];if(!file||!selectedCsvIntegration)return;try{const data=await file.text();const r=await api(`/api/integrations/${encodeURIComponent(selectedCsvIntegration)}/import-csv`,{method:'POST',body:data,headers:{'Content-Type':'text/csv'}});notify(`Imported ${r.created} tasks; skipped ${r.deduplicated} duplicates`,true);await refresh();}catch(err){notify(err.message);}finally{e.target.value='';selectedCsvIntegration=null;}});
$('#export').addEventListener('click',async()=>{try{const r=await api('/api/tasks.csv',{raw:true});const b=await r.blob();const u=URL.createObjectURL(b);const a=document.createElement('a');a.href=u;a.download='opspilot-tasks.csv';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}catch(err){notify(err.message);}});
$('#reloadGovernance').addEventListener('click',async()=>{try{await loadGovernance();}catch(err){notify(err.message);}});
document.addEventListener('click',async(e)=>{
  const syncId=e.target.getAttribute('data-sync');const taskId=e.target.getAttribute('data-complete');const decision=e.target.getAttribute('data-review');const csvId=e.target.getAttribute('data-csv');
  try {
    if(csvId){selectedCsvIntegration=csvId;$('#csvFile').click();}
    if(syncId){const r=await api(`/api/integrations/${encodeURIComponent(syncId)}/sync`,{method:'POST'});notify(`Sync imported ${r.created} events (cursor ${r.cursor})`,true);await refresh();}
    if(taskId){const r=await api('/api/tools/call',{method:'POST',body:JSON.stringify({name:'tasks.complete',arguments:{task_id:taskId}})});notify(`Approval requested: ${r.approval_id}`,true);await refresh();}
    if(decision){const id=e.target.getAttribute('data-id');const r=await api(`/api/approvals/${encodeURIComponent(id)}/review`,{method:'POST',body:JSON.stringify({decision})});notify(`Approval ${r.status}`,true);await refresh();}
  } catch(err){notify(err.message);}
});
