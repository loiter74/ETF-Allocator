"""
start.py — 一键启动：清理端口 + FastAPI 后端 + Vite 前端。
双击 start.bat 或在终端运行 python start.py。
"""
import subprocess, sys, time, os, webbrowser, socket
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ── 环境：确保 node/npm 在 PATH 中 ──
NODE_PATH = Path(r"C:\Program Files\nodejs")
if str(NODE_PATH) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = str(NODE_PATH) + os.pathsep + os.environ.get("PATH", "")
# npm 在 Windows 上需要 .cmd 后缀
NPM_CMD = "npm.cmd" if sys.platform == "win32" else "npm"

# ── 1. 清理旧进程 ──
def kill_on_port(port: int):
    """Windows: kill ALL processes listening on given port."""
    try:
        import subprocess as sp
        # 使用更宽泛的匹配，找到所有占用端口的进程
        result = sp.run(
            f'netstat -ano | findstr ":{port}"',
            shell=True, capture_output=True, text=True
        )
        killed_pids = set()
        for line in result.stdout.strip().split('\n'):
            parts = line.strip().split()
            if len(parts) >= 5 and 'LISTENING' in line:
                pid = parts[-1]
                if pid not in killed_pids and pid != '0':
                    sp.run(f'taskkill //F //PID {pid}', shell=True,
                           capture_output=True, stderr=subprocess.DEVNULL)
                    killed_pids.add(pid)
    except Exception:
        pass

def is_port_free(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('127.0.0.1', port))
        s.close()
        return True
    except OSError:
        return False

for port in (8000, 5173):
    if not is_port_free(port):
        print(f"  Port {port} in use — cleaning up...")
        kill_on_port(port)
        time.sleep(0.5)
        # 二次确认
        if not is_port_free(port):
            print(f"  WARNING: Port {port} still in use, waiting...")
            time.sleep(2)
            kill_on_port(port)

# ── 2. 启动后端 ──
print("Starting API server (port 8000)...")
api = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "src.api.server:app",
     "--host", "127.0.0.1", "--port", "8000"],
    cwd=str(ROOT),
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    bufsize=1, universal_newlines=True,
)

# ── 3. 等待后端就绪 ──
print("Waiting for API...", end="", flush=True)
for i in range(15):
    if not is_port_free(8000):
        break
    time.sleep(1)
    print(".", end="", flush=True)
print(" ready!")

# ── 4. 启动前端 ──
print("Starting frontend (port 5173, may take 10-30s on first run)...")
print("  [Tip] First launch is slow due to dependency optimization.", flush=True)
if sys.platform == "win32":
    # 使用绝对路径避免%~dp0解析问题
    NPM_FULL_PATH = str(NODE_PATH / NPM_CMD)
    ui = subprocess.Popen(
        f'"{NPM_FULL_PATH}" run dev',
        cwd=str(ROOT / "dashboard"),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        bufsize=1, universal_newlines=True,
        shell=True,
        encoding='utf-8',
        errors='replace',  # 遇到无法解码的字符时替换而不是报错
    )
else:
    ui = subprocess.Popen(
        [NPM_CMD, "run", "dev"],
        cwd=str(ROOT / "dashboard"),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        bufsize=1, universal_newlines=True,
        encoding='utf-8',
        errors='replace',
    )

# 等前端就绪，同时回显 Vite 关键日志
print("Waiting for frontend...", end="", flush=True)
for i in range(60):
    line = ui.stdout.readline() if ui.poll() is None else ""
    if "ready in" in line or "Local:" in line:
        print(f"\n  [Vite] {line.strip()}")
        if "ready in" in line:
            break
    if i % 5 == 0:
        print(".", end="", flush=True)
    if ui.poll() is not None:
        print("\n  [ERROR] Vite failed to start!")
        sys.exit(1)
print(" ready!")

# ── 5. 打开浏览器 ──
time.sleep(3)
webbrowser.open("http://localhost:5173")

print("=" * 48)
print("  ETF Allocator — Ready!")
print(f"  Dashboard: http://localhost:5173")
print(f"  API Docs:  http://localhost:8000/docs")
print("  Press Ctrl+C to stop both." )
print("=" * 48)
sys.stdout.flush()

# ── 6. 日志循环 ──
try:
    while True:
        for proc, label in [(api, "[API]"), (ui, "[UI]")]:
            if proc.poll() is not None:
                print(f"{label} process exited (code {proc.returncode})")
                # 任一进程退出 → 终止另一个 → 退出
                api.terminate()
                ui.terminate()
                sys.exit(1)
            line = proc.stdout.readline()
            if line:
                # 处理编码问题：替换无法在终端显示的字符
                safe_line = line.rstrip().encode('utf-8', errors='replace').decode('utf-8')
                try:
                    print(f"{label} {safe_line}", flush=True)
                except UnicodeEncodeError:
                    # 如果终端无法显示，使用ASCII安全模式
                    print(f"{label} {safe_line.encode('ascii', errors='replace').decode('ascii')}", flush=True)
except KeyboardInterrupt:
    print("\nShutting down...")
    api.terminate()
    ui.terminate()
    sys.exit(0)
