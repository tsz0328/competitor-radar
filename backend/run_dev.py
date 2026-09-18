"""本地开发入口：让热重载与 Playwright 渲染在 Windows 上共存。

为什么不用 uvicorn 自带的 reload：
- 直接 `uvicorn.Server(config).run()`：**不会启动重载器**（重载只在顶层 `uvicorn.run()`
  里启动），于是 `reload=True` 形同虚设——改代码永不加载，接口一直 404/405。
- 改用 `uvicorn.run(..., reload=True, loop=ProactorEventLoop)`：重载器会把**已绑定的 socket**
  传给子进程，而在 Windows + ProactorEventLoop 下子进程把该 socket 注册进 IOCP 会失败
  （OSError WinError 87），**热重载后服务无法再接收请求**（连接一直挂起）。

因此这里自己做一个极简「父进程看门 + 子进程服务」的热重载：
- 父进程用 watchfiles 监听 app 目录，文件一变就重启子进程；
- 子进程独立绑定端口、使用 ProactorEventLoop，Playwright 渲染不受影响，
  也不存在 socket 继承问题。

用法（backend 目录下）：
    python run_dev.py
端口可用环境变量 PORT 覆盖（默认 8000）。
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import uvicorn
from uvicorn.config import Config

# ProactorEventLoop 仅 Windows 存在；其他平台沿用 uvicorn 的 auto 策略
LOOP = "asyncio:ProactorEventLoop" if sys.platform == "win32" else "auto"

BACKEND_DIR = Path(__file__).resolve().parent
APP_DIR = BACKEND_DIR / "app"

# 子进程用它区分"我是被父进程拉起来的服务工作进程"
_WORKER_FLAG = "--serve"


def _serve() -> None:
    """子进程：直接起服务（自己绑端口、Proactor 事件循环、不再带重载）。"""
    uvicorn.Server(
        Config(
            "app.main:app",
            loop=LOOP,
            host="127.0.0.1",
            port=int(os.getenv("PORT", "8000")),
        )
    ).run()


def _spawn() -> subprocess.Popen:
    """拉起一个服务子进程（继承当前控制台，日志照常输出）。"""
    return subprocess.Popen([sys.executable, str(Path(__file__).resolve()), _WORKER_FLAG])


def _stop(child: subprocess.Popen) -> None:
    if child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


def main() -> None:
    if _WORKER_FLAG in sys.argv:
        _serve()
        return

    from watchfiles import watch

    child = _spawn()
    # 子进程若因端口占用等启动失败，直接报出来退出，别让父进程空等
    time.sleep(1.5)
    if child.poll() is not None:
        print("[run_dev] worker failed to start (check if port 8000 is in use)", flush=True)
        return

    try:
        for changes in watch(str(APP_DIR)):
            names = ", ".join(sorted({Path(path).name for _, path in changes}))
            print(f"[run_dev] change detected ({names}), reloading ...", flush=True)
            _stop(child)
            time.sleep(1.0)  # 给端口一点释放时间，避免 WinError 10048
            child = _spawn()
    except KeyboardInterrupt:
        pass
    finally:
        _stop(child)


if __name__ == "__main__":
    main()
