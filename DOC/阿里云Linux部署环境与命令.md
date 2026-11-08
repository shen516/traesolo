# 阿里云 Linux 部署环境与命令

> 适用：Alibaba Cloud Linux 2 / 3（及兼容的 CentOS / Anolis）部署 **traesolo**（足球纯竞技量化分析工具）。  
> **线上推荐（已有宿主机 MariaDB/Redis）**：`docker-compose.host.yml` + 根目录 `.env` + 宿主机 Nginx 托管 `frontend/dist`（路径示例 `/u01/app/traesolo`）。  
> **全容器备选**：`docker-compose.yml`（可加 `--profile bundled-db` 起内置 MySQL）。  
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

### 3.5 线上推荐：宿主机库 + `docker-compose.host.yml`

适用：MariaDB/MySQL、Redis 已在宿主机；后端用 Docker（`network_mode: host`）；前端用宿主机 Nginx 托管 `frontend/dist`。  
默认路径：`/u01/app/traesolo`（可改，全文路径一并替换）。

#### 3.5.1 首次部署

```bash
cd /u01/app/traesolo   # 或 git clone 到此目录

# 1) 停旧裸机 API，避免抢 8000（host 网络与宿主机共用端口）
sudo systemctl stop traesolo-api 2>/dev/null || true
sudo systemctl disable traesolo-api 2>/dev/null || true
ss -lntp | grep ':8000' || echo '8000 free'

# 2) 创建 .env（勿提交 Git）
cp .env.production.example .env
chmod 600 .env
# 编辑 .env，至少改：
#   ADMIN_PASSWORD=强密码（禁止 admin123；Compose 映射为 TRAESOLO_ADMIN_PASSWORD）
#   DATABASE_URL=mysql+pymysql://用户:密码@127.0.0.1:3306/实际库名
#   REDIS_URL=redis://127.0.0.1:6379/0
# 密码含 @ 等特殊字符须 URL 编码（@ → %40）

# 3) 确认库账号对「实际库名」有权限（库名不对会报 1044）
mysql -ufootball -p -h127.0.0.1 -e "USE 你的库名; SELECT DATABASE();"

# 4) 启动后端（model-api + rq-worker）
docker compose -f docker-compose.host.yml --env-file .env up -d --build
docker ps
docker logs --tail=80 football-model-api

# 5) 前端：构建 + 宿主机 Nginx（反代 127.0.0.1:8000，见 nginx.host-dist.conf）
cd frontend && npm ci && npm run build && cd ..
sudo cp frontend/nginx.host-dist.conf /etc/nginx/conf.d/traesolo.conf
# 或 sites-available/enabled 方式，见该 conf 头注释
sudo nginx -t && sudo systemctl reload nginx
```

#### 3.5.2 验证

```bash
curl -sS http://127.0.0.1:8000/api/v1/health/live
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1/api/v1/health/live
docker inspect football-model-api --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E 'DATABASE_URL|TRAESOLO_'
```

浏览器：`http://<ECS公网IP>/`。登录账号默认 `admin`，密码为 `.env` 中 `ADMIN_PASSWORD`。

#### 3.5.3 后续更新应用（日常发布）

| 变更类型 | 命令 |
|----------|------|
| 仅后端 Python 业务代码 | `git pull` → `docker compose -f docker-compose.host.yml --env-file .env restart model-api rq-worker` |
| `requirements.txt` / Dockerfile | `git pull` → `... up -d --build --force-recreate model-api rq-worker` |
| 仅改 `.env` | `... up -d --force-recreate model-api rq-worker`（必须 recreate，restart 不会重读环境变量） |
| 仅前端 | `cd frontend && npm ci && npm run build` → `sudo nginx -t && sudo systemctl reload nginx` |
| 前后端一起 | 先后端（按上表选 restart 或 build），再前端 build + reload nginx |

一键示例（依赖有变更时用 build；纯代码用 restart）：

```bash
cd /u01/app/traesolo
git pull

# 依赖变更：
docker compose -f docker-compose.host.yml --env-file .env up -d --build --force-recreate model-api rq-worker

# 仅代码、依赖未变：
# docker compose -f docker-compose.host.yml --env-file .env restart model-api rq-worker

cd frontend && npm ci && npm run build && cd ..
sudo nginx -t && sudo systemctl reload nginx

docker ps
curl -sS http://127.0.0.1:8000/api/v1/health/live
docker logs --tail=40 football-model-api
```

说明：`docker-compose.host.yml` 将 `./backend` 挂到容器 `/app`，**业务 .py 改完需 restart 才会被 uvicorn 加载**；`pip` 依赖在镜像层，改 `requirements.txt` 必须 `--build`。

#### 3.5.4 常见故障

| 现象 | 处理 |
|------|------|
| `1044 Access denied ... to database 'xxx'` | `.env` 的 `DATABASE_URL` 库名与线上一致；`GRANT` 对应用户 |
| `TRAESOLO_ADMIN_PASSWORD` / 弱口令拒绝启动 | `.env` 设非 `admin123` 的 `ADMIN_PASSWORD` 后 `--force-recreate` |
| `address already in use ... 8000` | 停 `traesolo-api` 或其它占用进程：`ss -lntp \| grep 8000` |
| `No module named 'requests'` 等 | `requirements.txt` 已含依赖后 `--build` 重建镜像 |
| 验证码竖条 / 只有噪点无字符 | 同步最新 `api/auth.py`（点阵分行 + 无 TTF 时禁止 Pillow `load_default`）后 `restart model-api`；slim 镜像无系统字体属正常 |
| Nginx 反代不通 | 宿主机 Nginx 用 `127.0.0.1:8000`（`nginx.host-dist.conf`），不要用 `host.docker.internal` |

### 3.6 备选：全容器 `docker-compose.yml`

MySQL/Redis 也跑在 Compose 内时用此路径（可加 `--profile bundled-db`）。

```bash
cd /opt/traesolo   # 或你的仓库路径
cp .env.production.example .env && chmod 600 .env
# 编辑 DATABASE_URL / ADMIN_PASSWORD；bundled-db 时库主机名多为 mysql

docker compose --profile bundled-db --env-file .env up -d --build
docker compose ps
```

验证：

```bash
curl -sS http://127.0.0.1:8000/api/v1/health/live
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1/
docker compose logs -f --tail=200 model-api
```

浏览器访问：`http://<ECS公网IP>/`。

### 3.7 常用运维命令

**host 模式（线上推荐）：**

```bash
cd /u01/app/traesolo
docker compose -f docker-compose.host.yml --env-file .env ps
docker logs -f --tail=200 football-model-api
docker compose -f docker-compose.host.yml --env-file .env restart model-api
docker compose -f docker-compose.host.yml --env-file .env up -d --build --force-recreate model-api rq-worker
```

**全容器模式：**

```bash
cd /opt/traesolo
docker compose ps
docker compose logs -f --tail=200 model-api
docker compose restart model-api
docker compose up -d --build
```

### 3.8 生产注意（必做）

1. **必须有根目录 `.env`**（从 `.env.production.example` 复制），`chmod 600`；勿把真实密码提交 Git。  
2. `TRAESOLO_PRODUCTION=1` 时 `ADMIN_PASSWORD` 禁止为 `admin123`。  
3. `DATABASE_URL` 库名、账号与线上 MariaDB 一致；密码特殊字符做 URL 编码。  
4. 安全组 **不要** 对 `0.0.0.0/0` 开放 3306、6379。  
5. 单机 `model-api` 保持 `--workers 1`（镜像已如此），避免调度/训练状态冲突。  
6. 可选：前面加 SLB + HTTPS 证书，ECS 只开 80/443。

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

写入项目根 `.env`，由 `--env-file .env` 注入（host 模式必填，勿依赖空环境）。

| 变量 | 含义 |
|------|------|
| `DATABASE_URL` | 如 `mysql+pymysql://football:密码@127.0.0.1:3306/football`（**库名按线上实际**） |
| `REDIS_URL` | host 模式：`redis://127.0.0.1:6379/0`；全容器：`redis://redis:6379/0` |
| `TRAESOLO_PRODUCTION` | 生产设 `1` |
| `ADMIN_PASSWORD` | 生产管理员口令；Compose 映射为 `TRAESOLO_ADMIN_PASSWORD`（禁止 `admin123`） |
| `RUN_SCHEDULER` | `1` 开定时采集；多实例时仅一台为 `1` |
| `TRAESOLO_INITIAL_CRAWL` | 启动时是否全量采集，生产建议 `0` |
| `TRAESOLO_JOB_QUEUE_ENABLED` | RQ 队列，worker 为 `1` |
| `TRAESOLO_JSON_LOGS` | JSON 日志 |

改密码或库名后务必同步改 `DATABASE_URL`，并对容器 `--force-recreate`。

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
echo "  cd /u01/app/traesolo"
echo "  cp .env.production.example .env && chmod 600 .env   # 再编辑"
echo "  docker compose -f docker-compose.host.yml --env-file .env up -d --build"
```

```bash
chmod +x /opt/install-traesolo-host.sh
sudo bash /opt/install-traesolo-host.sh
```

---

## 7. 验收清单

**host 模式（推荐）：**

- [ ] 根目录存在 `.env`（`chmod 600`），`DATABASE_URL` / `ADMIN_PASSWORD` 已按线上填写  
- [ ] `docker ps` 中 `football-model-api`、`football-rq-worker` 为 Up（api 随后 healthy）  
- [ ] `curl http://127.0.0.1:8000/api/v1/health/live` 成功  
- [ ] 宿主机 Nginx 反代 `127.0.0.1:8000`，`/` 与 `/api/` 可访问  
- [ ] 安全组已放行 80，未对公网放行 3306/6379  
- [ ] 浏览器能打开登录页并完成登录；验证码为清晰字母数字  

**全容器模式：**

- [ ] `docker compose ps` 中相关服务 Up / healthy  
- [ ] `curl` 本机 80 / health/live 成功  

---

## 8. 相关文档

- `DOC/部署与工作流文档.md` — 通用部署与工作流  
- `docker-compose.host.yml` — **线上 host 网络编排（权威）**  
- `docker-compose.yml` — 全容器编排  
- `.env.production.example` — 生产环境变量模板  
- `frontend/nginx.host-dist.conf` — 宿主机 Nginx 站点示例  
- `DOC/功能分析.md` — 端口、架构与运维注意  

*若与仓库代码冲突，以当前 `docker-compose.host.yml` / `docker-compose.yml` / Dockerfile 为准。*
