# 欢哥竞球（TraeSolo）Flutter 客户端

球类竞技量化分析移动端（当前足球，后续篮球）。对接现有 FastAPI：`/api/v1`。

**产品边界**：仅供学习、研究与数据分析；不得构成投注建议，禁止赌博引导。

## 本机环境

| 工具 | 路径 |
|------|------|
| Flutter SDK | `D:\programFiles\desiger\flutter` |
| Android SDK | `D:\programFiles\desiger\AndroidSdk` |

可将 Flutter 加入 PATH，或始终使用绝对路径调用：

```powershell
& "D:\programFiles\desiger\flutter\bin\flutter.bat" --version
```

`android/local.properties` 应包含：

```properties
sdk.dir=D:\\programFiles\\desiger\\AndroidSdk
flutter.sdk=D:\\programFiles\\desiger\\flutter
```

## 启动后端

在仓库根目录按 [AGENTS.md](../AGENTS.md) 启动 FastAPI（默认 `http://localhost:8000`，API 前缀 `/api/v1`）。

## 运行 App

```powershell
cd e:\fuye\traesolo\flutter
& "D:\programFiles\desiger\flutter\bin\flutter.bat" pub get
& "D:\programFiles\desiger\flutter\bin\flutter.bat" run --dart-define=APP_ENV=dev --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1
```

### 环境与 BaseUrl

| 场景 | 命令要点 |
|------|----------|
| Android 模拟器 | `--dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1` |
| 真机局域网 | `--dart-define=API_BASE_URL=http://192.168.x.x:8000/api/v1` |
| 生产 release | `--release --dart-define=APP_ENV=prod --dart-define=API_BASE_URL=https://your.api/api/v1` |

- `APP_ENV`：`dev` / `staging` / `prod`（关于页展示）
- Debug 清单允许 cleartext HTTP；**main/release 默认 `usesCleartextTraffic=false`**，生产必须 HTTPS
- 正式签名：复制 `android/key.properties.example` → `android/key.properties` 后填写；未配置时 release 回退 debug 签名仅供联调

若 Android 编译报 `this and base files have different roots`（Pub 在 C:、工程在 E:），工程已在 `android/gradle.properties` 关闭 Kotlin 增量编译。仍失败时可执行 `flutter clean` 后再构建。

### 深链

自定义 Scheme：`huange://open/match/{id}` → App 内路由 `/match/:id`（需已登录）。

## 功能（Phase 1～4 基线）

- 登录（PNG 验证码 hex）/ 强制改密 / 个人中心 / 关于
- 首页关注流、赛事筛选与分页加载更多
- 赛事详情 + 预测只读 + 收藏 + 单场模拟 / λ 敏感性 / 赔率快照
- 数据：联赛积分榜 / 射手榜 / 球队详情
- 竞彩只读（在赛/历史）+ 分页
- 赛事详情离线缓存（最近 20 场 / 24h；无网回退）
- CI：`flutter analyze` + `flutter test`

运维能力（采集、训练、权限、调度）请使用 Web 前端。

## 设计文档

见 [docs/DESIGN.md](docs/DESIGN.md)；路线图见 `DOC/2026-11-06 欢哥竞球APP后续开发方案.md`。
