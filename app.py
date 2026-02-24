import streamlit as st
import os
import re
import json
import time
import base64
import shutil
import asyncio
import requests
import platform
import subprocess
import threading
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer
import psutil
import pandas as pd
import random

# ================= 页面配置 (伪装) =================
st.set_page_config(
    page_title="Server Status",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 隐藏所有 Streamlit 元素
hide_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
</style>
"""
st.markdown(hide_style, unsafe_allow_html=True)

# ================= 环境变量获取 (兼容 Posit) =================
# Posit Connect 必须通过 os.environ 读取 Vars，不支持 st.secrets
def get_env(key, default):
    return os.environ.get(key, default)

# 必填项：UUID
UUID = get_env('UUID', '7db878c0-b65f-45b1-aef0-41d217caf44b') 
# 选填项
UPLOAD_URL = get_env('UPLOAD_URL', '')
PROJECT_URL = get_env('PROJECT_URL', 'https://019c8f86-4230-b089-b30b-55d3243a2ea7.share.connect.posit.cloud') # 你的项目访问地址，用于自动唤醒
AUTO_ACCESS = str(get_env('AUTO_ACCESS', 'false')).lower() == 'true'
ARGO_DOMAIN = get_env('ARGO_DOMAIN', 'f.0000.ddns-ip.net')
ARGO_AUTH = get_env('ARGO_AUTH', 'eyJhIjoiZTcyODcwODc5MzRhYTUzN2MxNzZmYzg3NWNjOGUxZGQiLCJ0IjoiNDk3YThmNGItYTQ4YS00MjZiLWE5MGYtYmMwNjI0YWUyYjE3IiwicyI6Ik5QWFpLbU1TVm1ZSjhmNzBmUjZCKzc2cURDWFZRYjFmdldBMFZyc1VPc1U9In0=')
CFIP = get_env('CFIP', 'cf.008500.xyz') # 优选IP/域名
CFPORT = int(get_env('CFPORT', '443'))
NAME = get_env('NAME', 'Posit')
CHAT_ID = get_env('CHAT_ID', '')
BOT_TOKEN = get_env('BOT_TOKEN', '')

# 端口配置
INTERNAL_PORT = 3000 
ARGO_PORT = 8080

# 路径配置
FILE_PATH = os.path.join(os.getcwd(), '.cache')
if not os.path.exists(FILE_PATH):
    os.makedirs(FILE_PATH)

web_path = os.path.join(FILE_PATH, 'web')
bot_path = os.path.join(FILE_PATH, 'bot')
sub_path = os.path.join(FILE_PATH, 'sub.txt')
boot_log_path = os.path.join(FILE_PATH, 'boot.log')
config_path = os.path.join(FILE_PATH, 'config.json')

# ================= 后台核心逻辑 =================

def download_resource(filename, url):
    filepath = os.path.join(FILE_PATH, filename)
    if os.path.exists(filepath):
        return
    try:
        r = requests.get(url, stream=True)
        with open(filepath, 'wb') as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        os.chmod(filepath, 0o775)
    except:
        pass

def setup_core():
    # 1. 识别架构下载文件
    arch = 'arm' if 'arm' in platform.machine().lower() else 'amd'
    domain = f"{arch}64.ssss.nyc.mn"
    download_resource("web", f"https://{domain}/web")
    download_resource("bot", f"https://{domain}/2go")

    # 2. 生成 Config
    config = {
        "log": {"access": "/dev/null", "error": "/dev/null", "loglevel": "none"},
        "inbounds": [
            {
                "port": ARGO_PORT, "protocol": "vless",
                "settings": {"clients": [{"id": UUID, "flow": "xtls-rprx-vision"}], "decryption": "none",
                "fallbacks": [{"dest": 3001}, {"path": "/vmess-argo", "dest": 3003}, {"path": "/trojan-argo", "dest": 3004}]},
                "streamSettings": {"network": "tcp"}
            },
            {"port": 3001, "listen": "127.0.0.1", "protocol": "vless", "settings": {"clients": [{"id": UUID}], "decryption": "none"}, "streamSettings": {"network": "ws", "security": "none"}},
            {"port": 3003, "listen": "127.0.0.1", "protocol": "vmess", "settings": {"clients": [{"id": UUID, "alterId": 0}]}, "streamSettings": {"network": "ws", "wsSettings": {"path": "/vmess-argo"}}},
            {"port": 3004, "listen": "127.0.0.1", "protocol": "trojan", "settings": {"clients": [{"password": UUID}]}, "streamSettings": {"network": "ws", "security": "none", "wsSettings": {"path": "/trojan-argo"}}}
        ],
        "outbounds": [{"protocol": "freedom", "tag": "direct"}, {"protocol": "blackhole", "tag": "block"}]
    }
    with open(config_path, 'w') as f:
        json.dump(config, f)

async def run_services():
    setup_core()
    
    # 启动核心
    subprocess.Popen(f"{web_path} -c {config_path} >/dev/null 2>&1", shell=True)
    
    # 启动 Argo
    if ARGO_AUTH and ARGO_DOMAIN:
         # 固定隧道
         cmd = f"{bot_path} tunnel --edge-ip-version auto --no-autoupdate --protocol http2 run --token {ARGO_AUTH}"
    else:
         # 临时隧道
         cmd = f"{bot_path} tunnel --edge-ip-version auto --no-autoupdate --protocol http2 --logfile {boot_log_path} --loglevel info --url http://localhost:{ARGO_PORT}"
    
    subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # 等待并生成订阅
    await asyncio.sleep(5)
    await generate_sub()

async def generate_sub():
    domain = ARGO_DOMAIN
    
    # 如果是临时隧道，从日志抓取域名
    if not domain:
        for _ in range(10):
            if os.path.exists(boot_log_path):
                try:
                    with open(boot_log_path, 'r') as f:
                        log_content = f.read()
                        match = re.search(r'https?://([^ ]*trycloudflare\.com)', log_content)
                        if match:
                            domain = match.group(1)
                            break
                except: pass
            await asyncio.sleep(2)
            
    if domain:
        # 生成节点信息
        isp = "Posit"
        vmess_json = {"v": "2", "ps": f"{NAME}-{isp}", "add": CFIP, "port": CFPORT, "id": UUID, "aid": "0", "scy": "none", "net": "ws", "type": "none", "host": domain, "path": "/vmess-argo?ed=2560", "tls": "tls", "sni": domain, "alpn": "", "fp": "chrome"}
        vmess_str = base64.b64encode(json.dumps(vmess_json).encode('utf-8')).decode('utf-8')
        
        raw_list = f"vless://{UUID}@{CFIP}:{CFPORT}?encryption=none&security=tls&sni={domain}&fp=chrome&type=ws&host={domain}&path=%2Fvless-argo%3Fed%3D2560#{NAME}-{isp}\nvmess://{vmess_str}\ntrojan://{UUID}@{CFIP}:{CFPORT}?security=tls&sni={domain}&fp=chrome&type=ws&host={domain}&path=%2Ftrojan-argo%3Fed%3D2560#{NAME}-{isp}"
        
        # 写入文件供读取
        with open(sub_path, 'w') as f:
            f.write(raw_list)
            
        # 1. 打印到控制台日志 (Posit后台可见)
        print("-" * 20)
        print("DOMAIN:", domain)
        print("NODES GENERATED SUCCESS")
        print("-" * 20)
        
        # 2. TG 推送
        if BOT_TOKEN and CHAT_ID:
            try:
                requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={raw_list}")
            except: pass
            
        # 3. 自动保活注册
        if AUTO_ACCESS and PROJECT_URL:
            try:
                requests.post('https://keep.gvrander.eu.org/add-url', json={"url": PROJECT_URL})
            except: pass

# 简单 HTTP Server 用于内部保活
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"System OK")

def start_http_daemon():
    try:
        server = HTTPServer(('0.0.0.0', INTERNAL_PORT), SimpleHandler)
        server.serve_forever()
    except: pass

# ================= 持久化运行逻辑 =================

@st.cache_resource
def background_process():
    # 启动 HTTP 守护线程
    t1 = Thread(target=start_http_daemon, daemon=True)
    t1.start()
    
    # 启动核心业务
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_services())
    return True

# 启动后台服务
background_process()

# ================= 前端显示 (伪装 & 后门) =================

# 检查 URL 参数是否有密钥
# 只有访问 URL 加上 ?secret=你的UUID 时才显示真实信息
# 例如: https://your-app.posit.cloud/?secret=20e6e496-cf19-45c8-b883-14f5e11cd9f1
query_params = st.query_params
is_admin = query_params.get("secret") == UUID

if is_admin:
    st.success("Admin Access Granted")
    if st.button("查看节点信息"):
        if os.path.exists(sub_path):
            with open(sub_path, 'r') as f:
                st.code(f.read(), language="text")
        else:
            st.warning("正在生成中，请稍后刷新...")
            # 尝试从日志读取并显示，方便调试
            if os.path.exists(boot_log_path):
                with open(boot_log_path, 'r') as logf:
                    st.text("Argo Logs (Latest 500 chars):")
                    st.code(logf.read()[-500:])
else:
    # --- 伪装界面 ---
    st.title("Server Status Monitor")
    st.caption("Operational | Uptime: 99.9%")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("CPU Load", f"{random.randint(15, 35)}%", "-2%")
    with col2:
        st.metric("Memory", f"{random.randint(40, 60)}%", "+1%")
        
    st.subheader("Throughput Metrics")
    chart_data = pd.DataFrame({
        'Inbound': [random.randint(100, 500) for _ in range(20)],
        'Outbound': [random.randint(80, 450) for _ in range(20)]
    })
    st.line_chart(chart_data)
    
    # 自动刷新以保持连接
    st.markdown(
        """
        <script>
        setTimeout(function(){ window.location.reload(); }, 600000);
        </script>
        """, 
        unsafe_allow_html=True
    )
