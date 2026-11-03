# 阿里云 Linux 部署环境与命令

> 适用：Alibaba Cloud Linux 2 / 3（及兼容的 CentOS / Anolis）部署 **traesolo**（足球纯竞技量化分析工具）。  
> 推荐方式：**主机只装 Docker + Docker Compose**，业务（前端 Nginx、FastAPI、MySQL、Redis、RQ Worker）全部走 `docker-compose.yml`。  
> **声明**：本工具仅供学习、研究与数据分析；生产请改默认密码并限制安全组。

---

## 1. 需要安装什么？

### 1.1 推荐：Docker 部署（主机环境最少）

| 组件 | 是否必须 | 版本建议 | 说明 |
|------|----------|----------|------|
| Git | 必须 | 任意近期版 | 拉取代码 |
| Docker Engine | 必须 | ≥ 24 | 跑容器 |
| Docker Compose | 必须 | Plugin v2（`docker compose`）或独立 ≥ 2.20 | 编排 |
| 防火墙 / 安全组 | 必须 | — | 放行 80（及按需 443/8000） |
| Node.js / Python / MySQL / Redis / Nginx | **不必装在主机** | — | 镜像内已有 |

`docker-compose.yml` 会起 5 个服务：

| 服务 | 容器端口映射 | 作用 |
|------|--------------|------|
| frontend | 80 → 80 | Vue 静态 + `/api` 反代 |
| model-api | 8000 → 8000 | FastAPI |
| mysql | 3306 → 3306 | 业务库 |
| redis | 6379 → 6379 | Token / 缓存 / RQ |
| rq-worker | 无对外端口 | 异步任务 |

### 1.2 可选：裸机部署（不用 Docker）

主机需额外安装：

| 组件 | 版本 | 用途 |
|------|------|------|
| Python | ≥ 3.12 | 后端（与 Dockerfile / numpy 2.5 一致） |
| Node.js | ≥ 18 | 仅构建前端（生产可只留 Nginx 托管 `dist`） |
| Nginx | 任意稳定版 | 静态站 + 反代 |
| MySQL | 8.0 | 数据库 |
| Redis | 7.x | 缓存（可关，功能降级） |
| gcc / g++ / make | — | 编译部分 Python 依赖 |

下文 **第 3 节为 Docker 推荐路径**；第 4 节为裸机补充。

---

## 2. 云侧准备（控制台）

1. ECS：建议 ≥ 2 核 4G（训练/采集更吃内存，生产建议 4 核 8G+）。  
2. 系统盘：≥ 40GB（镜像 + MySQL 数据）。  
3. **安全组入方向**（按需收紧源 IP）：

| 端口 | 用途 |
|------|------|
| 22 | SSH |
| 80 | 前端（必开） |
| 443 | HTTPS（若已配证书） |
| 8000 | 直连 API（可不对公网开，走 80 反代即可） |
| 3306 / 6379 | **不建议对公网开放** |

4. 若用域名：解析 A 记录到 ECS 公网 IP。

---

## 3. Docker 一键部署（推荐命令）

以下以 **Alibaba Cloud Linux 3**（`dnf`）为主；Cloud Linux 2 把 `dnf` 换成 `yum` 即可。

### 3.1 更新系统与基础工具

```bash
sudo dnf -y update
sudo dnf -y install git curl wget ca-certificates yum-utils
```

Cloud Linux 2：

```bash
sudo yum -y update
sudo yum -y install git curl wget ca-certificates yum-utils
```

### 3.2 安装 Docker

```bash
# 官方便捷脚本（通用；生产也可改用阿里云 Docker 镜像源文档中的 yum 源）
curl -fsSL https://get.docker.com | sudo sh

sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# 重新登录 SSH 后 docker 可不加 sudo
docker version
```

若 `get.docker.com` 较慢，可用阿里云文档中的 Docker CE 源安装（以控制台当前文档为准），核心仍是：`docker` 服务启动成功。

### 3.3 安装 Docker Compose Plugin

新版 Docker 一般自带 Compose 插件，验证：

```bash
docker compose version
```

若无插件，可安装独立二进制（示例）：

```bash
COMPOSE_VERSION=v2.29.7
sudo curl -L "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
docker-compose version
```

下文命令两种写法等价：

- `docker compose ...`（插件）
- `docker-compose ...`（独立命令）

### 3.4 防火墙（firewalld，若已启用）

```bash
sudo systemctl enable --now firewalld
sudo firewall-cmd --permanent --add-service=http
# sudo firewall-cmd --permanent --add-service=https
# 一般不必对公网开 8000
sudo firewall-cmd --reload
```

同时务必在 **阿里云安全组** 放行对应端口。

### 3.5 拉取代码并启动

```bash
# 换成你的仓库地址
cd /opt
sudo mkdir -p /opt/traesolo
sudo chown $USER:$USER /opt/traesolo
git clone <YOUR_REPO_URL> /opt/traesolo
cd /opt/traesolo

# 生产务必改密码：编辑 docker-compose.yml 中 MYSQL_* 与 DATABASE_URL
# 或使用环境变量覆盖（推荐后续改成 .env，勿把真实密码提交 Git）

docker compose build
docker compose up -d
docker compose ps
```

### 3.6 验证

```bash
# 后端存活
curl -sS http://127.0.0.1:8000/api/v1/health/live

# 经前端 Nginx 反代
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1/

# 日志
docker compose logs -f model-api
```

浏览器访问：`http://<ECS公网IP>/`  
API 文档（若未关）：`http://<ECS公网IP>:8000/docs`（建议仅内网或加鉴权/关公网 8000）。

### 3.7 常用运维命令

```bash
cd /opt/traesolo

docker compose ps
docker compose logs -f --tail=200 model-api
docker compose logs -f --tail=200 frontend
docker compose restart model-api
docker compose down
docker compose up -d --build          # 代码更新后重建并启动
docker compose exec model-api bash    # 进后端容器（镜像含 bash 时）
```

### 3.8 生产注意（必做）

1. 修改 `docker-compose.yml` 默认账号密码：`root` / `football` / `football`。  
2. 安全组 **不要** 对 `0.0.0.0/0` 开放 3306、6379。  
3. 登录后立即改管理员默认口令（见 `DOC/功能分析.md` / 初始化说明）。  
4. 单机 `model-api` 保持 `--workers 1`（镜像已如此），避免调度/训练状态冲突。  
5. 可选：前面加 SLB + HTTPS 证书，ECS 只开 80/443。

---

## 4. 裸机部署时主机还需安装的命令（可选）

仅在不用 Docker 时执行。Cloud Linux 3 示例：

### 4.1 Python 3.12+（与 `requirements.txt` / Docker 一致）

`numpy==2.5.1` + `scipy==1.16.x` 需要 **Python ≥ 3.12**。  
**Alibaba Cloud Linux 2/3（al8）默认 yum/dnf 源通常没有 `python3.12` 包**，请用下方「源码安装」或 Miniconda，不要再执行 `dnf install python3.12`。

#### 方式 A：官方源码安装（推荐，裸机）

```bash
sudo dnf -y install gcc gcc-c++ make openssl-devel bzip2-devel libffi-devel \
  zlib-devel readline-devel sqlite-devel xz-devel tk-devel wget curl tar

cd /usr/local/src
sudo curl -O https://www.python.org/ftp/python/3.12.8/Python-3.12.8.tgz
# 若官方 FTP 慢，可换华为/清华镜像，例如：
# sudo curl -O https://mirrors.huaweicloud.com/python/3.12.8/Python-3.12.8.tgz

sudo tar xf Python-3.12.8.tgz
cd Python-3.12.8
sudo ./configure --enable-optimizations --prefix=/usr/local
sudo make -j"$(nproc)"
sudo make altinstall          # 不会覆盖系统 python3
/usr/local/bin/python3.12 -V
/usr/local/bin/python3.12 -m ensurepip --upgrade
```

#### 方式 B：Miniconda（省编译时间）

```bash
cd /tmp
curl -O https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh -b -p $HOME/miniconda3
source $HOME/miniconda3/bin/activate
conda create -y -n traesolo python=3.12
conda activate traesolo
```

后端目录（源码安装后用 `/usr/local/bin/python3.12`）：

```bash
cd /opt/traesolo/backend   # 按实际路径改
deactivate 2>/dev/null || true
rm -rf venv
/usr/local/bin/python3.12 -m venv venv
source venv/bin/activate
pip install -U pip
pip install -r requirements.txt
# 配置 DATABASE_URL / config.yaml 后：
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

### 4.2 Node.js 18+（构建前端）

```bash
# 示例：NodeSource 18（以 Node 官方/阿里云镜像文档为准）
curl -fsSL https://rpm.nodesource.com/setup_18.x | sudo bash -
sudo dnf -y install nodejs
node -v && npm -v

cd /opt/traesolo/frontend
npm install
npm run build
# 将 dist/ 交给 Nginx root
```

### 4.3 Nginx

```bash
sudo dnf -y install nginx
sudo systemctl enable --now nginx
# 参考 frontend/nginx.conf：静态 root + location /api/ 反代到 127.0.0.1:8000
```

### 4.4 MySQL 8

```bash
# 按阿里云 Linux 对应 MySQL 官方/社区源安装 mysql-server
sudo dnf -y install mysql-server   # 若仓库有；否则跟云厂商文档装 8.0
sudo systemctl enable --now mysqld
# 建库建用户后，设置：
# export DATABASE_URL='mysql+pymysql://user:pass@127.0.0.1:3306/football_analytics'
```

### 4.5 Redis

```bash
sudo dnf -y install redis
sudo systemctl enable --now redis
# 对应 config / 环境变量 REDIS_URL=redis://127.0.0.1:6379/0
```

---

## 5. 环境变量速查（Docker / 裸机通用）

| 变量 | 含义 |
|------|------|
| `DATABASE_URL` | 如 `mysql+pymysql://football:密码@主机:3306/football_analytics` |
| `REDIS_URL` | 如 `redis://redis:6379/0`（Compose 内网主机名 `redis`） |
| `RUN_SCHEDULER` | `1` 开定时采集；多实例时仅一台为 `1` |
| `TRAESOLO_INITIAL_CRAWL` | 启动时是否全量采集，生产建议 `0` |
| `TRAESOLO_JOB_QUEUE_ENABLED` | RQ 队列，Compose 中 worker 为 `1` |
| `TRAESOLO_JSON_LOGS` | JSON 日志 |

Compose 内已写默认值；改密码后务必同步改 `DATABASE_URL`。

---

## 6. 一键脚本示例（可选拷贝到服务器）

将下列保存为 `/opt/install-traesolo-host.sh`，**仅安装主机 Docker 环境**（不含改密码）：

```bash
#!/usr/bin/env bash
set -euo pipefail

if command -v dnf >/dev/null 2>&1; then
  PKG=dnf
else
  PKG=yum
fi

sudo $PKG -y update
sudo $PKG -y install git curl wget ca-certificates

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi

sudo systemctl enable --now docker
sudo usermod -aG docker "$USER" || true

docker version
docker compose version || docker-compose version || true

echo "主机 Docker 环境就绪。请重新登录 SSH 后："
echo "  cd /opt/traesolo && docker compose up -d --build"
```

```bash
chmod +x /opt/install-traesolo-host.sh
sudo bash /opt/install-traesolo-host.sh
```

---

## 7. 验收清单

- [ ] `docker compose ps` 中 `mysql` healthy，`model-api` healthy，`frontend` Up  
- [ ] `curl` 本机 80 / health/live 成功  
- [ ] 安全组已放行 80，未对公网放行 3306/6379  
- [ ] 已修改 MySQL 与系统管理员默认密码  
- [ ] 浏览器能打开登录页并完成登录  

---

## 8. 相关文档

- `DOC/部署与工作流文档.md` — 通用部署与工作流  
- `docker-compose.yml` — 当前编排权威配置  
- `DOC/功能分析.md` — 端口、架构与运维注意  

*若与仓库代码冲突，以当前 `docker-compose.yml` / Dockerfile 为准。*
