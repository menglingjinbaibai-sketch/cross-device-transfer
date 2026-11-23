import os
import sys
import socket
import threading
import time
import json
import urllib.parse
import shutil
import re
import mimetypes
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import tkinter as tk
from tkinter import ttk, messagebox

# 保证 Windows 下控制台编码安全，杜绝闪退
if sys.platform == "win32":
    try:
        import io
        if sys.stdout and hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        if sys.stderr and hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

# ================= 默认配置 =================
DEFAULT_PORT = 8080 # 完美对齐本地 cpolar 8080 端口
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

INBOX_DIR = os.path.join(APP_DIR, "我接收的文件")
OUTBOX_DIR = os.path.join(APP_DIR, "电脑待分享的文件")
os.makedirs(INBOX_DIR, exist_ok=True)
os.makedirs(OUTBOX_DIR, exist_ok=True)

def get_live_cpolar_url(target_port=None):
    """自动从本机 cpolar 日志读取当前生效且指向目标端口的公网域名"""
    import glob
    port_str = str(target_port or actual_port or DEFAULT_PORT)
    default_url = "https://3b341ac2.r10.cpolar.top"
    url_pat = r'https://[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.cpolar\.(?:top|cn|io)'
    try:
        log_pattern = os.path.join(os.path.expanduser("~"), ".cpolar", "logs", "cpolar_service.log*")
        logs = [f for f in glob.glob(log_pattern) if 'master' not in f]
        if logs:
            logs.sort(key=os.path.getmtime, reverse=True)
            for log_file in logs:
                if os.path.getsize(log_file) == 0:
                    continue
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                for line in reversed(content.splitlines()):
                    if f':{port_str}' in line and ('NewTunnel' in line or 'RespStartTunnel' in line or 'LocalAddr' in line):
                        m = re.findall(url_pat, line)
                        if m:
                            return m[-1]
                all_m = re.findall(url_pat, content)
                if all_m:
                    return all_m[-1]
    except Exception:
        pass
    return default_url

CPOLAR_PLACEHOLDER = "__LIVE_CPOLAR_URL__"
MY_CPOLAR_DOMAIN = get_live_cpolar_url(DEFAULT_PORT)
auto_burn_after_download = True

# 仅记录“本次打开/本次会话”新接收的文件名：每次重启默认清空，不暴露电脑里以前收过的历史文件
session_recv_files = set()
session_lock = threading.Lock()

actual_port = DEFAULT_PORT

# ================= 网络探测与智能分类 =================
def get_all_ips():
    ips = {"wifi": [], "cable": [], "remote": [], "all": []}
    try:
        hostname = socket.gethostname()
        all_addrs = socket.gethostbyname_ex(hostname)[2]
        for ip in all_addrs:
            if ip.startswith("127.") or ip.startswith("198.18."):
                continue
            ips["all"].append(("物理网卡", ip))
            if ip.startswith("169.254."):
                ips["cable"].append(ip)
            elif ip.startswith("100."):
                ips["remote"].append(ip)
            elif ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172."):
                ips["wifi"].append(ip)
            else:
                ips["remote"].append(ip)
    except Exception as e:
        print("IP检测异常:", e)

    if not ips["wifi"] and ips["all"]:
        ips["wifi"].append(ips["all"][0][1])
    if not ips["cable"]:
        if ips["all"]:
            ips["cable"].append(ips["all"][0][1])
        else:
            ips["cable"].append("169.254.1.2")
    return ips

ips_data = get_all_ips()
wifi_ip = ips_data["wifi"][0] if ips_data["wifi"] else "127.0.0.1"
cable_ip = ips_data["cable"][0] if ips_data["cable"] else "169.254.1.2"

# ================= 1:1 完美对接用户定制的顶级审美 UI =================
HTML_TEMPLATE = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#FAFAF9">
<title>跨设备传输 - 极速直连</title>
<style>
:root{{
  --bg:#FAFAF9;
  --surface:#FFFFFF;
  --ink:#16161A;
  --ink2:#6B6B73;
  --ink3:#A3A3AB;
  --line:#ECECE8;
  --line2:#DDDDD8;
  --accent:#2E6BE6;
  --accent-soft:#EFF4FE;
  --ok:#17996A;
  --ok-soft:#EBF9F2;
  --warn:#D94949;
  --warn-soft:#FDF1F1;
  --r:14px;
  --ease:cubic-bezier(.22,.61,.36,1);
}}
*{{box-sizing:border-box}}
html,body{{margin:0;padding:0}}
body{{
  background:var(--bg);
  color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro SC","PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,sans-serif;
  font-size:14px;line-height:1.6;
  -webkit-font-smoothing:antialiased;
  -webkit-tap-highlight-color:transparent;
}}
button,input{{font-family:inherit}}

.app{{max-width:1000px;margin:0 auto;padding:40px 24px 52px}}

/* ---------- enter animation ---------- */
.rise{{opacity:0;transform:translateY(10px);animation:rise .62s var(--ease) forwards}}
@keyframes rise{{to{{opacity:1;transform:none}}}}
.d1{{animation-delay:.04s}}.d2{{animation-delay:.10s}}.d3{{animation-delay:.16s}}
.d4{{animation-delay:.22s}}.d5{{animation-delay:.28s}}.d6{{animation-delay:.34s}}

/* ---------- header ---------- */
.hd{{display:flex;align-items:center;justify-content:space-between;margin-bottom:34px}}
.hd-l{{display:flex;align-items:center;gap:11px}}
.logo{{
  width:26px;height:26px;border-radius:8px;background:var(--ink);
  display:flex;align-items:center;justify-content:center;color:#fff;flex:none;
}}
.logo svg{{width:15px;height:15px}}
.hd h1{{font-size:15px;font-weight:500;margin:0;letter-spacing:.01em}}
.hd p{{font-size:12px;color:var(--ink3);margin:0}}
.status{{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--ink2)}}
.dot{{width:6px;height:6px;border-radius:50%;background:var(--ok);position:relative}}
.dot::after{{
  content:"";position:absolute;inset:-3px;border-radius:50%;
  border:1px solid var(--ok);opacity:.5;animation:breathe 2.6s var(--ease) infinite;
}}
@keyframes breathe{{0%{{transform:scale(.7);opacity:.55}}70%{{transform:scale(1.55);opacity:0}}100%{{opacity:0}}}}

/* ---------- segmented ---------- */
.seg{{
  position:relative;display:grid;grid-template-columns:repeat(3,1fr);
  background:#F1F1EE;border-radius:11px;padding:3px;margin-bottom:12px;
}}
.seg-pill{{
  position:absolute;top:3px;left:3px;height:calc(100% - 6px);
  width:calc((100% - 6px)/3);background:var(--surface);border-radius:8px;
  box-shadow:0 1px 2px rgba(22,22,26,.07),0 0 0 .5px rgba(22,22,26,.04);
  transition:transform .46s var(--ease);
}}
.seg button{{
  position:relative;z-index:1;border:0;background:none;cursor:pointer;
  padding:9px 6px;font-size:13px;color:var(--ink2);border-radius:8px;
  transition:color .3s var(--ease);
}}
.seg button.on{{color:var(--ink);font-weight:500}}

.mode-info{{
  display:flex;align-items:center;gap:8px;font-size:12px;color:var(--ink3);
  padding-left:2px;margin-bottom:26px;min-height:19px;
}}
.mode-info .sw{{width:3px;height:3px;border-radius:50%;background:var(--ink3);opacity:.6}}
.mode-info.swap{{animation:fadeSwap .42s var(--ease)}}
@keyframes fadeSwap{{0%{{opacity:0;transform:translateY(3px)}}100%{{opacity:1;transform:none}}}}

/* ---------- cards ---------- */
.card{{
  background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r);padding:18px 20px;
}}
.card-hd{{display:flex;align-items:center;justify-content:space-between;margin-bottom:4px}}
.card-hd h2{{font-size:13px;font-weight:500;margin:0}}
.card-hd .sub{{font-size:11.5px;color:var(--ink3)}}
.tag{{font-size:11px;padding:2px 8px;border-radius:20px;line-height:1.6}}
.tag.priv{{background:#F2F2EF;color:var(--ink2)}}
.tag.pub{{background:var(--accent-soft);color:var(--accent)}}

/* ---------- drop ---------- */
.drop{{
  border:1.5px dashed var(--line2);border-radius:var(--r);
  padding:30px 20px;text-align:center;cursor:pointer;background:var(--surface);
  transition:border-color .3s var(--ease),background .3s var(--ease),transform .35s var(--ease);
  margin-bottom:12px;
}}
.drop:hover{{border-color:#C9C9C3;background:#FDFDFC}}
.drop:hover .drop-ic{{transform:translateY(-3px)}}
.drop.over{{border-color:var(--accent);background:var(--accent-soft);transform:scale(1.008)}}
.drop.over .drop-ic{{transform:translateY(-5px)}}
.drop-ic{{
  width:42px;height:42px;border-radius:13px;background:#F5F5F2;
  display:flex;align-items:center;justify-content:center;
  margin:0 auto 13px;color:var(--ink2);
  transition:transform .38s var(--ease),color .3s var(--ease),background .3s var(--ease);
}}
.drop.over .drop-ic{{color:var(--accent);background:var(--accent-soft);transform:translateY(-4px)}}
.drop strong{{display:block;font-size:13.5px;font-weight:500;margin-bottom:3px}}
.drop span{{font-size:12px;color:var(--ink3)}}

.mobile-acts{{display:none;gap:10px;margin-bottom:14px}}
.mact{{
  flex:1;display:flex;flex-direction:column;align-items:center;gap:9px;
  padding:22px 10px;background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r);font-size:13px;color:var(--ink);cursor:pointer;
  transition:.24s var(--ease);
}}
.mact:active{{transform:scale(.97);background:#F7F7F5}}
.mact svg{{width:24px;height:24px;color:var(--ink2)}}

/* ---------- upload queue ---------- */
.queue{{display:none;background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r);padding:2px 18px;margin-bottom:14px}}
.queue.on{{display:block;animation:rise .42s var(--ease)}}
.qitem{{padding:12px 0;border-bottom:1px solid var(--line);overflow:hidden;
  transition:max-height .38s var(--ease),opacity .3s var(--ease),padding .38s var(--ease),border-color .3s;
  max-height:72px}}
.qitem:last-child{{border-bottom:0}}
.qitem.gone{{max-height:0;opacity:0;padding-top:0;padding-bottom:0;border-color:transparent}}
.qtop{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:7px}}
.qname{{font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.qstat{{font-size:11.5px;color:var(--ink3);font-variant-numeric:tabular-nums;flex:none;
  transition:color .3s}}
.qitem.done .qstat{{color:var(--ok)}}
.bar{{height:3px;background:#F0F0ED;border-radius:2px;overflow:hidden}}
.bar i{{display:block;height:100%;width:0;background:var(--ink);border-radius:2px;
  transition:width .34s var(--ease),background .3s}}
.qitem.done .bar i{{background:var(--ok)}}

/* ---------- link & text row ---------- */
.linkrow{{
  display:flex;align-items:center;gap:9px;background:var(--surface);
  border:1px solid var(--line);border-radius:var(--r);padding:11px 12px 11px 16px;
  margin-bottom:14px;transition:border-color .25s
}}
.link-qr-row{{
  display:flex;align-items:center;gap:12px;background:var(--surface);
  border:1px solid var(--line);border-radius:var(--r);padding:12px 14px 12px 16px;
  margin-bottom:14px;transition:border-color .25s
}}
.link-qr-main{{
  flex:1;min-width:0;display:flex;align-items:center;gap:9px;
}}
.link-qr-main .lk{{color:var(--ink3);flex:none;display:flex;font-size:11px;font-weight:600}}
.link-qr-main input{{
  flex:1;min-width:0;border:0;background:none;outline:none;
  font-size:12.5px;color:var(--ink2);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  text-overflow:ellipsis;
}}
.qr-side{{
  display:flex;align-items:center;gap:10px;padding-left:12px;
  border-left:1px solid var(--line);flex:none;
}}
.qr-side img{{
  width:96px;height:96px;border-radius:10px;border:0;
  padding:0;background:#FFFFFF!important;display:block;
  box-shadow:0 2px 10px rgba(6,95,70,.16);
  filter:none!important;-webkit-filter:none!important;
  mix-blend-mode:normal!important;isolation:isolate;
  color-scheme:light;forced-color-adjust:none;
}}
@media (prefers-color-scheme:dark){{
  .qr-side img{{
    box-shadow:0 0 0 2px rgba(255,255,255,.92),0 4px 14px rgba(0,0,0,.45);
  }}
}}
.qr-side-txt{{
  font-size:11.5px;color:var(--ink2);line-height:1.45;
}}
.qr-side-txt strong{{
  display:block;font-size:12.5px;font-weight:500;color:var(--ink);margin-bottom:2px;
}}
.linkrow:focus-within{{border-color:var(--line2)}}
.linkrow .lk{{color:var(--ink3);flex:none;display:flex;font-size:11px;font-weight:600}}
.linkrow input{{
  flex:1;min-width:0;border:0;background:none;outline:none;
  font-size:12.5px;color:var(--ink2);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  text-overflow:ellipsis;
}}
.linkrow input.text-in{{
  font-family:inherit;color:var(--ink);
}}
.btn{{
  border:1px solid var(--line2);background:var(--surface);color:var(--ink);
  font-size:12.5px;padding:7px 13px;border-radius:9px;cursor:pointer;
  transition:.22s var(--ease);white-space:nowrap;
}}
.btn:hover{{border-color:#C6C6C0;background:#FCFCFB}}
.btn:active{{transform:scale(.97)}}
.btn.ok{{color:var(--ok);border-color:#C6E7D8;background:var(--ok-soft)}}
.btn.block{{width:100%;padding:9px 13px}}
.btn.danger{{color:var(--warn);border-color:#F1D3D3;background:var(--warn-soft)}}
.btn.danger:hover{{background:#FCE9E9;border-color:#E8BDBD}}
.btn.plain{{border-color:transparent;background:transparent;color:var(--ink2);font-size:11.5px;padding:4px 9px}}
.btn.plain:hover{{background:#F4F4F1;color:var(--ink)}}

/* ---------- file lists ---------- */
.cols{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}
.cols>*{{min-width:0}}
.flist{{list-style:none;margin:8px 0 0;padding:0 0 2px;max-height:268px;overflow-y:auto}}
.flist::-webkit-scrollbar{{width:4px}}
.flist::-webkit-scrollbar-thumb{{background:#E0E0DB;border-radius:2px}}
.flist::-webkit-scrollbar-track{{background:transparent}}

.fitem{{
  display:flex;align-items:center;gap:10px;padding:9px 6px;border-radius:9px;
  max-height:58px;overflow:hidden;
  transition:max-height .4s var(--ease),opacity .28s var(--ease),
             transform .28s var(--ease),padding .4s var(--ease),background .2s;
}}
.fitem:hover{{background:#FAFAF8}}
.fitem:hover .fname{{transform:translateX(2px)}}
.fitem.gone{{max-height:0;opacity:0;padding-top:0;padding-bottom:0;transform:translateX(14px)}}
.fitem.fresh{{opacity:0;transform:translateY(-8px)}}

.ficon{{
  width:28px;height:28px;flex:none;border-radius:8px;background:#F4F4F1;
  display:flex;align-items:center;justify-content:center;
  font-size:10px;font-weight:500;color:var(--ink2);letter-spacing:.02em;
}}
.fitem[data-k="img"] .ficon{{background:#F1F4FB;color:#4A6FA5}}
.fitem[data-k="vid"] .ficon{{background:#F7F2F5;color:#96547C}}
.fitem[data-k="doc"] .ficon{{background:#F1F5F9;color:#4B7396}}
.fitem[data-k="txt"] .ficon{{background:#FEF3C7;color:#B45309}}
.fmeta{{min-width:0;flex:1}}
.fname{{font-size:12.5px;display:block;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;transition:transform .28s var(--ease)}}
.fsub{{font-size:11px;color:var(--ink3);font-variant-numeric:tabular-nums}}
.acts{{display:flex;align-items:center;gap:6px;flex:none}}
.act{{
  border:1px solid var(--line2);background:var(--surface);color:var(--ink2);
  font-size:11.5px;padding:4px 11px;border-radius:7px;cursor:pointer;flex:none;
  transition:.2s var(--ease);text-decoration:none;display:inline-block;
}}
.act:hover{{border-color:var(--ink3);color:var(--ink)}}
.act.done{{color:var(--ok);border-color:#C6E7D8;background:var(--ok-soft)}}

.empty{{font-size:12px;color:var(--ink3);padding:22px 6px;text-align:center}}

.wx-warn{{display:none;background:#FFFBEB;border:1px solid #FCD34D;color:#92400E;padding:10px 14px;
  border-radius:12px;font-size:12.5px;line-height:1.55;margin-bottom:14px}}
.modal-mask{{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:99;display:none;
  align-items:center;justify-content:center;padding:16px}}
.modal-mask.show{{display:flex}}
.modal-card{{background:#fff;border-radius:16px;max-width:520px;width:100%;padding:16px;
  max-height:92vh;display:flex;flex-direction:column;gap:10px}}
.modal-tip{{background:#EFF4FE;color:#1E40AF;border-radius:10px;padding:9px 12px;font-size:12.5px;line-height:1.5}}
.modal-img{{background:#0E0E10;border-radius:10px;padding:6px;display:flex;justify-content:center;overflow:auto}}
.modal-img img{{max-width:100%;max-height:58vh;object-fit:contain;
  -webkit-touch-callout:default!important;-webkit-user-select:auto!important;user-select:auto!important}}
.modal-btns{{display:flex;gap:8px}}
.modal-btns .btn,.modal-btns a.btn{{flex:1;text-align:center;text-decoration:none;padding:10px 8px}}

.card .foot{{margin-top:12px;display:flex;gap:8px}}

/* ---------- toast ---------- */
.toast{{
  position:fixed;left:50%;bottom:32px;transform:translate(-50%,14px);
  background:var(--ink);color:#fff;font-size:12.5px;padding:9px 16px;
  border-radius:10px;opacity:0;pointer-events:none;z-index:50;
  transition:opacity .3s var(--ease),transform .38s var(--ease);
  display:flex;align-items:center;gap:8px;max-width:calc(100vw - 40px);
}}
.toast.show{{opacity:1;transform:translate(-50%,0)}}
.toast svg{{width:13px;height:13px;flex:none;color:#7FE3B4}}

.foot-note{{
  text-align:center;font-size:11.5px;color:var(--ink3);margin-top:34px;
  letter-spacing:.02em;
}}
.foot-note em{{font-style:normal;color:var(--ink3);opacity:.55;margin:0 7px}}

/* ---------- mobile ---------- */
@media (max-width:760px){{
  .app{{padding:26px 16px 48px}}
  .hd{{margin-bottom:22px}}
  .hd p{{display:none}}
  .drop{{display:none}}
  .mobile-acts{{display:flex}}
  .cols{{grid-template-columns:minmax(0,1fr)}}
  .link-qr-row{{flex-direction:column;align-items:stretch;gap:10px}}
  .qr-side{{padding-left:0;padding-top:10px;border-left:0;border-top:1px solid var(--line);justify-content:center}}
  .card{{padding:15px 14px;min-width:0;overflow:hidden}}
  .seg button{{padding:8px 4px;font-size:12.5px}}
  .mode-info{{font-size:11.5px;margin-bottom:20px}}
  .flist{{max-height:none}}
  .fitem{{max-height:none;flex-wrap:wrap;padding:10px 4px;gap:8px}}
  .fmeta{{min-width:0;flex:1 1 120px;overflow:hidden}}
  .acts{{margin-left:auto}}
  .act{{padding:6px 11px;font-size:12px}}
  #openInboxBtn{{display:none}}
  .toast{{bottom:24px}}
  .foot-note{{margin-top:26px}}
}}
@media (prefers-reduced-motion:reduce){{
  *{{animation-duration:.01ms!important;transition-duration:.01ms!important}}
}}
</style>
</head>
<body>

<svg width="0" height="0" style="position:absolute" aria-hidden="true">
  <symbol id="i-swap" viewBox="0 0 24 24">
    <path d="M4 9h13l-3.5-3.5M20 15H7l3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
  </symbol>
  <symbol id="i-up" viewBox="0 0 24 24">
    <path d="M12 16.5V5m0 0L7.4 9.6M12 5l4.6 4.6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M4.5 15.5v2.5a2 2 0 002 2h11a2 2 0 002-2v-2.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
  </symbol>
  <symbol id="i-album" viewBox="0 0 24 24">
    <rect x="3.5" y="5" width="17" height="14" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.5"/>
    <circle cx="9" cy="10" r="1.4" fill="none" stroke="currentColor" stroke-width="1.4"/>
    <path d="M5 16.5l4-3.6 3.4 2.8 2.6-2.2 4 3" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  </symbol>
  <symbol id="i-cam" viewBox="0 0 24 24">
    <path d="M3.5 8.5h2.2L7.3 6h9.4l1.6 2.5h2.2a1.5 1.5 0 011.5 1.5v7.5a1.5 1.5 0 01-1.5 1.5H3.5A1.5 1.5 0 012 17.5V10a1.5 1.5 0 011.5-1.5z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" transform="translate(0,-1)"/>
    <circle cx="12" cy="13.5" r="3.2" fill="none" stroke="currentColor" stroke-width="1.5"/>
  </symbol>
  <symbol id="i-link" viewBox="0 0 24 24">
    <path d="M10 13.5a4 4 0 005.7 0l2.8-2.8a4 4 0 00-5.7-5.7l-1.5 1.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    <path d="M14 10.5a4 4 0 00-5.7 0l-2.8 2.8a4 4 0 005.7 5.7l1.5-1.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
  </symbol>
  <symbol id="i-check" viewBox="0 0 24 24">
    <path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  </symbol>
</svg>

<div class="app">

  <header class="hd rise">
    <div class="hd-l">
      <div class="logo"><svg><use href="#i-swap"/></svg></div>
      <div>
        <h1>跨设备传输</h1>
        <p>三模式直连 · 收发隔离 · 阅后即焚</p>
      </div>
    </div>
    <div class="status"><span class="dot"></span>服务运行中</div>
  </header>

  <div class="wx-warn" id="wxWarn">⚠️ 检测到在微信/QQ内打开：这里无法保存文件。请点右上角 <b>「···」→「在浏览器中打开」</b>（Safari / 系统浏览器）后再点【下载】。</div>

  <div class="seg rise d1" id="seg">
    <span class="seg-pill" id="pill"></span>
    <button class="on" data-mode="wifi">WiFi 局域网</button>
    <button data-mode="lan">网线直连</button>
    <button data-mode="wan">公网远程</button>
  </div>

  <div class="mode-info rise d2" id="modeInfo">
    <span id="infoText">同网直连 · 约 30–80 MB/s · 不消耗外网流量</span>
  </div>

  <div class="rise d3">
    <div class="drop" id="drop">
      <div class="drop-ic"><svg width="19" height="19"><use href="#i-up"/></svg></div>
      <strong>拖拽文件或图片到这里</strong>
      <span>或点击选择文件 · 电脑与手机均可直接下载保存</span>
    </div>

    <div class="mobile-acts">
      <button class="mact" id="pickMobile">
        <svg><use href="#i-album"/></svg>选取相册／文件
      </button>
      <button class="mact" id="shotMobile">
        <svg><use href="#i-cam"/></svg>实时拍照上传
      </button>
    </div>

    <div class="linkrow">
      <span class="lk">TXT</span>
      <input id="textInput" class="text-in" placeholder="输入或粘贴文字内容，发送后手机与电脑均可复制或下载保存...">
      <button class="btn" id="sendTextBtn">发送文字</button>
    </div>

    <div class="queue" id="queue"></div>
  </div>

  <div class="link-qr-row rise d4">
    <div class="link-qr-main">
      <span class="lk"><svg width="15" height="15"><use href="#i-link"/></svg></span>
      <input id="urlInput" readonly value="http://{wifi_ip}:{actual_port}">
      <button class="btn" id="copyBtn">复制链接</button>
    </div>
    <div class="qr-side">
      <img id="qrImg" src="/api/qrcode?url=http%3A%2F%2F{wifi_ip}%3A{actual_port}&v=3" alt="扫码打开网址">
      <div class="qr-side-txt">
        <strong>手机扫码直达</strong>
        <span>扫码直接跳转此网址</span>
      </div>
    </div>
  </div>

  <div class="cols rise d5">
    <section class="card">
      <div class="card-hd">
        <h2>我接收的文件</h2>
        <span class="tag priv">仅显示本次 · 换人可清空</span>
      </div>
      <ul class="flist" id="recvList">
        <div class="empty">暂未接收文件</div>
      </ul>
      <div class="foot">
        <button class="btn block" id="openInboxBtn">打开文件夹</button>
        <button class="btn danger block" id="clearRecvBtn">清空本次记录</button>
      </div>
    </section>

    <section class="card">
      <div class="card-hd">
        <h2>待分享的文件</h2>
        <span class="tag pub">公开 · 阅后即焚</span>
      </div>
      <ul class="flist" id="shareList">
        <div class="empty">暂无待分享的文件</div>
      </ul>
      <div class="foot">
        <button class="btn block" id="addShareBtn">添加分享文件</button>
        <button class="btn danger block" id="clearBtn">一键清空分享</button>
      </div>
    </section>
  </div>

  <p class="foot-note">零安装<em>·</em>零登录<em>·</em>零残留</p>
</div>

<div class="modal-mask" id="photoModal">
  <div class="modal-card">
    <div class="modal-tip">💡 <b>长按下方图片</b> → 选择【存储图像 / 保存图片】即可存入手机相册</div>
    <div class="modal-img"><img id="photoImg" alt=""></div>
    <div class="modal-btns">
      <button class="btn ok" id="shareImgBtn" style="display:none">系统保存/分享</button>
      <a class="btn" id="photoDl" href="#" download>下载原图</a>
      <button class="btn" id="photoClose">关闭</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"><svg><use href="#i-check"/></svg><span id="toastText"></span></div>

<input type="file" id="fileInput" multiple hidden>
<input type="file" id="shareFileInput" multiple hidden>
<input type="file" id="camInput" accept="image/*" capture="environment" hidden>

<script>
var MODES = {{
  wifi:{{ info:'同网直连 · 约 30–80 MB/s · 不消耗外网流量', url:'http://{wifi_ip}:{actual_port}', speed:56 }},
  lan: {{ info:'169.254 自适应网段已捕获 · 千兆全速 · 脱网可用', url:'http://{cable_ip}:{actual_port}', speed:108 }},
  wan: {{ info:'专属公网域名 · 全国任意城市输入网址即连', url:'{CPOLAR_PLACEHOLDER}', speed:15 }}
}};
var mode = 'wifi';
var speedBase = MODES.wifi.speed;

var seg = document.getElementById('seg');
var pill = document.getElementById('pill');
var infoText = document.getElementById('infoText');
var modeInfo = document.getElementById('modeInfo');
var urlInput = document.getElementById('urlInput');
var qrImg = document.getElementById('qrImg');

function setMode(key, idx){{
  mode = key;
  speedBase = MODES[key].speed;
  pill.style.transform = 'translateX(' + (idx * 100) + '%)';
  Array.prototype.forEach.call(seg.querySelectorAll('button'), function(b, i){{
    b.classList.toggle('on', i === idx);
  }});
  infoText.textContent = MODES[key].info;
  urlInput.value = MODES[key].url;
  if (qrImg) qrImg.src = '/api/qrcode?url=' + encodeURIComponent(MODES[key].url) + '&v=3';
  modeInfo.classList.remove('swap');
  void modeInfo.offsetWidth;
  modeInfo.classList.add('swap');
}}

Array.prototype.forEach.call(seg.querySelectorAll('button'), function(b, i){{
  b.addEventListener('click', function(){{ setMode(b.dataset.mode, i); }});
}});

(function initDetectedMode(){{
  var h = window.location.hostname || '';
  if (h.indexOf('cpolar.') !== -1) {{
    MODES.wan.url = window.location.origin;
    setMode('wan', 2);
  }}
  else if (h.indexOf('169.254.') === 0) setMode('lan', 1);
  else setMode('wifi', 0);
}})();

/* ---------- toast ---------- */
var toastEl = document.getElementById('toast');
var toastText = document.getElementById('toastText');
var toastTimer = null;
function toast(msg){{
  toastText.textContent = msg;
  toastEl.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(function(){{ toastEl.classList.remove('show'); }}, 2400);
}}

/* ---------- copy ---------- */
function copyStr(text, cb){{
  if (navigator.clipboard && navigator.clipboard.writeText){{
    navigator.clipboard.writeText(text).then(cb).catch(cb);
  }} else {{
    var ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    if (cb) cb();
  }}
}}

var copyBtn = document.getElementById('copyBtn');
copyBtn.addEventListener('click', function(){{
  var text = urlInput.value;
  copyStr(text, function(){{
    copyBtn.textContent = '已复制';
    copyBtn.classList.add('ok');
    toast('链接已复制，发给对方即可打开');
    setTimeout(function(){{
      copyBtn.textContent = '复制链接';
      copyBtn.classList.remove('ok');
    }}, 1600);
  }});
}});

/* ---------- upload ---------- */
var queue = document.getElementById('queue');
var shareList = document.getElementById('shareList');
var recvList = document.getElementById('recvList');
var fileInput = document.getElementById('fileInput');
var shareFileInput = document.getElementById('shareFileInput');
var camInput = document.getElementById('camInput');
var drop = document.getElementById('drop');

function fmtSize(b){{
  if (b >= 1073741824) return (b/1073741824).toFixed(2) + ' GB';
  if (b >= 1048576) return (b/1048576).toFixed(1) + ' MB';
  if (b >= 1024) return Math.round(b/1024) + ' KB';
  return b + ' B';
}}
function extOf(name){{
  var p = name.split('.');
  if (p.length < 2) return 'FILE';
  return p.pop().slice(0,4).toUpperCase();
}}
function kindOf(name){{
  var e = name.split('.').pop().toLowerCase();
  if (['jpg','jpeg','png','gif','webp','heic','bmp'].indexOf(e) > -1) return 'img';
  if (['mp4','mov','avi','mkv','webm'].indexOf(e) > -1) return 'vid';
  if (e === 'txt') return 'txt';
  return 'doc';
}}

function uploadRealFile(file, targetBox){{
  var box = targetBox || 'inbox';
  queue.classList.add('on');
  var item = document.createElement('div');
  item.className = 'qitem';
  item.innerHTML =
    '<div class="qtop"><span class="qname"></span><span class="qstat">0%</span></div>' +
    '<div class="bar"><i></i></div>';
  item.querySelector('.qname').textContent = file.name;
  queue.appendChild(item);

  var stat = item.querySelector('.qstat');
  var fill = item.querySelector('.bar i');
  var startTime = Date.now();

  var xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/upload?box=' + box + '&filename=' + encodeURIComponent(file.name), true);
  
  xhr.upload.onprogress = function(e){{
    if (e.lengthComputable){{
      var pct = Math.round((e.loaded / e.total) * 100);
      fill.style.width = pct + '%';
      var elapsed = (Date.now() - startTime) / 1000;
      var mbps = elapsed > 0 ? (e.loaded / (1024*1024*elapsed)).toFixed(1) : '0';
      stat.textContent = pct + '%  ·  ' + mbps + ' MB/s';
    }}
  }};

  xhr.onload = function(){{
    if (xhr.status === 200){{
      stat.textContent = '已完成';
      item.classList.add('done');
      setTimeout(function(){{
        item.classList.add('gone');
        setTimeout(function(){{
          item.remove();
          if (!queue.children.length) queue.classList.remove('on');
        }}, 420);
        toast('✅ 发送成功，手机与电脑均可直接下载');
        loadAllFiles();
      }}, 500);
    }} else {{
      stat.textContent = '失败';
    }}
  }};

  xhr.onerror = function(){{
    stat.textContent = '网络中断';
  }};

  xhr.send(file);
}}

function handleFiles(list, targetBox){{
  if (!list || !list.length) return;
  Array.prototype.forEach.call(list, function(f){{ uploadRealFile(f, targetBox); }});
}}

drop.addEventListener('click', function(){{ fileInput.click(); }});
document.getElementById('pickMobile').addEventListener('click', function(){{ fileInput.click(); }});
document.getElementById('shotMobile').addEventListener('click', function(){{ camInput.click(); }});
document.getElementById('addShareBtn').addEventListener('click', function(){{ shareFileInput.click(); }});

fileInput.addEventListener('change', function(e){{ handleFiles(e.target.files, 'inbox'); e.target.value = ''; }});
shareFileInput.addEventListener('change', function(e){{ handleFiles(e.target.files, 'outbox'); e.target.value = ''; }});
camInput.addEventListener('change', function(e){{ handleFiles(e.target.files, 'inbox'); e.target.value = ''; }});

['dragenter','dragover'].forEach(function(t){{
  drop.addEventListener(t, function(e){{ e.preventDefault(); drop.classList.add('over'); }});
}});
['dragleave','drop'].forEach(function(t){{
  drop.addEventListener(t, function(e){{ e.preventDefault(); drop.classList.remove('over'); }});
}});
drop.addEventListener('drop', function(e){{
  if (e.dataTransfer && e.dataTransfer.files) handleFiles(e.dataTransfer.files, 'inbox');
}});

/* ---------- 发送文字 ---------- */
var textInput = document.getElementById('textInput');
var sendTextBtn = document.getElementById('sendTextBtn');
function sendTextContent(){{
  var val = textInput.value.trim();
  if (!val){{
    toast('请先输入要发送的文字');
    return;
  }}
  fetch('/api/send_text', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ text: val }})
  }}).then(function(r){{
    if (r.ok){{
      textInput.value = '';
      toast('✅ 文字已发送，可点击复制或下载保存');
      loadAllFiles();
    }}
  }});
}}
sendTextBtn.addEventListener('click', sendTextContent);
textInput.addEventListener('keydown', function(e){{
  if (e.key === 'Enter') sendTextContent();
}});

/* ---------- 打开接收文件夹 ---------- */
document.getElementById('openInboxBtn').addEventListener('click', function(){{
  fetch('/api/open_folder', {{ method: 'POST' }});
  toast('已在电脑端打开接收文件夹');
}});

/* ---------- 微信/QQ 提示 ---------- */
if (/micromessenger/i.test(navigator.userAgent) || navigator.userAgent.toLowerCase().indexOf('qq/') !== -1) {{
  document.getElementById('wxWarn').style.display = 'block';
}}

/* ---------- 图片预览（长按存相册） ---------- */
var photoModal = document.getElementById('photoModal');
var photoImg = document.getElementById('photoImg');
var photoDl = document.getElementById('photoDl');
var shareImgBtn = document.getElementById('shareImgBtn');
function openPhoto(name, prevUrl, dlUrl){{
  photoImg.src = '';
  photoImg.src = prevUrl;
  photoDl.href = dlUrl;
  photoDl.download = name;
  shareImgBtn.style.display = (navigator.canShare && navigator.share) ? 'block' : 'none';
  shareImgBtn.onclick = function(){{
    fetch(prevUrl).then(function(r){{ return r.blob(); }}).then(function(blob){{
      var f = new File([blob], name, {{ type: blob.type || 'image/jpeg' }});
      if (navigator.canShare({{ files: [f] }})) {{
        return navigator.share({{ files: [f] }});
      }}
      toast('请直接长按图片保存');
    }}).catch(function(){{ toast('请直接长按图片保存'); }});
  }};
  photoModal.classList.add('show');
}}
document.getElementById('photoClose').addEventListener('click', function(){{ photoModal.classList.remove('show'); }});
photoModal.addEventListener('click', function(e){{ if (e.target === photoModal) photoModal.classList.remove('show'); }});

/* ---------- 渲染单行文件/文字项（带直接下载与复制） ---------- */
function createFileElement(item, box, isBurn){{
  var li = document.createElement('li');
  li.className = 'fitem';
  var kind = kindOf(item.name);
  li.dataset.k = kind;

  var dlPrefix = box === 'recv' ? '/download_recv/' : '/download/';
  var pvPrefix = box === 'recv' ? '/preview_recv/' : '/preview/';
  var dlUrl = dlPrefix + encodeURIComponent(item.name);
  var pvUrl = pvPrefix + encodeURIComponent(item.name);

  var titleText = item.text ? ('文字: ' + item.text) : item.name;
  var subText = fmtSize(item.size) + ' · ' + (isBurn ? '下载后60秒自动清除' : item.time);

  var html =
    '<span class="ficon">' + extOf(item.name) + '</span>' +
    '<div class="fmeta"><span class="fname"></span><span class="fsub">' + subText + '</span></div>' +
    '<div class="acts">';
  if (item.text) html += '<button class="act copy-txt-btn" type="button">复制</button>';
  if (kind === 'img') html += '<button class="act pv-btn" type="button">存相册</button>';
  html += '<a class="act dl-link">下载</a>';
  html += '</div>';

  li.innerHTML = html;
  li.querySelector('.fname').textContent = titleText;
  li.querySelector('.fname').title = titleText;
  var dlLink = li.querySelector('.dl-link');
  dlLink.href = dlUrl;
  dlLink.download = item.name;

  if (item.text) {{
    var cb = li.querySelector('.copy-txt-btn');
    cb.addEventListener('click', function(){{
      copyStr(item.text, function(){{
        cb.textContent = '已复制';
        toast('✅ 文字已复制');
        setTimeout(function(){{ cb.textContent = '复制'; }}, 1600);
      }});
    }});
  }}
  if (kind === 'img') {{
    li.querySelector('.pv-btn').addEventListener('click', function(){{ openPhoto(item.name, pvUrl, dlUrl); }});
  }}
  li.querySelector('.dl-link').addEventListener('click', function(){{
    toast('📥 已开始下载：' + item.name + '（手机在浏览器下载列表/文件App中查看）');
  }});
  return li;
}}

/* ---------- 真实拉取文件列表（内容无变化时不重绘，避免点击被打断） ---------- */
var sigRecv = '', sigShare = '';
function loadAllFiles(){{
  fetch('/api/recv_files', {{ cache: 'no-store' }})
    .then(function(r){{ return r.json(); }})
    .then(function(data){{
      var sig = JSON.stringify(data);
      if (sig === sigRecv) return;
      sigRecv = sig;
      if (!data || !data.length){{
        recvList.innerHTML = '<div class="empty">暂未接收文件</div>';
        return;
      }}
      recvList.innerHTML = '';
      data.forEach(function(item){{ recvList.appendChild(createFileElement(item, 'recv', false)); }});
    }}).catch(function(){{}});

  fetch('/api/files', {{ cache: 'no-store' }})
    .then(function(r){{ return r.json(); }})
    .then(function(data){{
      var sig = JSON.stringify(data);
      if (sig === sigShare) return;
      sigShare = sig;
      if (!data || !data.length){{
        shareList.innerHTML = '<div class="empty">暂无待分享的文件</div>';
        return;
      }}
      shareList.innerHTML = '';
      data.forEach(function(item){{ shareList.appendChild(createFileElement(item, 'share', true)); }});
    }}).catch(function(){{}});
}}

/* ---------- 清空本次接收记录（仅清页面，不删电脑本地文件） ---------- */
document.getElementById('clearRecvBtn').addEventListener('click', function(){{
  fetch('/api/clear_recv', {{ method: 'POST' }})
    .then(function(){{
      sigRecv = ''; recvList.innerHTML = '<div class="empty">暂未接收文件</div>';
      toast('已清空页面记录（已收文件仍保留在电脑文件夹）');
    }});
}});

/* ---------- 一键清空所有分享 ---------- */
document.getElementById('clearBtn').addEventListener('click', function(){{
  fetch('/api/clear', {{ method: 'POST' }})
    .then(function(){{
      sigShare = ''; shareList.innerHTML = '<div class="empty">暂无待分享的文件</div>';
      toast('已撤下全部待分享文件');
    }});
}});

loadAllFiles();
setInterval(loadAllFiles, 3500);
</script>
</body>
</html>
"""

def build_dir_file_list(folder, allowed_names=None):
    file_list = []
    try:
        entries = []
        for fname in os.listdir(folder):
            if allowed_names is not None and fname not in allowed_names:
                continue
            fpath = os.path.join(folder, fname)
            if os.path.isfile(fpath):
                stat = os.stat(fpath)
                entries.append((stat.st_mtime, fname, fpath, stat.st_size))
        # 按修改时间倒序排列（最新发送的排在最上面）
        entries.sort(key=lambda x: x[0], reverse=True)
        for mtime, fname, fpath, size in entries:
            mod_time = time.strftime("%m-%d %H:%M", time.localtime(mtime))
            item = {"name": fname, "size": size, "time": mod_time}
            if fname.lower().endswith(".txt") and size <= 64 * 1024:
                try:
                    with open(fpath, "r", encoding="utf-8-sig", errors="ignore") as tf:
                        item["text"] = tf.read().strip()
                except Exception:
                    pass
            file_list.append(item)
    except Exception:
        pass
    return file_list

# ================= 多线程 HTTP 传输后台 =================
class FileHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def serve_download(self, fpath, fname, burn=False, inline=False, head_only=False):
        if not os.path.isfile(fpath):
            self.send_error(404, "File Not Found")
            return

        mime_type, _ = mimetypes.guess_type(fname)
        if not mime_type:
            mime_type = "application/octet-stream"
        file_size = os.path.getsize(fpath)

        # 解析 Range（手机下载管理器 / iOS Safari 必需）
        start, end, status = 0, file_size - 1, 200
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes=") and file_size > 0:
            try:
                s_, e_ = rng[6:].split(",")[0].strip().split("-")
                if s_ == "":
                    start = max(0, file_size - int(e_))
                else:
                    start = int(s_)
                    if e_:
                        end = min(int(e_), file_size - 1)
                if start > end or start >= file_size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{file_size}")
                    self.end_headers()
                    return
                status = 206
            except Exception:
                start, end, status = 0, file_size - 1, 200

        length = end - start + 1 if file_size else 0
        base_n, ext_n = os.path.splitext(fname)
        clean_base = re.sub(r'[^A-Za-z0-9._-]+', '_', base_n).strip('_') or "file"
        clean_ext = re.sub(r'[^A-Za-z0-9.]', '', ext_n)
        ascii_name = f"{clean_base}{clean_ext}"
        disp = "inline" if inline else "attachment"
        resp_ctype = mime_type if inline else "application/octet-stream"
        self.send_response(status)
        self.send_header("Content-Type", resp_ctype)
        self.send_header("Content-Disposition",
                         f'{disp}; filename="{ascii_name}"; filename*=UTF-8\'\'{urllib.parse.quote(fname)}')
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "private, max-age=0, must-revalidate")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.end_headers()
        if head_only:
            return

        try:
            with open(fpath, "rb") as f:
                f.seek(start)
                remain = length
                while remain > 0:
                    chunk = f.read(min(64 * 1024, remain))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remain -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        if not inline and end == file_size - 1:
            print(f"[{time.strftime('%H:%M:%S')}] 已下载保存文件: {fname}")

        if burn and auto_burn_after_download and not inline and end == file_size - 1:
            # 延迟 60 秒清理，保证手机多次/分段请求都能完成
            def delayed_remove(target_path, target_name):
                try:
                    if os.path.exists(target_path):
                        os.remove(target_path)
                        print(f"[{time.strftime('%H:%M:%S')}] 🔥 [阅后即焚] 已清除: {target_name}")
                except Exception:
                    pass
            threading.Timer(60.0, delayed_remove, args=(fpath, fname)).start()

    def do_HEAD(self):
        url_parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(url_parsed.path)
        for prefix, folder, inline in (("/download_recv/", INBOX_DIR, False), ("/download/", OUTBOX_DIR, False),
                                       ("/preview_recv/", INBOX_DIR, True), ("/preview/", OUTBOX_DIR, True)):
            if path.startswith(prefix):
                fname = os.path.basename(path[len(prefix):])
                if folder == INBOX_DIR:
                    with session_lock:
                        if fname not in session_recv_files:
                            self.send_error(404, "File Not Found")
                            return
                fpath = os.path.join(folder, fname)
                self.serve_download(fpath, fname, inline=inline, head_only=True)
                return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        url_parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(url_parsed.path)

        if path == "/" or path == "/index.html":
            live_cpolar = get_live_cpolar_url(actual_port)
            html_out = HTML_TEMPLATE.replace(CPOLAR_PLACEHOLDER, live_cpolar).replace(f":{DEFAULT_PORT}", f":{actual_port}")
            payload = html_out.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(payload)

        elif path == "/api/qrcode":
            import io
            query = urllib.parse.parse_qs(url_parsed.query)
            target_url = query.get("url", [f"http://{wifi_ip}:{actual_port}"])[0]
            try:
                import qrcode
                from PIL import ImageOps
                qr = qrcode.QRCode(
                    version=None,
                    error_correction=qrcode.constants.ERROR_CORRECT_M,
                    box_size=8,
                    border=3,
                )
                qr.add_data(target_url)
                qr.make(fit=True)
                # 使用高对比度深绿+纯白配色，并内置翠绿反差边框：
                # 1) 避免手机/电脑深色主题及暗黑插件将黑白位图反色或洗白；
                # 2) 在浅色和纯黑背景下都能保持清晰白边静区和高扫码识别率。
                img = qr.make_image(fill_color="#065F46", back_color="#FFFFFF").convert("RGB")
                img = ImageOps.expand(img, border=6, fill="#10B981")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                png_bytes = buf.getvalue()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(png_bytes)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(png_bytes)
            except Exception as e:
                self.send_error(500, f"QR error: {e}")

        elif path == "/api/files":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(build_dir_file_list(OUTBOX_DIR), ensure_ascii=False).encode("utf-8"))

        elif path == "/api/recv_files":
            with session_lock:
                allowed = set(session_recv_files)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(build_dir_file_list(INBOX_DIR, allowed_names=allowed), ensure_ascii=False).encode("utf-8"))

        elif path.startswith("/preview_recv/") or path.startswith("/preview/"):
            is_recv = path.startswith("/preview_recv/")
            prefix = "/preview_recv/" if is_recv else "/preview/"
            fname = os.path.basename(path[len(prefix):])
            if is_recv:
                with session_lock:
                    if fname not in session_recv_files:
                        self.send_error(404, "File Not Found")
                        return
                fpath = os.path.join(INBOX_DIR, fname)
            else:
                fpath = os.path.join(OUTBOX_DIR, fname)
            self.serve_download(fpath, fname, inline=True)

        elif path.startswith("/download_recv/"):
            fname = os.path.basename(path[len("/download_recv/"):])
            with session_lock:
                if fname not in session_recv_files:
                    self.send_error(404, "File Not Found")
                    return
            fpath = os.path.join(INBOX_DIR, fname)
            self.serve_download(fpath, fname, burn=False)

        elif path.startswith("/download/"):
            fname = os.path.basename(path[len("/download/"):])
            fpath = os.path.join(OUTBOX_DIR, fname)
            self.serve_download(fpath, fname, burn=True)
        else:
            self.send_error(404)

    def do_POST(self):
        url_parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(url_parsed.path)

        if path == "/api/upload":
            query = urllib.parse.parse_qs(url_parsed.query)
            fname = query.get("filename", ["未命名文件"])[0]
            box = query.get("box", ["inbox"])[0]
            target_dir = OUTBOX_DIR if box == "outbox" else INBOX_DIR

            fname = os.path.basename(fname)
            base, ext = os.path.splitext(fname)
            save_path = os.path.join(target_dir, fname)
            counter = 1
            while os.path.exists(save_path):
                save_path = os.path.join(target_dir, f"{base}_{counter}{ext}")
                counter += 1
            final_fname = os.path.basename(save_path)

            content_length = int(self.headers.get("Content-Length", 0))
            bytes_read = 0

            print(f"[{time.strftime('%H:%M:%S')}] 开始接收文件: {final_fname} ({content_length} bytes)")
            with open(save_path, "wb") as f:
                while bytes_read < content_length:
                    chunk_size = min(64 * 1024, content_length - bytes_read)
                    chunk = self.rfile.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_read += len(chunk)

            if box != "outbox":
                with session_lock:
                    session_recv_files.add(final_fname)

            print(f"[{time.strftime('%H:%M:%S')}] ✅ 成功接收并保存: {final_fname}")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK")

        elif path == "/api/send_text":
            content_length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(content_length)
            try:
                text_val = json.loads(raw.decode("utf-8")).get("text", "").strip()
            except Exception:
                text_val = raw.decode("utf-8", errors="ignore").strip()

            if text_val:
                fname = f"文字_{time.strftime('%H%M%S')}.txt"
                save_path = os.path.join(INBOX_DIR, fname)
                counter = 1
                while os.path.exists(save_path):
                    save_path = os.path.join(INBOX_DIR, f"文字_{time.strftime('%H%M%S')}_{counter}.txt")
                    counter += 1
                with open(save_path, "wb") as f:
                    f.write(text_val.encode("utf-8-sig"))
                saved_txt_name = os.path.basename(save_path)
                with session_lock:
                    session_recv_files.add(saved_txt_name)
                print(f"[{time.strftime('%H:%M:%S')}] ✅ 收到文字消息并保存: {saved_txt_name}")

            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK")

        elif path == "/api/clear_recv":
            with session_lock:
                session_recv_files.clear()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK")

        elif path == "/api/clear":
            for f in os.listdir(OUTBOX_DIR):
                p = os.path.join(OUTBOX_DIR, f)
                if os.path.isfile(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK")

        elif path == "/api/open_folder":
            os.startfile(INBOX_DIR)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_error(404)

# ================= 后台服务守护 =================
server_instance = None
server_ready = threading.Event()

class DualStackHTTPServer(ThreadingHTTPServer):
    """同时监听 IPv6 (::1) 和 IPv4 (0.0.0.0)，防止 Windows 下 cpolar 转发 localhost:8080 走 ::1 时连接失败"""
    address_family = socket.AF_INET6

    def server_bind(self):
        try:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except Exception:
            pass
        super().server_bind()

def start_server():
    global server_instance, actual_port
    port = DEFAULT_PORT
    for _ in range(15):
        try:
            try:
                server_instance = DualStackHTTPServer(("::", port), FileHandler)
            except OSError:
                server_instance = ThreadingHTTPServer(("0.0.0.0", port), FileHandler)
            actual_port = port
            server_ready.set()
            print(f"[{time.strftime('%H:%M:%S')}] ⚡ 跨设备传输引擎已就绪，端口: {actual_port}")
            server_instance.serve_forever()
            break
        except OSError:
            port += 1
    else:
        server_ready.set()
        print("❌ 启动失败: 8080 端口被占用！")

# ================= 桌面轻量快捷托盘控制窗 =================
class TransferTrayApp:
    def __init__(self, root):
        self.root = root
        self.root.title("跨设备传输 - 服务运行中")
        self.root.geometry("460x320")
        self.root.resizable(False, False)
        self.root.configure(bg="#FAFAF9")

        # 启动后台服务
        threading.Thread(target=start_server, daemon=True).start()

        self.setup_ui()

    def setup_ui(self):
        container = tk.Frame(self.root, bg="#FAFAF9", padx=28, pady=24)
        container.pack(fill="both", expand=True)

        # 顶部状态
        hd = tk.Frame(container, bg="#FAFAF9")
        hd.pack(fill="x", pady=(0, 16))
        
        logo = tk.Label(hd, text=" ⇄ ", font=("Segoe UI", 12, "bold"), bg="#16161A", fg="#FFFFFF")
        logo.pack(side="left")
        
        tk.Label(hd, text="  跨设备传输", font=("微软雅黑", 14, "bold"), bg="#FAFAF9", fg="#16161A").pack(side="left")
        tk.Label(hd, text="● 服务运行中", font=("微软雅黑", 9), bg="#FAFAF9", fg="#17996A").pack(side="right")

        # 信息卡片
        card = tk.Frame(container, bg="#FFFFFF", relief="solid", bd=1, padx=16, pady=16)
        card.pack(fill="x", pady=8)

        tk.Label(card, text="传输 Web 界面已在本地与公网同步激活", font=("微软雅黑", 10, "bold"), bg="#FFFFFF", fg="#16161A").pack(anchor="w")
        tk.Label(card, text=f"• WiFi 局域网:  http://{wifi_ip}:{actual_port}", font=("Consolas", 9), bg="#FFFFFF", fg="#6B6B73").pack(anchor="w", pady=(6, 2))
        tk.Label(card, text=f"• 专属公网专线: {MY_CPOLAR_DOMAIN}", font=("Consolas", 9), bg="#FFFFFF", fg="#6B6B73").pack(anchor="w")

        # 操作大按钮
        btn_box = tk.Frame(container, bg="#FAFAF9")
        btn_box.pack(fill="x", pady=(18, 0))

        btn_open = tk.Button(btn_box, text="🚀 打开高颜值传输界面", font=("微软雅黑", 10, "bold"),
                             bg="#16161A", fg="#FFFFFF", relief="flat", padx=16, pady=9, cursor="hand2",
                             command=self.open_browser)
        btn_open.pack(fill="x", pady=4)

        sub_box = tk.Frame(btn_box, bg="#FAFAF9")
        sub_box.pack(fill="x", pady=4)

        tk.Button(sub_box, text="📥 打开接收文件夹", font=("微软雅黑", 9), bg="#FFFFFF", fg="#16161A",
                  relief="solid", bd=1, padx=10, pady=5, cursor="hand2",
                  command=lambda: os.startfile(INBOX_DIR)).pack(side="left", expand=True, fill="x", padx=(0, 4))
        
        tk.Button(sub_box, text="📤 打开分享文件夹", font=("微软雅黑", 9), bg="#FFFFFF", fg="#16161A",
                  relief="solid", bd=1, padx=10, pady=5, cursor="hand2",
                  command=lambda: os.startfile(OUTBOX_DIR)).pack(side="right", expand=True, fill="x", padx=(4, 0))

    def open_browser(self):
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{actual_port}")

if __name__ == "__main__":
    if "--no-gui" in sys.argv or "--headless" in sys.argv:
        start_server()
    else:
        root = tk.Tk()
        app = TransferTrayApp(root)
        root.mainloop()
