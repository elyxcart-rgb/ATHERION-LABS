"""SONIC AI — Live Web Dashboard.

A Flask-based web dashboard that shows SONIC's automation status in real
time. Built with zero-JS dependency: Server-Sent Events (SSE) push from
the RealtimeEngine + plain HTML polling fallback. Beautiful sci-fi UI
that matches the bootstrap redesign.

Usage:
    python -m automation.dashboard
    # or
    from automation.dashboard import create_app
    app = create_app()
    app.run(host="127.0.0.1", port=7654)

Then open http://127.0.0.1:7654/

Routes:
    GET  /                        — main dashboard
    GET  /api/snapshot            — JSON snapshot of all jobs
    GET  /api/stream              — SSE stream of job updates
    GET  /api/templates           — list workflow templates
    POST /api/templates/<name>    — run a template (returns job_id)
    GET  /api/watches             — list file watches
    POST /api/watches             — start a watch
    DELETE /api/watches/<token>   — stop a watch
    GET  /api/schedules           — list scheduled tasks
    POST /api/schedules           — add a scheduled task
    DELETE /api/schedules/<token> — remove a scheduled task

Zero-touch design: no existing file is modified.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
from pathlib import Path

logger = logging.getLogger("DASHBOARD")


# ═════════════════════════════════════════════════════════════════════════════
# HTML — self-contained, no JS framework required
# ═════════════════════════════════════════════════════════════════════════════

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SONIC Apex — Live Automation</title>
<style>
  :root {
    --bg:         #020408;
    --bg-elev:    #0a0e18;
    --bg-card:    rgba(20,30,50,0.55);
    --cyan:       #00d9ff;
    --cyan-dim:   #0080a0;
    --green:      #30d158;
    --red:        #ff453a;
    --amber:      #ffd60a;
    --text:       #e6edf3;
    --text-dim:   #8a96a8;
    --border:     rgba(0,217,255,0.22);
    --border-strong: rgba(0,217,255,0.50);
    --mono:       "Cascadia Code", "Consolas", "Menlo", monospace;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; background: var(--bg); color: var(--text);
    font-family: var(--mono); font-size: 13px; line-height: 1.5; }
  body { padding: 24px 32px; overflow-x: hidden; }
  body::before {
    content: ""; position: fixed; inset: 0; pointer-events: none;
    background:
      radial-gradient(circle at 30% 20%, rgba(0,120,200,0.10), transparent 50%),
      radial-gradient(circle at 80% 70%, rgba(0,80,160,0.07), transparent 50%);
    z-index: -1;
  }
  header {
    display: flex; align-items: baseline; gap: 16px;
    margin-bottom: 28px; padding-bottom: 14px;
    border-bottom: 1px solid var(--border);
  }
  h1 {
    font-size: 22px; font-weight: 700; letter-spacing: 2px;
    background: linear-gradient(90deg, var(--cyan), #fff);
    -webkit-background-clip: text; background-clip: text; color: transparent;
  }
  .sub { color: var(--text-dim); font-size: 11px; letter-spacing: 1.5px; }
  .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 24px; }
  .stat {
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 10px; padding: 14px 18px;
  }
  .stat .label {
    font-size: 9px; color: var(--text-dim); letter-spacing: 1.8px;
    text-transform: uppercase; margin-bottom: 4px;
  }
  .stat .value {
    font-size: 28px; font-weight: 700; letter-spacing: 0.5px;
  }
  .stat.running .value { color: var(--cyan); text-shadow: 0 0 8px var(--cyan-dim); }
  .stat.queued  .value { color: var(--amber); }
  .stat.done    .value { color: var(--green); }
  .stat.failed  .value { color: var(--red); }
  .grid { display: grid; grid-template-columns: 1.4fr 1fr; gap: 24px; }
  .panel {
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 12px; padding: 18px 20px;
  }
  .panel h2 {
    font-size: 11px; color: var(--cyan); letter-spacing: 2px;
    text-transform: uppercase; margin-bottom: 14px;
    padding-bottom: 8px; border-bottom: 1px solid var(--border);
  }
  .job { padding: 12px 0; border-bottom: 1px solid rgba(0,217,255,0.08); }
  .job:last-child { border-bottom: none; }
  .job .row { display: flex; align-items: center; gap: 10px; }
  .job .name { font-weight: 600; font-size: 13px; flex: 1; }
  .badge {
    padding: 2px 8px; border-radius: 4px; font-size: 9px;
    letter-spacing: 1.2px; text-transform: uppercase; font-weight: 700;
  }
  .badge.queued    { background: rgba(255,214,10,0.18); color: var(--amber); }
  .badge.running   { background: rgba(0,217,255,0.18); color: var(--cyan); }
  .badge.done      { background: rgba(48,209,88,0.18); color: var(--green); }
  .badge.failed    { background: rgba(255,69,58,0.18); color: var(--red); }
  .badge.cancelled { background: rgba(138,150,168,0.18); color: var(--text-dim); }
  .progress {
    margin-top: 8px; height: 4px; background: rgba(0,217,255,0.10);
    border-radius: 2px; overflow: hidden; position: relative;
  }
  .progress .fill {
    height: 100%; background: linear-gradient(90deg, var(--cyan-dim), var(--cyan));
    transition: width 0.4s ease-out;
    box-shadow: 0 0 8px rgba(0,217,255,0.6);
  }
  .log {
    margin-top: 6px; max-height: 80px; overflow-y: auto;
    background: rgba(0,0,0,0.30); border-radius: 4px;
    padding: 6px 10px; font-size: 10.5px; color: var(--text-dim); white-space: pre-wrap;
  }
  .log-line { display: block; }
  .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
  .btn {
    background: transparent; color: var(--cyan); border: 1px solid var(--border-strong);
    border-radius: 6px; padding: 7px 13px; font-family: var(--mono);
    font-size: 11px; letter-spacing: 1.2px; cursor: pointer;
    transition: all 0.15s ease-out;
  }
  .btn:hover { background: rgba(0,217,255,0.10); border-color: var(--cyan); }
  .btn:active { transform: translateY(1px); }
  .btn.warn { color: var(--amber); border-color: rgba(255,214,10,0.45); }
  .btn.danger { color: var(--red); border-color: rgba(255,69,58,0.45); }
  .empty { color: var(--text-dim); font-size: 11px; text-align: center; padding: 18px 0; }
  .meta { font-size: 10px; color: var(--text-dim); margin-top: 4px; }
  .footer {
    margin-top: 24px; padding-top: 14px; border-top: 1px solid var(--border);
    font-size: 10px; color: var(--text-dim); text-align: right; letter-spacing: 1px;
  }
  .live-dot {
    display: inline-block; width: 6px; height: 6px; border-radius: 50%;
    background: var(--green); box-shadow: 0 0 6px var(--green);
    animation: pulse 1.5s ease-in-out infinite; margin-left: 6px;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50%      { opacity: 0.3; }
  }
  .scroll { max-height: 600px; overflow-y: auto; }
</style>
</head>
<body>
  <header>
    <h1>SONIC.APEX</h1>
    <span class="sub">LIVE AUTOMATION CONSOLE</span>
    <span class="live-dot" id="live-dot" title="Live updates via SSE"></span>
  </header>

  <div class="stats">
    <div class="stat running"><div class="label">Running</div>
      <div class="value" id="stat-running">0</div></div>
    <div class="stat queued"><div class="label">Queued</div>
      <div class="value" id="stat-queued">0</div></div>
    <div class="stat done"><div class="label">Completed</div>
      <div class="value" id="stat-done">0</div></div>
    <div class="stat failed"><div class="label">Failed</div>
      <div class="value" id="stat-failed">0</div></div>
  </div>

  <div class="grid">
    <div class="panel">
      <h2>Workflow Templates</h2>
      <div id="templates" class="actions"></div>

      <h2 style="margin-top: 22px;">Active Jobs</h2>
      <div id="jobs" class="scroll"></div>
    </div>

    <div class="panel">
      <h2>Watchers</h2>
      <div id="watches"></div>
      <h2 style="margin-top: 22px;">Scheduled Tasks</h2>
      <div id="schedules"></div>
    </div>
  </div>

  <div class="footer">SONIC.APEX LIVE — <span id="uptime">--</span> — powered by RealtimeEngine</div>

<script>
const COLORS = {
  cyan:  '#00d9ff', green: '#30d158', red:   '#ff453a',
  amber: '#ffd60a', dim:   '#8a96a8',
};

async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return await r.json();
}

function fmtTime(s) {
  if (!s || s < 1) return '0s';
  if (s < 60) return s.toFixed(1) + 's';
  const m = Math.floor(s / 60);
  return m + 'm ' + Math.floor(s % 60) + 's';
}

function statusClass(s) {
  if (s === 'queued')    return 'queued';
  if (s === 'running')   return 'running';
  if (s === 'done')      return 'done';
  if (s === 'failed')    return 'failed';
  return 'cancelled';
}

function renderJob(j) {
  const meta = (j.metadata && j.metadata.category) || '';
  return `
    <div class="job" id="job-${j.id}">
      <div class="row">
        <div class="name">${escape(j.name)}${meta ? ' · ' + meta : ''}</div>
        <span class="badge ${statusClass(j.status)}">${j.status}</span>
      </div>
      <div class="progress"><div class="fill" style="width:${Math.round(j.progress*100)}%"></div></div>
      <div class="meta">${fmtTime(j.elapsed)} · ${j.id}</div>
      ${j.log && j.log.length ? `<div class="log">${j.log.slice(-6).map(escape).join('<br>')}</div>` : ''}
      ${j.error ? `<div class="log" style="color:#ff453a">${escape(j.error.slice(0, 200))}</div>` : ''}
    </div>
  `;
}

function escape(s) {
  return String(s || '').replace(/[&<>"']/g, c => (
    {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]
  ));
}

async function refresh() {
  try {
    const snap = await fetchJSON('/api/snapshot');
    document.getElementById('stat-running').textContent = snap.active;
    document.getElementById('stat-queued').textContent  = snap.queued;
    document.getElementById('stat-done').textContent    = snap.done;
    document.getElementById('stat-failed').textContent  = snap.failed;

    const jobsHtml = snap.jobs.length
      ? snap.jobs.map(renderJob).join('')
      : '<div class="empty">No jobs yet — trigger a workflow above ↓</div>';
    document.getElementById('jobs').innerHTML = jobsHtml;

    const [watches, schedules] = await Promise.all([
      fetchJSON('/api/watches'),
      fetchJSON('/api/schedules'),
    ]);

    document.getElementById('watches').innerHTML = watches.length
      ? watches.map(w =>
          `<div class="job"><div class="row">
             <div class="name">${escape(w.path)}</div>
             <button class="btn danger" onclick="stopWatch('${w.token}')">STOP</button>
           </div></div>`).join('')
      : '<div class="empty">No file watchers</div>';

    document.getElementById('schedules').innerHTML = schedules.length
      ? schedules.map(s =>
          `<div class="job"><div class="row">
             <div class="name">${escape(s.name)} <span class="meta">${
               s.mode === 'interval' ? 'every ' + s.every_seconds + 's' : 'at ' + s.at
             }</span></div>
             <button class="btn danger" onclick="stopSchedule('${s.token}')">STOP</button>
           </div></div>`).join('')
      : '<div class="empty">No scheduled tasks</div>';

    document.getElementById('uptime').textContent = new Date().toLocaleTimeString();
  } catch (e) {
    document.getElementById('live-dot').style.background = '#ff453a';
    document.getElementById('live-dot').style.boxShadow = '0 0 6px #ff453a';
  }
}

async function loadTemplates() {
  const tpls = await fetchJSON('/api/templates');
  const el = document.getElementById('templates');
  el.innerHTML = tpls.map(t =>
    `<button class="btn" onclick="runTemplate('${t.name}')" title="${escape(t.description)}">${escape(t.name)}</button>`
  ).join('');
}

async function runTemplate(name) {
  const r = await fetchJSON(`/api/templates/${encodeURIComponent(name)}`, {method: 'POST'});
  if (r.job_id) {
    setTimeout(refresh, 300);
  } else {
    alert('Failed: ' + (r.error || 'unknown'));
  }
}

async function stopWatch(token) {
  await fetchJSON(`/api/watches/${token}`, {method: 'DELETE'});
  refresh();
}

async function stopSchedule(token) {
  await fetchJSON(`/api/schedules/${token}`, {method: 'DELETE'});
  refresh();
}

// SSE for live updates
function connectSSE() {
  const es = new EventSource('/api/stream');
  es.onmessage = () => refresh();
  es.onerror = () => { es.close(); setTimeout(connectSSE, 2000); };
}

refresh();
loadTemplates();
setInterval(refresh, 2000);
connectSSE();
</script>
</body>
</html>"""


# ═════════════════════════════════════════════════════════════════════════════
# Flask app factory
# ═════════════════════════════════════════════════════════════════════════════

def create_app(host: str = "127.0.0.1", port: int = 7654):
    """Build the Flask app. Imports Flask lazily so the rest of SONIC
    works even if Flask isn't installed.
    """
    try:
        from flask import Flask, jsonify, request, Response
    except ImportError as e:
        raise RuntimeError(
            "Flask is required for the dashboard. Run: pip install flask"
        ) from e

    app = Flask("SONIC-Dashboard")

    # Lazily import the rest of the platform so missing deps degrade cleanly
    from automation.realtime_engine import realtime
    from automation import workflow_templates
    from automation import proactive_monitor

    @app.get("/")
    def index():
        return Response(INDEX_HTML, mimetype="text/html")

    @app.get("/api/snapshot")
    def snapshot():
        return jsonify(realtime().snapshot())

    @app.get("/api/templates")
    def list_templates():
        return jsonify(workflow_templates.list_templates())

    @app.post("/api/templates/<name>")
    def run_template(name):
        # Pull params from JSON body (optional)
        try:
            params = request.get_json(silent=True) or {}
        except Exception:
            params = {}
        try:
            job_id = workflow_templates.run_template(name, **params)
            return jsonify({"job_id": job_id})
        except KeyError as e:
            return jsonify({"error": str(e)}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.get("/api/watches")
    def list_watches():
        return jsonify(proactive_monitor.list_watches())

    @app.post("/api/watches")
    def add_watch():
        body = request.get_json() or {}
        path = body.get("path") or ""
        callback_name = body.get("callback", "log_event")

        def _log_event(event_type, path):
            logger.info(f"watch event: {event_type} on {path}")

        callbacks = {"log_event": _log_event}
        cb = callbacks.get(callback_name, _log_event)
        try:
            token = proactive_monitor.watch(path, cb)
            return jsonify({"token": token})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.delete("/api/watches/<token>")
    def remove_watch(token):
        ok = proactive_monitor.cancel_watch(token)
        return jsonify({"ok": ok})

    @app.get("/api/schedules")
    def list_schedules():
        return jsonify(proactive_monitor.list_schedules())

    @app.post("/api/schedules")
    def add_schedule():
        body = request.get_json() or {}
        every_seconds = body.get("every_seconds")
        at = body.get("at")
        name = body.get("name", "scheduled")
        # For demo: a simple log callback. Real SONIC would accept any callable.
        def _tick():
            logger.info(f"scheduled tick: {name}")
        try:
            kwargs = {"name": name}
            if every_seconds:
                kwargs["every_seconds"] = float(every_seconds)
            if at:
                kwargs["at"] = at
            token = proactive_monitor.schedule(_tick, **kwargs)
            return jsonify({"token": token})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.delete("/api/schedules/<token>")
    def remove_schedule(token):
        ok = proactive_monitor.cancel_schedule(token)
        return jsonify({"ok": ok})

    @app.get("/api/stream")
    def stream():
        """Server-Sent Events — pushes a heartbeat every time any job changes."""
        def _gen():
            # Inline subscriber queue — pushes a "refresh" signal on change
            q: queue.Queue = queue.Queue(maxsize=10)
            def _on_change(_job):
                try:
                    q.put_nowait("refresh")
                except queue.Full:
                    pass
            unsub = realtime().subscribe(_on_change)
            try:
                yield "data: hello\n\n"  # initial
                while True:
                    try:
                        msg = q.get(timeout=15)
                        yield f"data: {msg}\n\n"
                    except queue.Empty:
                        yield ": keepalive\n\n"
            except GeneratorExit:
                unsub()
                raise

        return Response(_gen(), mimetype="text/event-stream",
                       headers={"Cache-Control": "no-cache",
                               "X-Accel-Buffering": "no"})

    return app


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    # Force UTF-8 stdout so the welcome banner doesn't crash on Windows cp1252
    try:
        import sys
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    p = argparse.ArgumentParser(description="SONIC Live Automation Dashboard")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=7654)
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()

    app = create_app(host=args.host, port=args.port)
    print(f"\n  SONIC Apex Live Dashboard")
    print(f"  -> http://{args.host}:{args.port}/\n")
    app.run(host=args.host, port=args.port, debug=args.debug,
            threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()


__all__ = ["create_app", "main"]
