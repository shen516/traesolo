# Windows 10 开发环境安装指南

> 适用于在新电脑上安装 Node.js、Python，以运行本仓库（足球纯竞技量化分析工具）。  
> 配套阅读：[部署与工作流文档.md](./部署与工作流文档.md)

---

## 目录

- [1. 版本要求（以本项目为准）](#1-版本要求以本项目为准)
- [2. 安装前准备](#2-安装前准备)
- [3. 安装 Node.js](#3-安装-nodejs)
- [4. 安装 Python](#4-安装-python)
- [5. 安装项目依赖并验证](#5-安装项目依赖并验证)
- [6. 日常启动命令](#6-日常启动命令)
- [7. 常见问题](#7-常见问题)

---

## 1. 版本要求（以本项目为准）

| 组件 | 最低要求 | 推荐版本 | 依据 |
|------|----------|----------|------|
| Node.js | >= 18.0 | **18 LTS** 或 20 LTS | `frontend/Dockerfile` 使用 `node:18`；`部署与工作流文档` 要求 >= 18 |
| npm | >= 9.0 | 随 Node 18+ 自带即可 | 前端包管理 |
| Python | >= 3.12 | **3.12**（与 Docker 一致）或 **3.13** | `backend/Dockerfile` 为 `python:3.12` |
| pip | >= 23.0 | 随官方安装包即可 | 安装 `backend/requirements.txt` |

说明：

- 不要使用 Node 16 及以下（Vite 5 不支持）。
- 不要使用 Python 3.10 及以下（与文档及依赖栈不一致）。
- 暂不建议安装尚未在依赖矩阵中验证的 Python 预览版。

---

## 2. 安装前准备

1. 使用管理员或具备安装软件权限的 Windows 10 账户。
2. 建议关闭可能拦截安装程序的安全软件临时拦截（安装完成后可再开启）。
3. 准备一个新的 **PowerShell** 或 **命令提示符（cmd）** 窗口，用于验证；**安装完成后务必新开终端**，否则可能读不到 PATH。
4. 确认磁盘有足够空间（Node + Python + 依赖建议预留 **2GB+**）。

可选检查：本机是否已装过旧版本。

```powershell
node -v
npm -v
python --version
py -0p
```

若命令不存在或版本过低，按下文重装/升级。

---

## 3. 安装 Node.js

### 3.1 推荐方式：官网 LTS 安装包

1. 打开官网：[https://nodejs.org/](https://nodejs.org/)
2. 下载 **LTS**（建议 18.x 或 20.x）的 Windows 安装包（`.msi`）。
3. 运行安装程序，建议勾选：
   - **Add to PATH**（加入 PATH）
   - **Automatically install the necessary tools** 可按需（一般前端开发不强制）
4. 一路 Next 完成安装。
5. **关闭并重新打开** PowerShell，执行：

```powershell
node -v
npm -v
```

期望示例：

```text
v18.20.x   （或 v20.x.x）
9.x.x 或更高
```

### 3.2 可选：用 nvm-windows 管理多版本

若同一台机器需要多个 Node 版本，可使用 [nvm-windows](https://github.com/coreybutler/nvm-windows)：

```powershell
# 安装 nvm-windows 后（新开终端）
nvm install 18.20.4
nvm use 18.20.4
node -v
```

本项目固定用 Node 18+ 即可，单版本官方安装包通常足够。

### 3.3 国内网络加速（可选）

若 `npm install` 较慢，可临时使用镜像：

```powershell
npm config set registry https://registry.npmmirror.com
```

恢复官方源：

```powershell
npm config set registry https://registry.npmjs.org
```

---

## 4. 安装 Python

### 4.1 推荐方式：官网安装包

1. 打开官网：[https://www.python.org/downloads/windows/](https://www.python.org/downloads/windows/)
2. 下载 **Python 3.11.x** 或 **3.13.x** 的 Windows installer（64-bit）。
3. 运行安装程序时，**务必勾选**：
   - **Add python.exe to PATH**
4. 选择 **Install Now**，或 Customize 时确认安装 **pip**、**py launcher**。
5. 安装结束后，**新开** PowerShell，执行：

```powershell
python --version
pip --version
py -0p
```

期望示例：

```text
Python 3.11.x   或  Python 3.13.x
pip 23.x 或更高
```

`py -0p` 可列出本机已注册的 Python 路径，便于确认用的是哪一套。

### 4.2 若 `python` 指向微软商店占位符

Windows 10 可能把 `python` 映射到应用商店。处理办法：

1. **设置 → 应用 → 应用执行别名**，关闭 **python.exe** / **python3.exe** 的应用安装程序别名；或
2. 使用启动器明确版本：

```powershell
py -3.11 --version
# 或
py -3.13 --version
```

后续创建虚拟环境时也用同一命令，例如：

```powershell
py -3.11 -m venv .venv
```

### 4.3 升级 pip（建议）

```powershell
python -m pip install --upgrade pip
```

国内镜像（可选）：

```powershell
python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 5. 安装项目依赖并验证

假设仓库已克隆到例如 `E:\fuye\traesolo`（按你本机路径替换）。

### 5.1 前端（Node）

```powershell
cd E:\fuye\traesolo\frontend
npm install
npm run dev
```

浏览器访问：`http://localhost:5173`  
能打开页面即表示 Node 环境可用。

生产构建自检：

```powershell
npm run build
```

### 5.2 后端（Python 虚拟环境）

**推荐始终使用虚拟环境**，避免污染系统 Python。

```powershell
cd E:\fuye\traesolo\backend

# 创建虚拟环境（目录名可用 .venv 或 venv，与团队习惯一致即可）
python -m venv .venv

# 激活（PowerShell）
.\.venv\Scripts\Activate.ps1

# 若提示无法加载脚本，见本文「7. 常见问题」
# cmd 下激活：
# .venv\Scripts\activate.bat

python -m pip install --upgrade pip
pip install -r requirements.txt

# 启动 API
python main.py
```

浏览器或 curl 访问：`http://localhost:8000/`  
能返回健康检查结果即表示 Python 环境可用。

也可用 uvicorn：

```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 5.3 一键自检清单

| 步骤 | 命令 | 通过标准 |
|------|------|----------|
| Node | `node -v` | >= v18 |
| npm | `npm -v` | >= 9 |
| Python | `python --version` | >= 3.11 |
| 前端依赖 | `cd frontend && npm install` | 无报错结束 |
| 后端依赖 | 激活 venv 后 `pip install -r requirements.txt` | 无报错结束 |
| 前端运行 | `npm run dev` | 5173 可访问 |
| 后端运行 | `python main.py` | 8000 可访问 |

---

## 6. 日常启动命令

每次开发建议开两个终端：

**终端 A — 前端**

```powershell
cd E:\fuye\traesolo\frontend
npm run dev
```

**终端 B — 后端**

```powershell
cd E:\fuye\traesolo\backend
.\.venv\Scripts\Activate.ps1
python main.py
```

更完整的部署、Docker、接口说明见 [部署与工作流文档.md](./部署与工作流文档.md)。

---

## 7. 常见问题

### 7.1 安装后 `node` / `python` 仍找不到

- 关闭所有旧终端，重新打开再试。
- 检查系统环境变量 PATH 是否包含例如：
  - `C:\Program Files\nodejs\`
  - `C:\Users\<用户名>\AppData\Local\Programs\Python\Python311\`
  - `...\Python311\Scripts\`
- 修改 PATH 后同样需要新开终端。

### 7.2 PowerShell 无法激活虚拟环境

报错类似「禁止运行脚本」时，对当前用户放开执行策略：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

或改用 cmd：

```cmd
cd E:\fuye\traesolo\backend
.venv\Scripts\activate.bat
```

### 7.3 `pip install` 失败（编译 / 网络）

- 先确认 Python 为 **64 位** 且版本在 **3.11–3.13**。
- 换镜像重试，例如：

```powershell
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

- 部分科学计算包需要 Microsoft C++ 生成工具时，按 pip 报错提示安装 [Build Tools for Visual Studio](https://visualstudio.microsoft.com/visual-cpp-build-tools/)，勾选「使用 C++ 的桌面开发」。

### 7.4 同时装了多个 Python，版本搞混

用启动器指定版本创建 venv：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
```

确认激活后提示符前有 `(.venv)`，且 `where python` 指向项目下的 `.venv\Scripts\python.exe`。

### 7.5 Node 版本过旧导致 Vite 报错

升级到 Node 18+ 后删除依赖重装：

```powershell
cd E:\fuye\traesolo\frontend
Remove-Item -Recurse -Force node_modules
Remove-Item -Force package-lock.json   # 可选；团队若锁定锁文件则勿删
npm install
```

### 7.6 与 Docker 环境对齐

若希望与容器完全一致：

- 前端镜像：`node:18`
- 后端镜像：`python:3.12`

本机可优先安装 **Node 18 LTS + Python 3.12**，减少「本机能跑、镜像里不行」的差异。

---

## 附录：本机建议安装结果示例

```text
OS:        Windows 10 (64-bit)
Node.js:   v18.20.x 或 v20.x.x
npm:       9.x+ / 10.x+
Python:    3.11.x 或 3.13.x
前端目录:  frontend\  （npm install 后存在 node_modules）
后端目录:  backend\.venv\  （pip install -r requirements.txt 完成）
```

安装完成后，按第 5、6 节启动前后端，即可在新 Windows 10 环境运行当前程序。
