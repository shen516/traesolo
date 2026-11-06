# 欢哥竞球（TraeSolo）Flutter 设计方案

> 状态：MVP 已脚手架（登录 + 赛事列表/详情预测只读）  
> 应用名：**欢哥竞球**（英文品牌 TraeSolo；当前足球，后续篮球）  
> 工程目录：仓库根 `flutter/`（勿与 Web 运维端混淆）

## 1. 目标与边界

| 纳入 App（P0–P1） | 留在 Web |
|---|---|
| 登录、验证码、强制改密、个人中心 | 定时任务 / 爬虫调度 |
| 首页、赛事未赛/已赛 | 用户 / 角色权限管理 |
| 赛事详情、预测结果只读展示 | 联赛管理、模型训练触发 |
| （规划）联赛积分榜 / 射手榜 / 模拟预测 | 风控写操作、采集运维 |

原则：**App = 消费端；Web = 运营端**。

产品文案与 UI 不得构成投注建议，禁止赌博引导。

## 2. 技术选型

| 层 | 选型 |
|---|---|
| UI | Flutter + Material 3（深色主题对齐 Web） |
| 状态 | flutter_riverpod |
| 路由 | go_router（含登录守卫 / 强制改密） |
| 网络 | dio → FastAPI `/api/v1` |
| Token | flutter_secure_storage |
| 用户缓存 | shared_preferences |

不在 App 内跑 ELO/泊松等模型；全部走后端接口。

## 3. 本地 SDK（本机）

- Flutter：`D:\programFiles\desiger\flutter`
- Android SDK：`D:\programFiles\desiger\AndroidSdk`
- 已写入 `android/local.properties`（勿提交密钥；该文件通常本地生成）

## 4. API 对接（已实现）

| 能力 | 路径 |
|---|---|
| 验证码 | `GET /auth/captcha`（hex PNG → `Image.memory`） |
| 登录 | `POST /auth/login` |
| 登出 | `POST /auth/logout` |
| 改密 | `POST /auth/change-password` |
| 未赛/已赛 | `GET /matches/upcoming`、`/matches/finished`（`view=summary`） |
| 详情 | `GET /matches/{id}` |
| 预测 | `GET /matches/{id}/prediction?recalculate=false` |

BaseUrl 默认：`http://10.0.2.2:8000/api/v1`（Android 模拟器）。  
真机：`--dart-define=API_BASE_URL=http://<局域网IP>:8000/api/v1`。

## 5. 信息架构

```
Login → (must_change_password?) ChangePassword
     → Shell: [首页] [赛事] [我的]
                  ↓
            MatchDetail（预测概率只读）
```

## 6. 路线图

| 阶段 | 内容 |
|---|---|
| Phase 1（当前） | 登录 + 赛事列表/详情 + 个人中心 |
| Phase 2 | 积分榜/射手榜、球队详情、模拟预测、图表 |
| Phase 3 | 竞彩只读、推送（需后端扩展）、深链 |
