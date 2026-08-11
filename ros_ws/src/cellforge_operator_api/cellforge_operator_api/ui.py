# ruff: noqa: E501
"""Dependency-free local operator page."""

OPERATOR_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>CellForge Operator</title>
  <style>
    :root{color-scheme:dark;--bg:#101516;--panel:#182124;--line:#2d3b3f;--ink:#eaf2ef;--muted:#9fb0aa;--ok:#74d49b;--bad:#ff8b82;--accent:#65c6d4}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:28px}
    header{display:flex;gap:16px;align-items:end;justify-content:space-between;border-bottom:1px solid var(--line);padding-bottom:18px}h1{margin:0;font-size:24px}h2{font-size:16px;margin:0 0 12px}.muted{color:var(--muted)}
    .auth{display:flex;gap:8px}input,button{border:1px solid var(--line);border-radius:6px;padding:9px;background:#11191b;color:var(--ink)}button{background:#23434a;cursor:pointer}button.danger{background:#542d2d}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px;margin-top:18px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:16px}.value{font-size:22px;margin:6px 0}.ok{color:var(--ok)}.bad{color:var(--bad)}pre{white-space:pre-wrap;word-break:break-word;color:var(--muted);max-height:360px;overflow:auto}ul{padding-left:20px}.warning{border-left:3px solid #e6b45f;padding-left:10px}
  </style>
</head>
<body><main>
  <header><div><h1>CellForge Operator</h1><div class="muted">Local cell interface · safety state is display-only</div></div><div class="auth"><input id="token" type="password" autocomplete="off" placeholder="Local bearer token"><button onclick="refresh()">Connect</button></div></header>
  <p class="warning">Independent rated hardware remains authoritative. This interface cannot bypass interlocks or implement functional safety.</p>
  <section class="grid"><article class="panel"><h2>Cell state</h2><div id="state" class="value">Disconnected</div><div id="readiness" class="muted"></div></article><article class="panel"><h2>Active identity</h2><div id="identity" class="muted">—</div></article><article class="panel"><h2>Active job</h2><div id="job" class="muted">—</div><button class="danger" onclick="cancelJob()">Request cancellation</button></article><article class="panel"><h2>Faults & approved recovery</h2><div id="faults" class="muted">—</div></article></section>
  <section class="panel" style="margin-top:14px"><h2>Submit approved job</h2><p class="muted">Exact bundle recipe/task references are revalidated by the job gateway.</p><textarea id="submission" rows="10" style="width:100%;background:#11191b;color:var(--ink);border:1px solid var(--line)">{"job_id":"","cell_id":"","recipe_id":"","recipe_version":1,"task_id":"","input_payload":{},"execution_mode":"simulation","idempotency_key":"","timeout_seconds":300}</textarea><button onclick="submitJob()">Submit job</button></section>
  <section class="panel" style="margin-top:14px"><h2>Local response</h2><pre id="output">No request made.</pre></section>
</main><script>
let current=null;let actions=[];const headers=()=>({'Authorization':'Bearer '+document.getElementById('token').value,'Content-Type':'application/json'});
async function call(path,options={}){options.headers=headers();const response=await fetch(path,options);const body=await response.json();document.getElementById('output').textContent=JSON.stringify(body,null,2);if(!response.ok)throw new Error(body.error?.message||'Request failed');return body}
async function refresh(){try{current=await call('/api/v1/status');actions=(await call('/api/v1/recovery-actions')).actions;state.textContent=current.state+(current.stale?' (STALE)':'');state.className='value '+(current.state==='READY'?'ok':'bad');readiness.textContent='Devices: '+current.all_required_devices_ready+' · Safety input healthy: '+current.safety_healthy;identity.textContent='Bundle '+current.identity.bundle_id+'\nRecipe '+(current.identity.recipe_id||'—')+' v'+(current.identity.recipe_version||'—');job.textContent=current.active_job?current.active_job.job_id+' · '+current.active_job.active_step:'No active job';faults.innerHTML=current.faults.length?'<ul>'+current.faults.map(f=>'<li>'+escapeText(f.code)+': '+escapeText(f.operator_message)+recoveryButtons(f)+'</li>').join('')+'</ul>':'No active faults'}catch(error){state.textContent='Unavailable';state.className='value bad'}}
async function submitJob(){const body=JSON.parse(document.getElementById('submission').value);await call('/api/v1/jobs',{method:'POST',body:JSON.stringify(body)});await refresh()}
async function cancelJob(){if(!current?.active_job)return;await call('/api/v1/jobs/'+encodeURIComponent(current.active_job.job_id)+'/cancel',{method:'POST',body:'{}'});await refresh()}
function recoveryButtons(fault){return fault.recovery_action_ids.map(id=>{const action=actions.find(a=>a.action_id===id);return action?'<div>'+escapeText(action.instructions)+(action.confirmation_required?' Confirmation: '+escapeText(action.confirmation):'')+' <button onclick="requestRecovery(\''+encodeURIComponent(id)+'\',\''+encodeURIComponent(fault.fault_id)+'\')">'+escapeText(action.label)+'</button></div>':''}).join('')}
async function requestRecovery(actionId,faultId){const action=actions.find(a=>a.action_id===decodeURIComponent(actionId));const confirmation=action?.confirmation_required?window.prompt('Enter the displayed confirmation phrase:')||'':'';await call('/api/v1/recovery-actions/'+actionId,{method:'POST',body:JSON.stringify({fault_id:decodeURIComponent(faultId),confirmation})});await refresh()}
function escapeText(value){const node=document.createElement('span');node.textContent=value;return node.innerHTML}
</script></body></html>"""
