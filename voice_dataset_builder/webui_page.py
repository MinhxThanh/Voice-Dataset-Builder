"""The single-page HTML/CSS/JS for the web UI (kept separate from server logic)."""

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Voice Dataset Builder</title>
<style>
  :root { --bg:#131313; --panel:rgba(38,38,37,.72); --ink:#ffffff; --muted:#A4A4A4;
          --accent:#EFD395; --accent2:#cdae6a; --gold-ink:#131313;
          --line:rgba(119,118,116,.28); --surface:rgba(75,74,72,.18);
          --ok:#EFD395; --err:#ff6b6b; --warn:#EFD395; --radius:14px; }
  * { box-sizing: border-box; }
  html { scroll-behavior:smooth; }
  body { margin:0; min-height:100vh; color:var(--ink);
         font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; background:#131313;
         background-image:
           radial-gradient(60vw 60vw at 12% -10%, rgba(239,211,149,.10), transparent 60%),
           radial-gradient(55vw 55vw at 110% 10%, rgba(239,211,149,.07), transparent 55%),
           radial-gradient(50vw 50vw at 50% 120%, rgba(119,118,116,.10), transparent 60%);
         background-attachment:fixed; animation:floatGlow 18s ease-in-out infinite; }
  @keyframes floatGlow { 0%,100%{background-position:0% 0%,100% 0%,50% 100%;}
    50%{background-position:6% 4%,94% 6%,50% 96%;} }
  header { padding:20px 28px; border-bottom:1px solid var(--line); backdrop-filter:blur(8px);
           display:flex; align-items:center; justify-content:space-between; gap:16px; }
  .head-copy { min-width:0; }
  .head-actions { display:flex; align-items:center; gap:8px; flex:0 0 auto; }
  header h1 { margin:0; font-size:20px; letter-spacing:.2px;
              background:linear-gradient(90deg,var(--accent),var(--accent2));
              -webkit-background-clip:text; background-clip:text; color:transparent; }
  header p { margin:5px 0 0; color:var(--muted); font-size:13px; }
  main { display:grid; grid-template-columns:420px 1fr; gap:0; min-height:calc(100vh - 70px); }
  .form, .out { animation:rise .5s cubic-bezier(.2,.7,.2,1) both; }
  .out { animation-delay:.06s; }
  @keyframes rise { from{opacity:0; transform:translateY(10px);} to{opacity:1; transform:none;} }
  .form { padding:18px 24px 28px; border-right:1px solid var(--line); overflow:auto;
          background:linear-gradient(180deg,rgba(255,255,255,.02),transparent); }
  .out { padding:18px 24px; display:flex; flex-direction:column; min-width:0; }
  label { display:block; font-size:11px; color:var(--muted); margin:13px 0 5px;
          text-transform:uppercase; letter-spacing:.06em; }
  input, select, textarea { width:100%; background:rgba(19,19,19,.6); color:var(--ink);
         border:1px solid var(--line); border-radius:10px; padding:10px 12px; font:inherit;
         transition:border-color .18s, box-shadow .18s, background .18s; }
  input:hover, select:hover, textarea:hover { border-color:rgba(255,255,255,.18); }
  input:focus, select:focus, textarea:focus { outline:none; border-color:var(--accent);
         box-shadow:0 0 0 3px rgba(239,211,149,.22); background:rgba(19,19,19,.9); }
  textarea { resize:vertical; min-height:84px; line-height:1.45; }
  .row { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
  .check { display:flex; align-items:center; gap:8px; margin-top:12px; font-size:13px; }
  .check input { width:auto; accent-color:var(--accent); }
  .check label { margin:0; text-transform:none; letter-spacing:0; font-size:13.5px; color:var(--ink); }
  .switch { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:12px 0;
            padding:10px 12px; border:1px solid var(--line); border-radius:10px; background:rgba(255,255,255,.035); }
  .switch span { font-size:13.5px; }
  .switch input { width:42px; height:22px; appearance:none; border-radius:999px; padding:0;
                  background:rgba(255,255,255,.15); position:relative; flex:0 0 auto; cursor:pointer; }
  .switch input::after { content:""; position:absolute; width:18px; height:18px; top:1px; left:1px;
                         border-radius:999px; background:#fff; transition:transform .16s; }
  .switch input:checked { background:var(--accent); }
  .switch input:checked::after { transform:translateX(20px); }
  .dropzone { display:grid; place-items:center; min-height:148px; margin-top:8px; padding:18px;
              border:1px dashed rgba(255,255,255,.28); border-radius:10px; background:rgba(19,19,19,.5);
              color:var(--muted); text-align:center; cursor:pointer; transition:border-color .16s, background .16s; }
  .dropzone strong { display:block; color:var(--ink); margin-bottom:4px; font-size:14px; }
  .dropzone.drag { border-color:var(--accent); background:rgba(239,211,149,.1); }
  .upload-list { margin-top:10px; display:grid; gap:6px; font-size:12.5px; color:var(--muted); }
  .upload-list div { padding:8px 10px; border:1px solid var(--line); border-radius:8px; background:rgba(255,255,255,.03); word-break:break-word; }
  .manual-paths { display:none; }
  .manual-paths.show { display:block; }
  fieldset { border:1px solid var(--line); border-radius:var(--radius); margin:16px 0 0; padding:6px 14px 14px;
             background:linear-gradient(180deg,rgba(255,255,255,.015),transparent); }
  legend { padding:0 8px; font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--accent); }
  button { color:var(--gold-ink); border:0; border-radius:12px; padding:13px; font-weight:700; font-size:15px;
           cursor:pointer; background:linear-gradient(90deg,var(--accent),var(--accent2));
           background-size:200% 100%; box-shadow:0 8px 24px rgba(239,211,149,.22);
           transition:transform .12s, box-shadow .2s, background-position .4s, opacity .2s; }
  button:hover:not(:disabled) { background-position:100% 0; box-shadow:0 10px 30px rgba(239,211,149,.32); transform:translateY(-1px); }
  button:active:not(:disabled) { transform:translateY(0) scale(.99); }
  button:disabled { opacity:.55; cursor:not-allowed; box-shadow:none; }
  .icon-btn { width:42px; height:42px; padding:0; display:grid; place-items:center; flex:0 0 auto;
              color:var(--accent); border:1px solid var(--line); background:var(--surface); box-shadow:none; }
  .icon-btn:hover:not(:disabled){ color:var(--ink); background:rgba(239,211,149,.12); border-color:var(--accent); }
  .icon-btn svg { width:19px; height:19px; stroke:currentColor; fill:none; stroke-width:2; }
  .btn-row { display:grid; grid-template-columns:2fr 1fr; gap:10px; margin-top:20px; }
  .btn-ghost { background:rgba(255,255,255,.06); color:var(--ink); box-shadow:none; }
  .btn-ghost:hover:not(:disabled){ background:rgba(255,255,255,.12); }
  #stop { grid-column:1 / -1; margin-top:2px; border:1px solid rgba(255,107,107,.5);
          background:rgba(255,107,107,.12); color:#ffb1b1; font-weight:600;
          animation:stopIn .28s cubic-bezier(.2,.7,.2,1) both, stopPulse 1.8s ease-in-out .28s infinite; }
  #stop:hover:not(:disabled){ background:rgba(255,107,107,.22); border-color:rgba(255,107,107,.8);
          box-shadow:0 0 0 3px rgba(255,107,107,.18); }
  #stop.hidden { display:none; }
  @keyframes stopIn { from{opacity:0; transform:translateY(-6px) scale(.96);} to{opacity:1; transform:none;} }
  @keyframes stopPulse { 0%,100%{ box-shadow:0 0 0 0 rgba(255,107,107,.32);} 50%{ box-shadow:0 0 0 6px rgba(255,107,107,0);} }
  /* tabs */
  .tabs { display:flex; gap:6px; margin-bottom:10px; }
  .tab { flex:1; text-align:center; padding:9px; border-radius:10px; cursor:pointer; font-size:13.5px;
         color:var(--muted); border:1px solid var(--line); background:rgba(255,255,255,.03); transition:.18s; }
  .tab:hover { color:var(--ink); }
  .tab.active { color:var(--gold-ink); border-color:transparent; font-weight:700;
                background:linear-gradient(90deg,var(--accent),var(--accent2)); }
  .tabpane { display:none; } .tabpane.active { display:block; }
  .seg { display:grid; grid-template-columns:1fr 1fr; gap:6px; }
  .seg label { margin:0; text-transform:none; letter-spacing:0; font-size:13.5px; color:var(--ink);
               display:flex; align-items:center; justify-content:center; min-height:40px; padding:8px;
               border:1px solid var(--line); border-radius:10px; background:rgba(255,255,255,.03); cursor:pointer; }
  .seg input { position:absolute; opacity:0; pointer-events:none; }
  .seg label:has(input:checked) { border-color:transparent; color:var(--gold-ink); font-weight:700;
                                  background:linear-gradient(90deg,var(--accent),var(--accent2)); }
  .seg label:has(input:disabled) { opacity:.45; cursor:not-allowed; }
  /* presets */
  .presets { display:flex; flex-wrap:wrap; gap:7px; margin-top:6px; }
  .preset { padding:6px 11px; font-size:12.5px; border-radius:999px; cursor:pointer; color:var(--ink);
            border:1px solid var(--line); background:rgba(255,255,255,.04); transition:.16s; }
  .preset:hover { border-color:var(--accent); transform:translateY(-1px); }
  /* progress bar with status text overlay */
  .progress { position:relative; height:28px; border-radius:999px; background:rgba(255,255,255,.07);
              overflow:hidden; margin:0 0 8px; border:1px solid var(--line); }
  .progress > i { display:block; height:100%; width:0%;
                  background:linear-gradient(90deg,var(--accent),var(--accent2)); transition:width .4s ease; }
  .progress .status { position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
                       margin:0; font-size:13px; font-weight:600; color:var(--ink); text-shadow:0 1px 2px rgba(0,0,0,.55);
                       pointer-events:none; transition:color .2s; }
  .progress .status.ok { color:#fff; } .progress .status.err { color:#ffd1d1; }
  /* pet walking across the progress lane (animated GIFs, 192x208 each) */
  .pet-track { position:relative; height:60px; margin:6px 0 4px; overflow:hidden; pointer-events:none;
               --pet-scale:0.28; }
  .pet-track .pet { position:absolute; bottom:-2px; left:0;
               width:calc(192 * var(--pet-scale) * 1px);
               height:calc(208 * var(--pet-scale) * 1px);
               image-rendering:auto;
               transform:translateX(var(--pet-x, 0px));
               transition:transform var(--pet-move, .4s) linear;
               will-change:transform; }
  .phases { display:flex; gap:6px; margin:0 0 12px; font-size:11px; color:var(--muted); flex-wrap:wrap; }
  .phases span { padding:3px 9px; border-radius:999px; background:rgba(255,255,255,.04); border:1px solid var(--line); transition:.2s; }
  .phases span.active { color:var(--gold-ink); font-weight:700; border-color:transparent; background:linear-gradient(90deg,var(--accent),var(--accent2)); }
  .phases span.done { color:var(--ok); border-color:rgba(239,211,149,.4); }
  pre#log { flex:1; min-height:180px; background:rgba(7,9,13,.72); border:1px solid var(--line);
            border-radius:var(--radius); padding:16px; overflow:auto; white-space:pre-wrap;
            font:13px/1.55 ui-monospace,Menlo,monospace; margin:0; backdrop-filter:blur(6px); }
  pre#log .ln { display:block; animation:lineIn .28s ease both; }
  @keyframes lineIn { from{opacity:0; transform:translateX(-6px);} to{opacity:1; transform:none;} }
  details { margin-top:12px; } summary { cursor:pointer; color:var(--muted); font-size:12px; padding:4px 0; }
  summary:hover { color:var(--ink); }
  .hint { color:var(--muted); font-size:12px; margin-top:8px; }
  .summary { border:1px solid var(--line); border-radius:var(--radius); padding:0 14px; margin-bottom:12px;
             font-size:13px; backdrop-filter:blur(6px); max-height:0; opacity:0; overflow:hidden;
             background:linear-gradient(135deg,rgba(239,211,149,.08),rgba(119,118,116,.05));
             transition:max-height .4s ease, opacity .3s ease, padding .3s ease; }
  .summary.show { max-height:none; opacity:1; padding:14px; }
  .summary b { color:var(--accent); } .summary code { background:rgba(255,255,255,.06); padding:2px 6px; border-radius:6px; }
  .clip { display:flex; align-items:center; gap:10px; padding:8px 0; border-top:1px solid var(--line); }
  .clip:first-of-type { border-top:0; }
  .clip audio { height:32px; }
  .clip .txt { font-size:12.5px; color:var(--ink); flex:1; min-width:0; }
  .clip .dur { font-size:11px; color:var(--muted); }
  .ds-head { margin-top:12px; font-size:11px; color:var(--muted); text-transform:uppercase;
             letter-spacing:.06em; display:flex; align-items:center; gap:8px; }
  .ds-count { color:var(--accent); background:rgba(239,211,149,.12); border:1px solid var(--line);
              padding:1px 8px; border-radius:999px; font-size:10.5px; letter-spacing:.02em; }
  .ds-list { margin-top:8px; max-height:420px; overflow:auto; padding-right:4px;
             border:1px solid var(--line); border-radius:10px; }
  .ds-list .clip { padding:8px 10px; }
  .clip .idx { flex:0 0 auto; width:26px; text-align:right; font-size:11px; color:var(--muted);
               font-variant-numeric:tabular-nums; }
  .clip .fn { font-size:10.5px; color:var(--muted); margin-bottom:2px; }
  .clip .txt { white-space:normal; word-break:break-word; }
  .clip.is-transcribing { opacity:.92; }
  .clip .pending { color:var(--muted); font-style:italic;
                   animation:pendingPulse 1.2s ease-in-out infinite; }
  @keyframes pendingPulse { 0%,100%{opacity:.45;} 50%{opacity:.95;} }
  .clip .editable { cursor:text; border-radius:5px; padding:1px 3px; margin:-1px -3px;
                    transition:background .15s, box-shadow .15s; outline:none; }
  .clip .editable:hover { background:rgba(255,255,255,.05); }
  .clip .editable.editing { background:rgba(239,211,149,.1);
                            box-shadow:0 0 0 1px rgba(239,211,149,.5) inset; cursor:text; }
  .clip .editable.saving { box-shadow:0 0 0 1px rgba(120,200,140,.6) inset; }
  .clip .edit-hint { font-size:10px; color:var(--muted); margin-left:6px; opacity:0; transition:opacity .15s; }
  .clip:hover .edit-hint { opacity:.65; }
  .modal { position:fixed; inset:0; display:none; place-items:center; padding:24px; z-index:20;
           background:rgba(5,7,11,.72); backdrop-filter:blur(8px); }
  .modal.show { display:grid; animation:fadeIn .16s ease both; }
  @keyframes fadeIn { from{opacity:0;} to{opacity:1;} }
  .settings { width:min(760px,100%); max-height:min(720px,92vh); overflow:auto; border:1px solid var(--line);
              border-radius:var(--radius); background:rgba(15,18,25,.96); box-shadow:0 24px 70px rgba(0,0,0,.38); }
  .settings-head { display:flex; align-items:center; justify-content:space-between; gap:12px;
                   padding:16px 18px; border-bottom:1px solid var(--line); }
  .settings-head h2 { margin:0; font-size:17px; letter-spacing:0; }
  .settings-body { padding:16px 18px 18px; }
  .model-list { display:grid; gap:10px; margin-top:14px; }
  .model-row { display:grid; grid-template-columns:1fr auto; gap:12px; align-items:center;
               padding:12px; border:1px solid var(--line); border-radius:10px; background:rgba(255,255,255,.035); }
  .model-name { font-weight:650; }
  .model-meta { color:var(--muted); font-size:12px; word-break:break-word; }
  .model-state { display:inline-flex; align-items:center; gap:7px; margin-top:5px; font-size:12px; color:var(--muted); }
  .model-actions { display:flex; gap:8px; align-items:center; }
  .dot { width:7px; height:7px; border-radius:999px; background:var(--muted); }
  .dot.ok { background:var(--ok); } .dot.warn { background:var(--warn); }
  .model-hint { margin:7px 0 0; font-size:12.5px; color:var(--muted); }
  .download-log { margin-top:14px; min-height:84px; max-height:180px; overflow:auto; padding:12px;
                  border:1px solid var(--line); border-radius:10px; background:rgba(7,9,13,.72);
                  font:12.5px/1.5 ui-monospace,Menlo,monospace; color:var(--muted); white-space:pre-wrap;
                  display:none; }
  .download-log.show { display:block; }
  .download-bar { height:7px; margin-top:10px; border-radius:999px; overflow:hidden; background:rgba(255,255,255,.07); display:none; }
  .download-bar.on { display:block; }
  .download-bar i { display:block; width:40%; height:100%; border-radius:999px;
                    background:linear-gradient(90deg,var(--accent),var(--accent2)); animation:sweep 1.1s ease-in-out infinite; }
  @keyframes sweep { 0%{ transform:translateX(-110%);} 100%{ transform:translateX(260%);} }
  @media (max-width:640px){ header{padding:16px 18px;} .row,.model-row{grid-template-columns:1fr;} .model-actions{display:grid;} .model-row button{width:100%;} }
  @media (max-width:860px){ main{grid-template-columns:1fr;} .form{border-right:0;border-bottom:1px solid var(--line);} }
  @media (prefers-reduced-motion:reduce){ *{animation:none!important; transition:none!important;} }
  .hidden { display:none !important; }
  header h1 a { color:inherit; text-decoration:none; }
  /* ---- home view ---- */
  .home { min-height:calc(100vh - 70px); padding:48px 28px 64px; display:flex;
          flex-direction:column; align-items:center; }
  .home-hero { text-align:center; max-width:680px; margin:32px auto 8px; animation:rise .5s cubic-bezier(.2,.7,.2,1) both; }
  .home-title { margin:0; font-size:clamp(34px,6vw,56px); line-height:1.05; letter-spacing:-.5px;
                background:linear-gradient(90deg,var(--accent),var(--accent2));
                -webkit-background-clip:text; background-clip:text; color:transparent; }
  .home-tag { margin:14px 0 0; color:var(--muted); font-size:16px; }
  .home-actions { display:flex; gap:12px; justify-content:center; flex-wrap:wrap; margin-top:28px; }
  .home-actions button { padding:12px 22px; font-size:15px; }
  .project-list { width:min(760px,100%); margin:36px auto 0; display:grid; gap:10px; }
  .project-list .empty { color:var(--muted); text-align:center; font-size:13.5px; padding:18px; }
  .project-list h3 { font-size:11px; color:var(--ink); text-transform:uppercase; letter-spacing:.06em; margin:0 0 4px; }
  .pcard { display:flex; align-items:center; gap:14px; min-height:72px; padding:18px 20px; border:1px solid var(--line);
           border-radius:12px; background:var(--panel); cursor:pointer; text-align:left;
           transition:border-color .16s, transform .16s, background .16s; }
  .pcard:hover { border-color:rgba(255,255,255,.22); transform:translateY(-1px); background:rgba(255,255,255,.04); }
  .pcard .pmain { flex:1; min-width:0; margin:10px; }
  .pcard .pname { font-weight:650; font-size:15px; margin-bottom:22px; color:white; }
  .pcard .pmeta { color:var(--muted); font-size:12.5px; margin-top:3px; }
  .pcard .pbadge { flex:0 0 auto; font-size:11px; padding:3px 10px; border-radius:999px;
                   border:1px solid var(--line); color:var(--muted); }
  .pcard .pbadge.resume { color:var(--warn); border-color:rgba(255,204,102,.4); background:rgba(255,204,102,.1); }
  .pcard .pbadge.partial { color:var(--accent); border-color:rgba(239,211,149,.4); background:rgba(239,211,149,.1); }
  /* ---- create-project dialog ---- */
  .dialog { width:min(440px,100%); border:1px solid var(--line); border-radius:var(--radius);
            background:rgba(15,18,25,.98); box-shadow:0 24px 70px rgba(0,0,0,.45);
            animation:rise .28s cubic-bezier(.2,.7,.2,1) both; }
  .dialog .settings-body { padding:18px; }
  .dialog input { font-size:15px; }
  .dialog-error { color:var(--err); font-size:12.5px; margin:8px 0 0; min-height:0; display:none; }
  .dialog-error.show { display:block; }
  .dialog-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:18px; }
</style>
</head>
<body>
<header>
  <div class="head-copy">
    <h1><a id="home_link" href="/">Voice Dataset Builder</a></h1>
    <p id="header_sub">YouTube or local audio &rarr; cleaned, transcribed clips + JSONL / CSV / Fish / GPT-SoVITS for TTS training.</p>
  </div>
  <div class="head-actions">
    <button id="open_project_dir" class="icon-btn hidden" title="Open project folder in Finder/Explorer" aria-label="Open project folder">
      <svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/><path d="m9 14 3-3 3 3"/><path d="M12 11v6"/></svg>
    </button>
    <button id="settings_open" class="icon-btn" title="Settings" aria-label="Settings">
      <svg viewBox="0 0 24 24"><path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 8.98 19.35a1.7 1.7 0 0 0-1.88.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.65 8.98a1.7 1.7 0 0 0-.34-1.88l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.56V3a2 2 0 1 1 4 0v.09A1.7 1.7 0 0 0 15.02 4.65a1.7 1.7 0 0 0 1.88-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9c.65.26 1.07.88 1.07 1.58V12c0 .7-.42 1.32-1.07 1.58Z"/></svg>
    </button>
  </div>
</header>
<div id="settings_modal" class="modal" aria-hidden="true">
  <section class="settings" role="dialog" aria-modal="true" aria-labelledby="settings_title">
    <div class="settings-head">
      <h2 id="settings_title">Automatic Speech Recognition</h2>
      <button id="settings_close" class="icon-btn" title="Close" aria-label="Close">
        <svg viewBox="0 0 24 24"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
      </button>
    </div>
    <div class="settings-body">
      <label>Hugging Face token</label>
      <input id="hf_token" type="password" placeholder="Required for gated CohereLabs/cohere-transcribe-03-2026" autocomplete="off" />
      <p class="hint">The token is only sent with the download request and is not saved by this UI.</p>
      <div class="download-bar" id="download_bar"><i></i></div>
      <div class="model-list" id="model_list"></div>
      <div class="download-log" id="download_log">Download logs will appear here.</div>
    </div>
  </section>
</div>
<div id="newproj_modal" class="modal" aria-hidden="true">
  <section class="dialog" role="dialog" aria-modal="true" aria-labelledby="newproj_title">
    <div class="settings-head">
      <h2 id="newproj_title">Create new project</h2>
      <button id="newproj_close" class="icon-btn" title="Close" aria-label="Close">
        <svg viewBox="0 0 24 24"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
      </button>
    </div>
    <div class="settings-body">
      <label for="newproj_name">Project name</label>
      <input id="newproj_name" type="text" placeholder="e.g. My Voice" autocomplete="off" />
      <p id="newproj_hint" class="hint">A new folder is created under <code>projects/</code>. Letters, numbers, dashes and underscores.</p>
      <p id="newproj_error" class="dialog-error"></p>
      <div class="dialog-actions">
        <button id="newproj_cancel" class="btn-ghost">Cancel</button>
        <button id="newproj_submit">Create project</button>
      </div>
    </div>
  </section>
</div>
<section id="home" class="home">
  <div class="home-hero">
    <h2 class="home-title">Voice Dataset Builder</h2>
    <p class="home-tag">Turn YouTube or local audio into clean, transcribed TTS datasets.</p>
    <div class="home-actions">
      <button id="home_open" class="btn-ghost">Open Project</button>
      <button id="home_create">Create new Project</button>
    </div>
  </div>
  <div id="project_list" class="project-list"></div>
</section>
<main id="builder" class="hidden">
  <section class="form">
    <label>Presets</label>
    <div class="presets" id="presets"></div>

    <div class="tabs" style="margin-top:14px;">
      <div class="tab active" data-tab="yt">YouTube URLs</div>
      <div class="tab" data-tab="local">Local files</div>
    </div>
    <div class="tabpane active" data-pane="yt">
      <label>YouTube URLs (one per line)</label>
      <textarea id="urls" placeholder="https://www.youtube.com/watch?v=...&#10;https://youtu.be/..."></textarea>
    </div>
    <div class="tabpane" data-pane="local">
      <label>Local audio/video files</label>
      <div id="dropzone" class="dropzone" tabindex="0" role="button" aria-label="Drop or choose local files">
        <div><strong>Drop audio/video files here</strong>or click to choose files</div>
      </div>
      <input id="file_picker" type="file" multiple accept="audio/*,video/*" hidden />
      <div id="upload_list" class="upload-list"></div>
      <label class="switch"><span>Enter local paths manually</span><input id="manual_paths" type="checkbox" /></label>
      <div id="manual_paths_box" class="manual-paths">
        <label>Local audio/video paths (one per line)</label>
        <textarea id="local_sources" placeholder="/path/to/recording.wav&#10;/path/to/lecture.mp4"></textarea>
        <p class="hint">Absolute paths on this machine. Folders not expanded; list files.</p>
      </div>
    </div>

    <div class="row">
      <div><label>Speaker ID</label><input id="speaker_id" value="speaker_01" /></div>
      <div><label>Language (blank = auto)</label><input id="language" placeholder="vi, en..." /></div>
    </div>
    <fieldset>
      <legend>Transcription</legend>
      <label>Transcription source</label>
      <div class="seg" id="transcription_source">
        <label><input type="radio" name="transcription_source" id="source_youtube" value="youtube" />YouTube transcription</label>
        <label><input type="radio" name="transcription_source" id="source_ai" value="ai" checked />AI transcription</label>
      </div>
      <p id="source_hint" class="hint">YouTube transcription uses subtitles/CC when available.</p>
      <div id="ai_settings">
        <div class="row" style="margin-top:10px;">
          <div><label>Transcription model</label>
            <select id="whisper_model">
              <option>tiny</option><option selected>base</option><option>small</option>
              <option>medium</option><option>large-v3</option><option>large-v3-turbo</option>
            </select>
            <p id="model_hint" class="model-hint">Whisper models use the selected backend below.</p>
          </div>
          <div><label>Backend</label>
            <select id="whisper_backend"><option>auto</option><option>faster-whisper</option><option>openai-whisper</option></select></div>
        </div>
        <label>Initial prompt (biases decoding; great for Vietnamese diacritics)</label>
        <textarea id="initial_prompt" style="min-height:54px" placeholder="e.g. Xin chào, đây là tiếng Việt có dấu."></textarea>
        <div class="row">
          <div><label>Min confidence (blank = off)</label><input id="min_confidence" type="number" step="0.05" placeholder="-1.0 .. 0.0" /></div>
          <div><label>Device</label><select id="device"><option>auto</option><option>cpu</option><option>cuda</option></select></div>
        </div>
      </div>
    </fieldset>

    <fieldset>
      <legend>Cleaning</legend>
      <div class="check"><input id="remove_silence" type="checkbox" checked /><label>Remove leading/trailing silence (VAD)</label></div>
      <div class="row" id="silence_row" style="margin-top:6px;">
        <div><label>Silence threshold (dB)</label>
          <input id="silence_threshold_db" type="number" step="1" value="-45" min="-60" max="-20" />
          <p class="hint">Quieter than this counts as silence. Try -50 for clean studio, -35 for noisy phone.</p>
        </div>
        <div><label>High-pass (Hz)</label>
          <select id="highpass_hz">
            <option value="0">Off</option>
            <option value="60">60 Hz</option>
            <option value="80" selected>80 Hz (recommended)</option>
            <option value="100">100 Hz</option>
          </select>
          <p class="hint">Removes DC + low rumble so loudnorm stays accurate.</p>
        </div>
      </div>
      <div class="check"><input id="loudnorm" type="checkbox" checked /><label>Loudness normalize</label></div>
      <div class="row" style="margin-top:8px;">
        <div><label>Target LUFS</label>
          <input id="loudnorm_lufs" type="number" step="1" value="-23" min="-36" max="-9" />
          <div class="presets" style="margin-top:6px;">
            <span class="preset" data-lufs="-23">-23 broadcast</span>
            <span class="preset" data-lufs="-16">-16 TTS / streaming</span>
            <span class="preset" data-lufs="-14">-14 loud</span>
          </div>
        </div>
        <div><label>Sample rate</label>
          <select id="sample_rate"><option selected>24000</option><option>22050</option><option>16000</option><option>48000</option></select></div>
      </div>
      <div class="check"><input id="loudnorm_two_pass" type="checkbox" /><label>Accurate two-pass loudnorm (slower)</label></div>
      <div class="check"><input id="denoise" type="checkbox" /><label>Denoise / isolate vocals (Demucs, optional)</label></div>
      <div class="row" id="denoise_row" style="margin-top:6px;">
        <div><label>Demucs model</label>
          <select id="demucs_model">
            <option value="htdemucs" selected>htdemucs (fast)</option>
            <option value="htdemucs_ft">htdemucs_ft (slower, cleaner)</option>
          </select>
        </div>
        <div><p class="hint" id="sample_rate_hint" style="margin-top:24px;"></p></div>
      </div>
    </fieldset>

    <fieldset>
      <legend>Output</legend>
      <label>Format</label>
      <select id="output_formats">
        <option value="universal" selected>Universal (JSONL + CSV + Fish + GPT-SoVITS)</option>
        <option value="jsonl">JSONL only</option>
        <option value="ljspeech">LJSpeech CSV (id|text|normalized — XTTS-compatible)</option>
        <option value="fish">Fish Speech (.lab files)</option>
        <option value="gpt-sovits">GPT-SoVITS (.list: wav|spk|lang|text)</option>
      </select>
      <p class="hint">LJSpeech and Fish Speech now fully compatible with official recipes (no manual path editing needed). Wavs are linked into <code>wavs/</code> for XTTS and into <code>fish/&lt;speaker&gt;/</code> for Fish Speech.</p>
      <div class="row" style="margin-top:8px;">
        <div><label>Min clip (s)</label><input id="min_clip" type="number" step="0.5" value="3" /></div>
        <div><label>Max clip (s)</label><input id="max_clip" type="number" step="0.5" value="12" /></div>
      </div>
      <div class="row">
        <div><label>Val ratio</label><input id="val_ratio" type="number" step="0.05" value="0.1" /></div>
        <div><label>Merge gap (s)</label><input id="merge_gap" type="number" step="0.1" value="0.4" /></div>
      </div>
      <div class="check"><input id="make_references" type="checkbox" checked /><label>Auto-create references/ folder</label></div>
      <div class="check"><input id="keep_source_audio" type="checkbox" /><label>Keep full source audio</label></div>
    </fieldset>

    <details>
      <summary>Advanced</summary>
      <div class="row">
        <div><label>Channels</label><select id="channels"><option selected>1</option><option>2</option></select></div>
        <div><label>Bit depth</label><select id="bits"><option selected>16</option><option>24</option><option>32</option></select></div>
      </div>
    </details>

    <div class="btn-row">
      <button id="run">Build dataset</button>
      <button id="run_test" class="btn-ghost" title="Process only the first 3 minutes of each source">Test (3 min)</button>
      <button id="stop" class="btn-ghost hidden" title="Stop the running build">Stop</button>
    </div>
    <p class="hint">Runs locally. Needs ffmpeg, yt-dlp, and a Whisper backend. Demucs optional.</p>
  </section>

  <section class="out">
    <div class="pet-track idle" id="pet_track"><img class="pet" id="pet" alt="" src="/assets/pet/dodoco-andersdotter-idle.gif"></div>
    <div class="progress"><i id="bar"></i><p id="status" class="status">Idle.</p></div>
    <div class="phases" id="phases"></div>
    <div id="summary" class="summary"></div>
    <pre id="log"><span class="ln" style="color:var(--muted)">Logs will appear here…</span></pre>
  </section>
</main>

<script>
const $ = (id) => document.getElementById(id);
const PHASES = ["download","transcribe","segment","clean","save"];
let polling = null, currentJob = null;
let currentProject = null;
let currentResumable = false;
let modelPolling = null, asrModels = [], activeModelDownload = null;
let uploadedLocalPaths = [];
let previewCursor = 0;
// Keyed live preview: clip_id -> row, preserving first-seen order so audio
// shows immediately and text fills in via later transcribing/done events.
let previewRows = new Map();
function upsertPreview(ev){
  const id = ev.clip_id || ev.audio_path;
  if (ev.status === "removed") { previewRows.delete(id); return; }
  const prev = previewRows.get(id) || {};
  // Never let a partial event blank out text we already captured.
  const text = (ev.text && ev.text.length) ? ev.text : (prev.text || "");
  previewRows.set(id, Object.assign({}, prev, ev, { clip_id: id, text: text }));
}
function previewList(){ return Array.from(previewRows.values()); }

// ---- tabs ----
document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
  document.querySelectorAll(".tabpane").forEach(x => x.classList.remove("active"));
  t.classList.add("active");
  document.querySelector(`.tabpane[data-pane="${t.dataset.tab}"]`).classList.add("active");
  updateTranscriptionSourceMode();
}));

function activeInputTab() {
  return document.querySelector(".tab.active")?.dataset.tab || "yt";
}

function updateTranscriptionSourceMode() {
  const local = activeInputTab() === "local";
  $("source_youtube").disabled = local;
  if (local) $("source_ai").checked = true;
  $("source_hint").textContent = local
    ? "Local files always use AI transcription."
    : "YouTube transcription uses subtitles/CC when available.";
  // Hide the AI-only settings (model, backend, prompt, confidence, device)
  // when the user chose YouTube transcription, since none of them apply.
  const aiOn = $("source_ai").checked;
  $("ai_settings").style.display = aiOn ? "" : "none";
}
// Re-run when the user flips between YouTube / AI transcription.
$("source_youtube").addEventListener("change", updateTranscriptionSourceMode);
$("source_ai").addEventListener("change", updateTranscriptionSourceMode);
updateTranscriptionSourceMode();

// ---- Cleaning section: LUFS chips, conditional rows, sample-rate hint ----
function updateCleaningUi() {
  const silenceOn = $("remove_silence").checked;
  $("silence_row").style.display = silenceOn ? "" : "none";
  const loudOn = $("loudnorm").checked;
  $("loudnorm_lufs").disabled = !loudOn;
  $("loudnorm_two_pass").disabled = !loudOn;
  const denoiseOn = $("denoise").checked;
  $("denoise_row").style.display = denoiseOn ? "" : "none";
  const sr = parseInt($("sample_rate").value, 10) || 24000;
  const hint = $("sample_rate_hint");
  if (hint) {
    if (sr >= 48000) hint.textContent = "48 kHz: ~3x larger files than 24 kHz with no quality gain for TTS.";
    else if (sr <= 16000) hint.textContent = "16 kHz: small files, fine for ASR; thin for TTS playback.";
    else hint.textContent = "";
  }
}
["remove_silence", "loudnorm", "denoise", "sample_rate"].forEach(id => {
  const el = $(id); if (el) el.addEventListener("change", updateCleaningUi);
});
document.querySelectorAll(".preset[data-lufs]").forEach(chip => {
  chip.addEventListener("click", () => {
    $("loudnorm_lufs").value = chip.dataset.lufs;
    $("loudnorm").checked = true;
    updateCleaningUi();
    setStatus("LUFS set to " + chip.dataset.lufs + ".", "ok");
  });
});
updateCleaningUi();

// ---- local file uploads ----
const dropzone = $("dropzone");
const filePicker = $("file_picker");
const uploadList = $("upload_list");
function appendManualPath(path) {
  const box = $("local_sources");
  const existing = box.value.trim();
  box.value = existing ? existing + "\n" + path : path;
}
async function uploadLocalFiles(files) {
  const chosen = [...files].filter(f => f && (f.type.startsWith("audio/") || f.type.startsWith("video/") || !f.type));
  if (!chosen.length) return;
  for (const file of chosen) {
    const row = document.createElement("div");
    row.textContent = `Uploading ${file.name}...`;
    uploadList.prepend(row);
    try {
      const res = await fetch("/api/upload-local", {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream", "X-Filename": encodeURIComponent(file.name) },
        body: file,
      }).then(r => r.json());
      if (res.error) throw new Error(res.error);
      uploadedLocalPaths.push(res.path);
      appendManualPath(res.path);
      row.textContent = `Ready: ${res.path}`;
    } catch (e) {
      row.textContent = `Upload failed: ${file.name} - ${e}`;
    }
  }
}
dropzone.addEventListener("click", () => filePicker.click());
dropzone.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); filePicker.click(); } });
filePicker.addEventListener("change", e => uploadLocalFiles(e.target.files));
["dragenter", "dragover"].forEach(name => dropzone.addEventListener(name, e => { e.preventDefault(); dropzone.classList.add("drag"); }));
["dragleave", "drop"].forEach(name => dropzone.addEventListener(name, e => { e.preventDefault(); dropzone.classList.remove("drag"); }));
dropzone.addEventListener("drop", e => uploadLocalFiles(e.dataTransfer.files));
$("manual_paths").addEventListener("change", e => {
  $("manual_paths_box").classList.toggle("show", e.target.checked);
});

// ---- phases chips ----
function renderPhases(active, overall) {
  const box = $("phases"); box.innerHTML = "";
  const ai = PHASES.indexOf(active);
  PHASES.forEach((p, i) => {
    const s = document.createElement("span"); s.textContent = p;
    if (i < ai) s.classList.add("done");
    if (i === ai) s.classList.add("active");
    box.appendChild(s);
  });
}
renderPhases("", 0);

// ---- settings / ASR model downloads ----
function openSettings() {
  $("settings_modal").classList.add("show");
  $("settings_modal").setAttribute("aria-hidden", "false");
  loadAsrModels();
}
function closeSettings() {
  $("settings_modal").classList.remove("show");
  $("settings_modal").setAttribute("aria-hidden", "true");
}
$("settings_open").addEventListener("click", openSettings);
$("settings_close").addEventListener("click", closeSettings);
$("settings_modal").addEventListener("click", e => { if (e.target.id === "settings_modal") closeSettings(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") closeSettings(); });

function renderAsrModelOptions(models) {
  const sel = $("whisper_model");
  const current = sel.value;
  [...sel.querySelectorAll("optgroup[data-asr-group='1']")].forEach(o => o.remove());
  const available = (models || []).filter(m => m.downloaded);
  const unavailable = (models || []).filter(m => !m.downloaded);
  const addGroup = (label, items, disabled) => {
    if (!items.length) return;
    const group = document.createElement("optgroup");
    group.label = label;
    group.dataset.asrGroup = "1";
    items.forEach(m => {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = disabled ? `${m.label} (download in Settings)` : m.label;
      opt.dataset.asr = "1";
      opt.disabled = !!disabled;
      group.appendChild(opt);
    });
    sel.appendChild(group);
  };
  addGroup("Downloaded ASR models", available, false);
  addGroup("Available to download", unavailable, true);
  if ([...sel.options].some(o => o.value === current && !o.disabled)) {
    sel.value = current;
  } else if ([...sel.options].some(o => o.value === current)) {
    sel.value = "base";
  }
  updateModelHint();
}

function selectAsrModel(modelId) {
  const sel = $("whisper_model");
  const opt = [...sel.options].find(o => o.value === modelId && !o.disabled);
  if (!opt) return;
  sel.value = modelId;
  updateModelHint();
  setStatus("ASR model selected.", "ok");
  closeSettings();
}

function updateModelHint() {
  const selected = asrModels.find(m => m.id === $("whisper_model").value);
  const hint = $("model_hint");
  const backend = $("whisper_backend");
  if (selected) {
    hint.textContent = `${selected.label} will run through Transformers from ${selected.local_dir}.`;
    backend.disabled = true;
  } else {
    hint.textContent = "Whisper models use the selected backend below.";
    backend.disabled = false;
  }
}

function renderModelList(models) {
  const box = $("model_list");
  box.innerHTML = "";
  (models || []).forEach(m => {
    const row = document.createElement("div"); row.className = "model-row";
    const left = document.createElement("div");
    left.innerHTML = `<div class="model-name">${escapeHtml(m.label)}</div>` +
      `<div class="model-meta">${escapeHtml(m.id)}<br/>${escapeHtml(m.local_dir)}</div>` +
      `<div class="model-state"><span class="dot ${m.downloaded ? "ok" : (m.requires_token ? "warn" : "")}"></span>` +
      `${m.downloaded ? "Downloaded" : (m.requires_token ? "Request access + token needed" : "Not downloaded")}</div>`;
    const actions = document.createElement("div"); actions.className = "model-actions";
    if (m.downloaded) {
      const selectBtn = document.createElement("button");
      selectBtn.textContent = "Select";
      selectBtn.addEventListener("click", () => selectAsrModel(m.id));
      actions.appendChild(selectBtn);
    }
    const btn = document.createElement("button");
    btn.className = m.downloaded ? "btn-ghost" : "";
    btn.textContent = m.downloading ? "Downloading" : (m.downloaded ? "Ready" : "Download");
    btn.disabled = !!m.downloaded || !!m.downloading;
    btn.addEventListener("click", () => startModelDownload(m.id));
    actions.appendChild(btn);
    row.appendChild(left); row.appendChild(actions); box.appendChild(row);
  });
}

async function loadAsrModels() {
  try {
    const d = await fetch("/api/asr-models").then(r => r.json());
    asrModels = d.models || [];
    renderAsrModelOptions(asrModels);
    renderModelList(asrModels);
  } catch (e) {
    $("download_log").classList.add("show");
    $("download_log").textContent = "Could not load model list: " + e;
  }
}

async function startModelDownload(modelId) {
  clearTimeout(modelPolling);
  activeModelDownload = modelId;
  $("download_log").classList.add("show");
  $("download_log").textContent = "Starting download...";
  $("download_bar").classList.add("on");
  renderModelList(asrModels.map(m => m.id === modelId ? {...m, downloading:true} : m));
  let res;
  try {
    res = await fetch("/api/asr-download", { method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ model_id:modelId, hf_token:$("hf_token").value }) }).then(r => r.json());
  } catch (e) {
    $("download_log").textContent = "Download request failed: " + e;
    $("download_bar").classList.remove("on");
    activeModelDownload = null;
    renderModelList(asrModels);
    return;
  }
  if (res.error) {
    $("download_log").textContent = res.error;
    $("download_bar").classList.remove("on");
    activeModelDownload = null;
    renderModelList(asrModels);
    return;
  }
  pollModelDownload(res.job_id, 0);
}

function pollModelDownload(jobId, since) {
  fetch(`/api/asr-download/${jobId}?since=${since}`).then(r => r.json()).then(d => {
    if (d.error) { $("download_log").classList.add("show"); $("download_log").textContent += "\n" + d.error; $("download_bar").classList.remove("on"); return; }
    if (d.logs && d.logs.length) {
      const log = $("download_log");
      if (since === 0) log.textContent = "";
      log.textContent += d.logs.join("\n") + "\n";
      log.scrollTop = log.scrollHeight;
    }
    if (d.models) {
      asrModels = d.models;
      renderAsrModelOptions(asrModels);
      renderModelList(asrModels.map(m => m.id === activeModelDownload && d.status === "running" ? {...m, downloading:true} : m));
    }
    if (d.status === "running") modelPolling = setTimeout(() => pollModelDownload(jobId, d.total), 1200);
    else {
      $("download_bar").classList.remove("on");
      activeModelDownload = null;
      if (d.status === "done") $("download_log").classList.remove("show");
      loadAsrModels();
    }
  }).catch(() => { modelPolling = setTimeout(() => pollModelDownload(jobId, since), 1800); });
}
loadAsrModels();
$("whisper_model").addEventListener("change", updateModelHint);

// ---- presets ----
fetch("/api/presets").then(r => r.json()).then(d => {
  const box = $("presets");
  Object.keys(d.presets || {}).forEach(name => {
    const b = document.createElement("div"); b.className = "preset"; b.textContent = name;
    b.addEventListener("click", () => applyPreset(d.presets[name]));
    box.appendChild(b);
  });
});
function applyPreset(p) {
  for (const [k, v] of Object.entries(p)) {
    if (k === "prefer_subtitles") {
      $(v ? "source_youtube" : "source_ai").checked = true;
      continue;
    }
    const el = $(k); if (!el) continue;
    if (el.type === "checkbox") el.checked = !!v; else el.value = v;
  }
  updateTranscriptionSourceMode();
  updateCleaningUi();
  setStatus("Preset applied.", "ok");
}

// The pet is an animated GIF that swaps per state. Each GIF self-animates, so
// we only change the src when the action actually changes (swapping src
// restarts the GIF, so avoid doing it every tick).
const PET_GIF = {
  idle:     "/assets/pet/dodoco-andersdotter-idle.gif",
  waving:   "/assets/pet/dodoco-andersdotter-waving.gif",
  jumping:  "/assets/pet/dodoco-andersdotter-jumping.gif",
  waiting:  "/assets/pet/dodoco-andersdotter-waiting.gif",
  running:  "/assets/pet/dodoco-andersdotter-running.gif",
  review:   "/assets/pet/dodoco-andersdotter-review.gif",
  runRight: "/assets/pet/dodoco-andersdotter-running-right.gif",
  runLeft:  "/assets/pet/dodoco-andersdotter-running-left.gif",
};
// Actions the pet plays in place while idle (stay put, just animate).
const PET_IDLE_STILL = ["idle", "waving", "jumping", "waiting", "running", "review"];
let petIdleTimer = null;

function petSetGif(name) {
  const pet = $("pet"); if (!pet) return;
  const src = PET_GIF[name] || PET_GIF.idle;
  if (!pet.src.endsWith(src)) pet.src = src;  // only swap on change => no restart flicker
}

function petStopIdle() {
  if (petIdleTimer) { clearTimeout(petIdleTimer); petIdleTimer = null; }
}

const rand = (a, b) => a + Math.random() * (b - a);
const pick = arr => arr[Math.floor(Math.random() * arr.length)];

// Free-roaming "live" mode: each turn the pet rolls a random action. Sometimes
// it dashes across the lane (directional run GIFs), sometimes it stops and
// plays an in-place animation (wave, jump, review, ...).
let petX = 0;
const PET_SPEED = 42; // px per second for directional runs => natural pace
function petStartIdle() {
  const track = $("pet_track"); const pet = $("pet");
  if (!track || !pet) return;
  track.classList.add("idle");
  if (petIdleTimer) return; // already living its life
  const step = () => {
    const lane = Math.max(1, track.clientWidth - pet.clientWidth);
    // ~45% of the time take a stroll, otherwise stand and emote.
    if (Math.random() < 0.45) {
      // Dash to the far side of the lane, facing the way we travel.
      const goRight = petX < lane / 2;
      const target = goRight ? lane : 0;
      const dur = Math.max(0.4, Math.abs(target - petX) / PET_SPEED);
      petSetGif(goRight ? "runRight" : "runLeft");
      pet.style.setProperty("--pet-move", dur.toFixed(2) + "s");
      pet.style.setProperty("--pet-x", target.toFixed(1) + "px");
      petX = target;
      petIdleTimer = setTimeout(step, dur * 1000 + rand(200, 600));
    } else {
      // Stand still and play a random in-place animation for a moment.
      petSetGif(pick(PET_IDLE_STILL));
      petIdleTimer = setTimeout(step, rand(2200, 4200));
    }
  };
  step();
}

function setPet(frac, reset=false, done=false, phase=null) {
  const track = $("pet_track"); const pet = $("pet"); if (!track || !pet) return;
  const p = Math.max(0, Math.min(1, Number(frac) || 0));
  // Build in progress: pet walks the lane in lockstep with the progress bar.
  const running = reset || (!done && p > 0 && p < 1);
  if (running) {
    petStopIdle();
    track.classList.remove("idle");
    petSetGif("runRight");
    pet.style.setProperty("--pet-move", "0.8s");
    const lane = track.clientWidth - pet.clientWidth;
    petX = lane * p;
    pet.style.setProperty("--pet-x", petX.toFixed(1) + "px");
  } else if (done) {
    // Finished: stand at the end of the lane and wave.
    petStopIdle();
    track.classList.remove("idle");
    petSetGif("waving");
    const lane = track.clientWidth - pet.clientWidth;
    petX = lane;
    pet.style.setProperty("--pet-move", "0.6s");
    pet.style.setProperty("--pet-x", petX.toFixed(1) + "px");
  } else {
    // Idle: roll random actions to stay lively.
    petStartIdle();
  }
}

function setStatus(text, cls) {
  const el = $("status"); if (!el) return;
  el.textContent = text;
  el.className = "status" + (cls ? " " + cls : "");
}

// ---- Reveal a project subfolder in Finder / Explorer / xdg-open ----
// Asks the local server (which runs on the user's machine) to spawn the
// platform-native opener. Safe: server clamps the path to inside the project.
async function openFolder(subpath, label) {
  if (!currentProject) {
    setStatus("Open a project first.", "err");
    return;
  }
  setStatus("Opening " + (label || subpath || "project folder") + "…");
  try {
    const res = await fetch("/api/open", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project: currentProject, subpath: subpath || "" }),
    }).then(r => r.json());
    if (res.error) { setStatus(res.error, "err"); return; }
    setStatus("Opened " + (label || subpath || "project folder") + ".", "ok");
  } catch (e) {
    setStatus("Open failed: " + e, "err");
  }
}
$("open_project_dir").addEventListener("click", () => openFolder("", "project folder"));

// What folder each chosen Output Format actually wants the user to reveal.
// Keep these aligned with metadata.py / pipeline.py layout.
const OPENER_TARGETS = [
  { id: "open_root",   label: "Project",   subpath: ""           },
  { id: "open_audios", label: "audios/",   subpath: "audios"     },
  { id: "open_wavs",   label: "wavs/ (XTTS)",  subpath: "wavs",  fmts: ["csv"] },
  { id: "open_fish",   label: "fish/ (Fish Speech)", subpath: "fish", fmts: ["fish"] },
  { id: "open_refs",   label: "references/",  subpath: "references" },
];

function renderOpeners(formats) {
  // formats: lowercase array like ["jsonl","csv","fish","gpt-sovits"]
  const fmts = (formats || []).map(s => String(s).toLowerCase());
  const chips = OPENER_TARGETS.filter(t => !t.fmts || t.fmts.some(f => fmts.includes(f)))
    .map(t => `<span class="preset" data-open="${t.subpath}" data-label="${escapeHtml(t.label)}">📂 ${escapeHtml(t.label)}</span>`)
    .join("");
  return chips ? `<div class="presets" style="margin-top:10px;">${chips}</div>` : "";
}
// Event delegation for the chips, since the summary HTML is re-rendered.
$("summary").addEventListener("click", (e) => {
  const chip = e.target.closest(".preset[data-open]");
  if (!chip) return;
  openFolder(chip.dataset.open, chip.dataset.label || chip.dataset.open);
});

function payload(testMode) {
  const localSources = $("manual_paths").checked ? $("local_sources").value : uploadedLocalPaths.join("\n");
  const useYoutubeTranscription = activeInputTab() === "yt" && $("source_youtube").checked;
  return {
    urls: $("urls").value, local_sources: localSources,
    speaker_id: $("speaker_id").value, language: $("language").value,
    project: currentProject || "", whisper_model: $("whisper_model").value,
    whisper_backend: $("whisper_backend").value, device: $("device").value,
    initial_prompt: $("initial_prompt").value, min_confidence: $("min_confidence").value,
    prefer_subtitles: useYoutubeTranscription,
    remove_silence: $("remove_silence").checked, loudnorm: $("loudnorm").checked,
    loudnorm_lufs: $("loudnorm_lufs").value, denoise: $("denoise").checked,
    loudnorm_two_pass: $("loudnorm_two_pass").checked,
    silence_threshold_db: $("silence_threshold_db").value,
    highpass_hz: $("highpass_hz").value,
    demucs_model: $("demucs_model").value,
    sample_rate: $("sample_rate").value, output_formats: $("output_formats").value,
    min_clip: $("min_clip").value, max_clip: $("max_clip").value,
    val_ratio: $("val_ratio").value, merge_gap: $("merge_gap").value,
    make_references: $("make_references").checked, keep_source_audio: $("keep_source_audio").checked,
    channels: $("channels").value, bits: $("bits").value,
    limit_seconds: testMode ? 180 : "",
  };
}

function renderPreviewRows(items, jobId) {
  let html = `<div class="ds-head">Dataset <span class="ds-count">${items.length} clips</span>` +
             `<span class="edit-hint">double-click text to edit</span></div>`;
  html += `<div class="ds-list">`;
  items.forEach((c, i) => {
    const url = jobId
      ? `/api/clip?job=${jobId}&path=${encodeURIComponent(c.audio_path)}`
      : `/api/clip?project=${encodeURIComponent(currentProject)}&path=${encodeURIComponent(c.audio_path)}`;
    const name = c.audio_path.split("/").pop();
    const cid = c.clip_id || name.replace(/\.[^.]+$/, "");
    const transcribing = c.status === "transcribing";
    let body;
    if (transcribing && !c.text) {
      body = `<span class="pending">transcribing…</span>`;
    } else {
      // Editable transcription. Double-click to edit; saves on blur or idle.
      body = `<span class="editable" data-clip="${escapeHtml(cid)}" tabindex="0" `
           + `title="Double-click to edit">${escapeHtml(c.text)}</span>`;
    }
    html += `<div class="clip${transcribing ? " is-transcribing" : ""}" data-clip="${escapeHtml(cid)}">` +
            `<span class="idx">${i + 1}</span>` +
            `<audio controls preload="none" src="${url}"></audio>` +
            `<div class="txt"><div class="fn">${escapeHtml(name)}${c.duration != null ? " · " + c.duration + "s" : ""}</div>` +
            `${body}</div></div>`;
  });
  html += `</div>`;
  return html;
}

// ---- inline transcription editing ----
let editingClipId = null;   // suppress list re-render while editing
let editIdleTimer = null;

function setRowText(clipId, text){
  if (previewRows.has(clipId)) {
    const row = previewRows.get(clipId);
    previewRows.set(clipId, Object.assign({}, row, { text: text }));
  }
}

async function saveClipText(span){
  const clipId = span.dataset.clip;
  const text = span.textContent.trim();
  if (span.dataset.saved === text) return;   // nothing changed since last save
  span.dataset.saved = text;
  span.classList.add("saving");
  setRowText(clipId, text);
  try {
    await fetch("/api/edit-clip", { method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ job_id: currentJob || "", project: currentJob ? "" : (currentProject || ""), clip_id: clipId, text: text }) });
  } catch (e) { /* keep local edit even if the save call fails */ }
  setTimeout(() => span.classList.remove("saving"), 500);
}

function beginEdit(span){
  if (span.classList.contains("editing")) return;
  editingClipId = span.dataset.clip;
  span.dataset.saved = span.textContent.trim();
  span.contentEditable = "true";
  span.classList.add("editing");
  span.focus();
  // place caret / select all for quick correction
  const r = document.createRange(); r.selectNodeContents(span);
  const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
}

function endEdit(span){
  clearTimeout(editIdleTimer);
  span.contentEditable = "false";
  span.classList.remove("editing");
  editingClipId = null;
  saveClipText(span);
}

// Event delegation on the summary box (rows are re-rendered as innerHTML).
$("summary").addEventListener("dblclick", (e) => {
  const span = e.target.closest(".editable");
  if (span) beginEdit(span);
});
$("summary").addEventListener("blur", (e) => {
  const span = e.target.closest && e.target.closest(".editable");
  if (span && span.classList.contains("editing")) endEdit(span);
}, true);
$("summary").addEventListener("input", (e) => {
  const span = e.target.closest && e.target.closest(".editable");
  if (!span || !span.classList.contains("editing")) return;
  clearTimeout(editIdleTimer);
  editIdleTimer = setTimeout(() => endEdit(span), 3000);   // idle auto-save
});
$("summary").addEventListener("keydown", (e) => {
  const span = e.target.closest && e.target.closest(".editable");
  if (!span || !span.classList.contains("editing")) return;
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); span.blur(); }
  else if (e.key === "Escape") { e.preventDefault(); span.textContent = span.dataset.saved || ""; span.blur(); }
});

function showLivePreview(jobId) {
  const items = previewList();
  if (!items.length) return;
  // Don't wipe the DOM while the user is editing a transcription.
  if (editingClipId !== null) return;
  const done = items.filter(c => c.status !== "transcribing").length;
  const box = $("summary"); box.classList.add("show");
  box.innerHTML = `<b>${done}</b> clips ready · transcribing...` + renderPreviewRows(items, jobId);
}

function showSummary(s, jobId) {
  if (!s) return;
  const box = $("summary"); box.classList.add("show");
  let html =
    `<b>${s.clips}</b> clips (${s.train_clips} train / ${s.val_clips} val) · ` +
    `<b>${s.references}</b> refs · <b>${s.total_audio_min}</b> min · ${s.sample_rate} Hz · ` +
    `speaker <b>${s.speaker_id}</b><br/>Formats: ${(s.formats||[]).join(", ")}<br/>` +
    `Output: <code>${s.output_dir}</code>`;
  html += renderOpeners(s.formats);
  if (s.preview && s.preview.length) {
    html += renderPreviewRows(s.preview, jobId);
  }
  box.innerHTML = html;
}
function escapeHtml(s){ return (s||"").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c])); }

async function build(testMode) {
  const localPaneActive = document.querySelector('.tab[data-tab="local"]').classList.contains("active");
  if (localPaneActive && !$("manual_paths").checked && !uploadedLocalPaths.length) {
    setStatus("Drop or choose at least one local file, or turn on manual paths.", "err");
    return;
  }
  $("run").disabled = true; $("run_test").disabled = true;
  $("stop").classList.remove("hidden"); $("stop").disabled = false;
  $("log").textContent = ""; $("summary").classList.remove("show");
  previewCursor = 0; previewRows = new Map();
  $("bar").style.width = "0%"; renderPhases("download", 0); setPet(0, true);
  setStatus("Starting…");
  let res;
  try {
    res = await fetch("/api/build", { method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify(payload(testMode)) }).then(r => r.json());
  } catch (e) { setStatus("Request failed: " + e, "err"); reEnable(); return; }
  if (res.error) { setStatus(res.error, "err"); reEnable(); return; }
  currentJob = res.job_id; poll(res.job_id, 0);
}
function reEnable(){ $("run").disabled = false; $("run_test").disabled = false; $("stop").disabled = true; $("stop").classList.add("hidden"); }

function poll(jobId, since) {
  setStatus("Running…"); clearTimeout(polling);
  fetch(`/api/job/${jobId}?since=${since}&preview_since=${previewCursor}`).then(r => r.json()).then(d => {
    if (d.error) { setStatus(d.error, "err"); reEnable(); return; }
    if (d.logs && d.logs.length) {
      const log = $("log");
      for (const line of d.logs) {
        const span = document.createElement("span"); span.className = "ln"; span.textContent = line;
        log.appendChild(span);
      }
      log.scrollTop = log.scrollHeight;
    }
    if (d.preview && d.preview.length) {
      d.preview.forEach(upsertPreview);
      previewCursor = d.preview_total || previewCursor;
      showLivePreview(jobId);
    } else if (typeof d.preview_total === "number") {
      previewCursor = d.preview_total;
    }
    if (typeof d.overall === "number") { $("bar").style.width = (d.overall*100).toFixed(1) + "%"; renderPhases(d.phase, d.overall); setPet(d.overall); }
    const next = d.total;
    if (d.status === "running") { polling = setTimeout(() => poll(jobId, next), 900); }
    else if (d.status === "done") {
      $("bar").style.width = "100%"; renderPhases("", 1); setPet(1, false, true);
      setStatus("Done.", "ok"); showSummary(d.summary, jobId);
      setResumable(false); reEnable();
    } else if (d.status === "cancelled") {
      setStatus("Saved. Click Resume to continue.", "warn");
      setResumable(true); reEnable();
    } else { setStatus("Failed: " + (d.error || "unknown error"), "err"); reEnable(); }
  }).catch(() => { polling = setTimeout(() => poll(jobId, since), 1500); });
}

async function stop() {
  if (!currentJob) return;
  $("stop").disabled = true;
  setStatus("Stopping…", "warn");
  try {
    await fetch("/api/cancel", { method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ job_id: currentJob }) }).then(r => r.json());
  } catch (e) { setStatus("Stop request failed: " + e, "err"); }
}
$("stop").addEventListener("click", stop);
$("run").addEventListener("click", () => build(false));
$("run_test").addEventListener("click", () => build(true));

// ---- resume button state ----
function setResumable(on){
  currentResumable = !!on;
  $("run").textContent = on ? "Resume" : "Build dataset";
  $("run_test").classList.toggle("hidden", !!on);
}

// ---- projects: home view + per-project URL routing ----
function fmtMeta(p){
  const bits = [];
  if (p.clips) bits.push(p.clips + " clips");
  if (p.total_audio_min) bits.push(p.total_audio_min + " min");
  if (p.speaker_id) bits.push(p.speaker_id);
  return bits.join(" · ") || "Empty project";
}
async function loadProjects(){
  let data;
  try { data = await fetch("/api/projects").then(r => r.json()); }
  catch(e){ data = { projects: [] }; }
  const list = data.projects || [];
  const box = $("project_list");
  $("home_open").classList.toggle("hidden", list.length === 0);
  if (!list.length){ box.innerHTML = '<div class="empty">No projects yet. Create one to get started.</div>'; return; }
  let html = '<h3>Recent projects</h3>';
  list.forEach(p => {
    let badge = "";
    if (p.resumable) badge = '<span class="pbadge resume">Resume</span>';
    else if (p.partial) badge = '<span class="pbadge partial">Partial</span>';
    html += `<button class="pcard" data-name="${escapeHtml(p.name)}">`
          + `<div class="pmain"><div class="pname">${escapeHtml(p.name)}</div>`
          + `<div class="pmeta">${escapeHtml(fmtMeta(p))}</div></div>${badge}</button>`;
  });
  box.innerHTML = html;
  box.querySelectorAll(".pcard").forEach(btn =>
    btn.addEventListener("click", () => navigateTo(btn.dataset.name)));
}
function showHome(){
  currentProject = null;
  $("home").classList.remove("hidden");
  $("builder").classList.add("hidden");
  $("header_sub").textContent = "Pick a project to continue, or create a new one.";
  document.title = "Voice Dataset Builder";
  $("open_project_dir").classList.add("hidden");
  loadProjects();
}
function applyInputs(inputs){
  if (!inputs) return;
  // Restore previously saved YouTube URLs first so we can pick the right tab.
  const savedUrls = (inputs.urls || "").trim();
  const savedLocal = (inputs.local_sources || "").trim();
  for (const [k, v] of Object.entries(inputs)){
    if (k === "prefer_subtitles"){ $(v ? "source_youtube" : "source_ai").checked = true; continue; }
    if (k === "local_sources" || k === "limit_seconds") continue;
    const el = $(k); if (!el) continue;
    if (el.type === "checkbox") el.checked = !!v; else el.value = v;
  }
  // Restore local file paths the user supplied / uploaded last time so the
  // "Resume working" build can re-use them without re-typing or re-uploading.
  if (savedLocal){
    $("local_sources").value = savedLocal;
    $("manual_paths").checked = true;
    $("manual_paths_box").classList.add("show");
    uploadedLocalPaths = savedLocal.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
    const uploadList = $("upload_list");
    if (uploadList){
      uploadList.innerHTML = "";
      uploadedLocalPaths.forEach(p => {
        const row = document.createElement("div");
        row.textContent = "Saved: " + p;
        uploadList.appendChild(row);
      });
    }
    // Switch to the Local files tab if the project was built from local files
    // and there were no YouTube URLs.
    if (!savedUrls){
      document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
      document.querySelectorAll(".tabpane").forEach(x => x.classList.remove("active"));
      const localTab = document.querySelector('.tab[data-tab="local"]');
      const localPane = document.querySelector('.tabpane[data-pane="local"]');
      if (localTab) localTab.classList.add("active");
      if (localPane) localPane.classList.add("active");
    }
  } else {
    uploadedLocalPaths = [];
  }
  updateTranscriptionSourceMode();
  updateCleaningUi();
}
async function showProject(name){
  currentProject = name;
  $("home").classList.add("hidden");
  $("builder").classList.remove("hidden");
  $("open_project_dir").classList.remove("hidden");
  $("header_sub").textContent = "Project: " + name;
  document.title = name + " · Voice Dataset Builder";
  setStatus("Idle.");
  setPet(0);  // wake the pet into its idle "live" stroll
  $("summary").classList.remove("show"); $("summary").innerHTML = "";
  previewRows = new Map();
  try {
    const info = await fetch("/api/project/" + encodeURIComponent(name)).then(r => r.json());
    if (!info.error){
      applyInputs(info.inputs);
      setResumable(info.resumable);
      showProjectClips(info.clips || []);
    } else setResumable(false);
  } catch(e){ setResumable(false); }
}

// Render the clips already saved in an opened project (read + edit).
function showProjectClips(clips){
  if (!clips.length) return;
  // Seed previewRows so inline edits stay consistent with the live builder.
  previewRows = new Map();
  clips.forEach(c => previewRows.set(c.clip_id || c.audio_path, c));
  const box = $("summary"); box.classList.add("show");
  // null jobId => renderPreviewRows builds project-scoped clip URLs.
  // We don't know which formats this project shipped with on disk, so show
  // every opener whose folder happens to exist on the server side. The server
  // gracefully 404s on missing folders, so the chips that don't apply are
  // harmless.
  const openers = renderOpeners(["csv", "fish", "gpt-sovits", "jsonl"]);
  box.innerHTML = `<b>${clips.length}</b> clips in this dataset · double-click text to edit`
                + openers
                + renderPreviewRows(clips, null);
}
function navigateTo(name){
  history.pushState({ project: name }, "", "/" + encodeURIComponent(name));
  showProject(name);
}
function route(){
  const seg = decodeURIComponent(location.pathname.replace(/^\/+|\/+$/g, ""));
  if (seg && seg !== "index.html") showProject(seg);
  else showHome();
}
window.addEventListener("popstate", route);
$("home_link").addEventListener("click", e => { e.preventDefault(); history.pushState({}, "", "/"); showHome(); });
// ---- create-project dialog ----
function openNewProject(){
  const m = $("newproj_modal");
  $("newproj_name").value = "";
  $("newproj_error").classList.remove("show"); $("newproj_error").textContent = "";
  $("newproj_submit").disabled = false;
  m.classList.add("show"); m.setAttribute("aria-hidden", "false");
  setTimeout(() => $("newproj_name").focus(), 30);
}
function closeNewProject(){
  const m = $("newproj_modal");
  m.classList.remove("show"); m.setAttribute("aria-hidden", "true");
}
async function submitNewProject(){
  const name = $("newproj_name").value.trim();
  const err = $("newproj_error");
  if (!name){ err.textContent = "Please enter a project name."; err.classList.add("show"); $("newproj_name").focus(); return; }
  $("newproj_submit").disabled = true;
  let res;
  try {
    res = await fetch("/api/create-project", { method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ name }) }).then(r => r.json());
  } catch(e){ err.textContent = "Create failed: " + e; err.classList.add("show"); $("newproj_submit").disabled = false; return; }
  if (res.error){ err.textContent = res.error; err.classList.add("show"); $("newproj_submit").disabled = false; return; }
  closeNewProject();
  navigateTo(res.name);
}
$("home_create").addEventListener("click", openNewProject);
$("newproj_close").addEventListener("click", closeNewProject);
$("newproj_cancel").addEventListener("click", closeNewProject);
$("newproj_submit").addEventListener("click", submitNewProject);
$("newproj_modal").addEventListener("click", e => { if (e.target.id === "newproj_modal") closeNewProject(); });
$("newproj_name").addEventListener("keydown", e => {
  if (e.key === "Enter"){ e.preventDefault(); submitNewProject(); }
  else if (e.key === "Escape"){ e.preventDefault(); closeNewProject(); }
});
$("newproj_name").addEventListener("input", () => $("newproj_error").classList.remove("show"));
$("home_open").addEventListener("click", () => {
  $("project_list").scrollIntoView({ behavior: "smooth" });
});
route();
</script>
</body>
</html>"""
