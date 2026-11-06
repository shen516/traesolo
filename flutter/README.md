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
& "D:\programFiles\desiger\flutter\bin\flutter.bat" run
```

### BaseUrl

| 场景 | 命令 |
|------|------|
| Android 模拟器（默认） | 直接 `flutter run` → `http://10.0.2.2:8000/api/v1` |
| 真机（示例） | `flutter run --dart-define=API_BASE_URL=http://192.168.1.8:8000/api/v1` |

Debug 已允许 cleartext HTTP；生产请使用 HTTPS。

若 Android 编译报 `this and base files have different roots`（Pub 在 C:、工程在 E:），工程已在 `android/gradle.properties` 关闭 Kotlin 增量编译。仍失败时可执行 `flutter clean` 后再 `flutter build apk --debug`。

## 功能（MVP）

- 登录（PNG 验证码 hex 解码）
- 强制改密拦截
- 首页免责声明
- 赛事未赛 / 已赛列表
- 赛事详情 + 预测概率只读
- 个人中心 / 退出登录

运维能力（采集、训练、权限、调度）请使用 Web 前端。

## 设计文档

见 [docs/DESIGN.md](docs/DESIGN.md)。
