from __future__ import annotations

import json
import sys
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, Response, redirect, render_template_string, request, send_from_directory, url_for

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline import analyze_app

app = Flask(__name__)

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


# ─── Index Page (light theme, matches report.html) ───────────────────────────

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Splunk Agent-Readiness Engine</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',system-ui,sans-serif;background:#f0f2f5;color:#1e2530;font-size:14px;line-height:1.6}
.page{max-width:860px;margin:0 auto;padding:36px 20px}

/* Header */
.header{background:#fff;border:1px solid #dde1e9;border-radius:10px;padding:20px 24px;margin-bottom:20px;display:flex;align-items:center;justify-content:space-between}
.header-left h1{font-size:18px;font-weight:700;color:#0f1623}
.header-left p{font-size:12px;color:#8492a6;margin-top:2px}
.badge{font-size:11px;font-weight:600;padding:4px 10px;border-radius:20px;background:#dbeafe;color:#1d4ed8}

/* Panel */
.panel{background:#fff;border:1px solid #dde1e9;border-radius:10px;margin-bottom:16px;overflow:hidden}
.panel-head{padding:14px 20px;border-bottom:1px solid #eaecf0;display:flex;align-items:center;justify-content:space-between}
.panel-head h2{font-size:14px;font-weight:600;color:#0f1623}
.panel-body{padding:20px}

/* Form */
.field{margin-bottom:16px}
.field label{display:block;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:#8492a6;margin-bottom:6px}
.field select,.field input{width:100%;padding:10px 12px;border:1px solid #dde1e9;border-radius:7px;font-size:13px;color:#1e2530;background:#fff;font-family:inherit;outline:none;transition:border-color .15s,box-shadow .15s}
.field select:focus,.field input:focus{border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,.08)}
.field .hint{font-size:11px;color:#8492a6;margin-top:4px}
.row-2{display:grid;grid-template-columns:1fr 1fr;gap:14px}

/* App list */
.app-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;padding:16px 20px}
.app-card{border:2px solid #eaecf0;border-radius:8px;padding:14px 16px;cursor:pointer;transition:border-color .15s,background .15s;background:#fafbfc}
.app-card:hover{border-color:#2563eb;background:#f0f6ff}
.app-card.selected{border-color:#2563eb;background:#eff6ff}
.app-card-name{font-size:13px;font-weight:600;color:#0f1623;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.app-card-label{font-size:11px;color:#8492a6;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.loading-apps{padding:24px 20px;color:#8492a6;font-size:13px;text-align:center}

/* Button */
.btn{width:100%;padding:11px;background:#2563eb;color:#fff;font-weight:600;font-size:13px;border:none;border-radius:7px;cursor:pointer;font-family:inherit;transition:background .15s,transform .1s;margin-top:4px}
.btn:hover{background:#1d4ed8}
.btn:active{transform:scale(.99)}
.btn:disabled{background:#a5b4c6;cursor:not-allowed}

/* Progress */
.progress-panel{display:none;background:#fff;border:1px solid #dde1e9;border-radius:10px;overflow:hidden;margin-bottom:16px}
.progress-panel.visible{display:block}
.progress-head{padding:14px 20px;border-bottom:1px solid #eaecf0;display:flex;align-items:center;gap:10px}
.spinner{width:16px;height:16px;border-radius:50%;border:2px solid #e5e9f0;border-top-color:#2563eb;animation:spin .7s linear infinite;flex-shrink:0}
.spinner.done{border-top-color:#16a34a;animation:none}
@keyframes spin{to{transform:rotate(360deg)}}
.progress-title{font-size:13px;font-weight:600;color:#0f1623}
.pbar-wrap{height:3px;background:#f0f2f5}
.pbar{height:100%;background:#2563eb;width:0%;transition:width .4s ease}
.log-box{padding:14px 20px;font-family:'JetBrains Mono',monospace;font-size:12px;color:#374151;max-height:220px;overflow-y:auto;line-height:1.8;background:#fafbfc}
.log-ok{color:#16a34a}.log-warn{color:#d97706}.log-err{color:#dc2626}.log-info{color:#2563eb}

/* Features */
.feat-row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:4px}
.feat{background:#fff;border:1px solid #dde1e9;border-radius:8px;padding:16px}
.feat-icon{font-size:18px;margin-bottom:8px}
.feat-title{font-size:12px;font-weight:600;color:#0f1623;margin-bottom:3px}
.feat-desc{font-size:11px;color:#8492a6;line-height:1.5}

@media(max-width:640px){.row-2,.feat-row{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="page">

<div class="header">
  <div class="header-left">
    <h1>Splunk Agent-Readiness Engine</h1>
    <p>Scan any installed app and generate an instant MCP compatibility patch</p>
  </div>
  <span class="badge">Hackathon 2026</span>
</div>

<!-- App selector panel -->
<div class="panel">
  <div class="panel-head">
    <h2>Select a Splunk App</h2>
    <span id="app-count" style="font-size:12px;color:#8492a6"></span>
  </div>
  <div id="app-list" class="loading-apps">Loading apps from Splunk…</div>
</div>

<!-- Config + run -->
<div class="panel">
  <div class="panel-head"><h2>Run Analysis</h2></div>
  <div class="panel-body">
    <div class="row-2">
      <div class="field">
        <label>Selected App</label>
        <input id="selected-app-display" readonly placeholder="Pick an app above" style="background:#f8fafc;color:#8492a6">
        <input type="hidden" id="selected-app-name">
      </div>
      <div class="field">
        <label>Max Searches (0 = all)</label>
        <input id="limit-input" type="number" value="0" min="0" max="200">
        <div class="hint">Limit to speed up analysis on large apps</div>
      </div>
    </div>
    <button class="btn" id="run-btn" onclick="startAnalysis()" disabled>Run Analysis</button>
  </div>
</div>

<!-- Progress -->
<div class="progress-panel" id="progress-panel">
  <div class="progress-head">
    <div class="spinner" id="spinner"></div>
    <div class="progress-title" id="progress-title">Initialising…</div>
  </div>
  <div class="pbar-wrap"><div class="pbar" id="pbar"></div></div>
  <div class="log-box" id="log-box"></div>
</div>

<!-- Feature cards -->
<div class="feat-row">
  <div class="feat"><div class="feat-icon">🔬</div><div class="feat-title">Deep Scan</div><div class="feat-desc">Reads saved searches, macros, dashboards, lookups via REST API.</div></div>
  <div class="feat"><div class="feat-icon">🏥</div><div class="feat-title">Health Check</div><div class="feat-desc">Flags deprecated commands, hardcoded IPs and SPL anti-patterns.</div></div>
  <div class="feat"><div class="feat-icon">🤖</div><div class="feat-title">AI Descriptions</div><div class="feat-desc">Groq (Llama 3.3) generates agent-optimised descriptions for every object.</div></div>
  <div class="feat"><div class="feat-icon">🔗</div><div class="feat-title">MCP Patch</div><div class="feat-desc">Drop-in <code>agent_ready_patch.conf</code> — zero SPL changes needed.</div></div>
</div>

</div>
<script>
// ── Load app list from Splunk ──────────────────────────────────────────────
let selectedApp = '';

fetch('/apps')
  .then(r => {
    if (!r.ok) return r.json().then(e => Promise.reject(e.error || 'Server error ' + r.status));
    return r.json();
  })
  .then(apps => {
    const list = document.getElementById('app-list');
    const count = document.getElementById('app-count');
    if (!Array.isArray(apps) || !apps.length) {
      list.textContent = 'No apps found — is Splunk running on localhost:8089?';
      return;
    }
    count.textContent = apps.length + ' apps installed';
    list.className = 'app-grid';
    list.innerHTML = '';
    apps.forEach(a => {
      const card = document.createElement('div');
      card.className = 'app-card';
      card.innerHTML = '<div class="app-card-name">' + a.name + '</div><div class="app-card-label">' + a.label + '</div>';
      card.onclick = () => selectApp(a.name, a.label, card);
      list.appendChild(card);
    });
  })
  .catch(err => {
    const list = document.getElementById('app-list');
    list.innerHTML = '<span style="color:#dc2626">⚠ ' + err + '</span>';
  });

function selectApp(name, label, card) {
  document.querySelectorAll('.app-card').forEach(c => c.classList.remove('selected'));
  card.classList.add('selected');
  selectedApp = name;
  document.getElementById('selected-app-display').value = label + '  (' + name + ')';
  document.getElementById('selected-app-name').value = name;
  document.getElementById('run-btn').disabled = false;
}

// ── Run analysis ───────────────────────────────────────────────────────────
function startAnalysis() {
  if (!selectedApp) return;
  const limit = document.getElementById('limit-input').value;
  const panel = document.getElementById('progress-panel');
  const logBox = document.getElementById('log-box');
  const pbar = document.getElementById('pbar');
  const spinner = document.getElementById('spinner');
  const title = document.getElementById('progress-title');
  const btn = document.getElementById('run-btn');

  panel.classList.add('visible');
  logBox.innerHTML = '';
  pbar.style.width = '0%';
  spinner.className = 'spinner';
  btn.disabled = true;
  btn.textContent = 'Running…';

  const data = new FormData();
  data.append('app', selectedApp);
  data.append('limit', limit);
  data.append('config', 'config/config.yaml');

  fetch('/analyze', { method: 'POST', body: data })
    .then(r => r.json())
    .then(info => {
      if (info.error) { addLog('err', '✗ ' + info.error); return; }
      pollJob(info.job_id, pbar, spinner, title, btn);
    })
    .catch(err => addLog('err', '✗ ' + err));
}

function addLog(cls, msg) {
  const lb = document.getElementById('log-box');
  const p = document.createElement('p');
  p.className = 'log-' + cls;
  p.textContent = msg;
  lb.appendChild(p);
  lb.scrollTop = lb.scrollHeight;
}

function pollJob(jobId, pbar, spinner, title, btn) {
  const es = new EventSource('/job/' + jobId + '/stream');
  es.onmessage = ev => {
    const d = JSON.parse(ev.data);
    if (d.type === 'log') {
      addLog(d.cls || 'info', d.msg);
      pbar.style.width = (d.progress || 0) + '%';
      title.textContent = d.msg;
    } else if (d.type === 'done') {
      es.close();
      spinner.className = 'spinner done';
      title.textContent = '✓ Analysis complete — opening report…';
      pbar.style.width = '100%';
      setTimeout(() => window.location.href = '/report/' + jobId, 1000);
    } else if (d.type === 'error') {
      es.close();
      addLog('err', '✗ ' + d.msg);
      btn.disabled = false;
      btn.textContent = 'Run Analysis';
    }
  };
  es.onerror = () => {
    es.close();
    addLog('err', 'Connection lost.');
    btn.disabled = false;
    btn.textContent = 'Run Analysis';
  };
}
</script>
</body>
</html>
"""


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return render_template_string(INDEX_HTML)


@app.get("/apps")
def list_apps():
    """Return installed visible Splunk apps as JSON for the dropdown."""
    try:
        import requests as _req
        import urllib3
        urllib3.disable_warnings()

        from src.config import load_yaml_config
        config = load_yaml_config("config/config.yaml")
        cfg = config["splunk"]
        host = cfg.get("host", "localhost")
        port = cfg.get("port", 8089)
        scheme = cfg.get("scheme", "https")
        username = cfg["username"]
        password = cfg["password"]
        verify_ssl = cfg.get("verify_ssl", False)

        base = f"{scheme}://{host}:{port}"
        resp = _req.get(
            f"{base}/services/apps/local",
            auth=(username, password),
            params={"output_mode": "json", "count": 0},
            timeout=10,
            verify=verify_ssl,
        )
        resp.raise_for_status()
        entries = resp.json().get("entry", [])
        apps = [
            {"name": e["name"], "label": e.get("content", {}).get("label", e["name"])}
            for e in entries
            if e.get("content", {}).get("visible", True)
        ]
        apps.sort(key=lambda x: x["label"].lower())
        return json.dumps(apps)
    except Exception as exc:
        import traceback
        return json.dumps({"error": str(exc), "detail": traceback.format_exc()}), 500


@app.post("/analyze")
def analyze():
    job_id = request.form.get("job_id") or str(uuid.uuid4())
    app_name = request.form.get("app", "")
    config_path = request.form.get("config") or "config/config.yaml"
    app_path = request.form.get("app_path") or None
    limit = int(request.form.get("limit") or 0)

    with _jobs_lock:
        _jobs[job_id] = {"status": "running", "log": [], "result": None, "error": None}

    def run():
        logs = _jobs[job_id]["log"]

        def emit(msg, cls="", progress=0):
            logs.append({"type": "log", "msg": msg, "cls": cls, "progress": progress})

        try:
            emit(f"Scanning app: {app_name}…", "info", 5)
            result = analyze_app(
                app=app_name,
                config_path=config_path,
                app_path=app_path,
                offline_ai=False,
                limit=limit,
            )
            emit(f"✓ {len(result['app_data']['saved_searches'])} saved searches", "ok", 40)
            emit(f"✓ {len(result['app_data']['macros'])} macros", "ok", 55)
            emit(f"✓ {len(result['app_data']['dashboards'])} dashboards", "ok", 65)
            emit(f"✓ {result['scoring']['mcp_blockers']} objects missing description", "warn", 80)
            emit(f"✓ Score: {result['scoring']['overall_score']}/100 — {result['scoring']['grade']}", "ok", 92)
            emit("✓ Report ready", "ok", 98)
            _jobs[job_id]["result"] = result
            _jobs[job_id]["status"] = "done"
            logs.append({"type": "done"})
        except Exception as exc:
            import traceback
            _jobs[job_id]["error"] = traceback.format_exc()
            _jobs[job_id]["status"] = "error"
            logs.append({"type": "error", "msg": str(exc)})

    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job_id}


@app.get("/job/<job_id>/stream")
def job_stream(job_id: str):
    def generate():
        sent = 0
        while True:
            with _jobs_lock:
                job = _jobs.get(job_id)
            if not job:
                yield f"data: {json.dumps({'type':'error','msg':'Job not found'})}\n\n"
                return
            logs = job["log"]
            while sent < len(logs):
                yield f"data: {json.dumps(logs[sent])}\n\n"
                sent += 1
            if job["status"] in ("done", "error"):
                return
            time.sleep(0.3)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/report/<job_id>")
def report_page(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job or not job.get("result"):
        return redirect(url_for("index"))
    report_path = job["result"]["paths"]["report"]
    return Path(report_path).read_text(encoding="utf-8")


@app.get("/output/<path:filename>")
def output_file(filename: str):
    return send_from_directory(Path("output").resolve(), filename)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
