# 欢哥竞球（TraeSolo）Flutter 设计方案

> 状态：Phase 2.1～2.4 已落地（数据 Tab + 关注流 + 球队详情 + 收藏）  
> 应用名：**欢哥竞球**（英文品牌 TraeSolo；当前足球，后续篮球）  
> 工程目录：仓库根 `flutter/`（勿与 Web 运维端混淆）  
> 路线图权威：`DOC/2026-11-06 欢哥竞球APP后续开发方案.md`

## 1. 目标与边界

| 纳入 App（P0–P2） | 留在 Web |
|---|---|
| 登录、验证码、强制改密、个人中心 | 定时任务 / 爬虫调度 |
| 首页关注流、赛事未赛/已赛 | 用户 / 角色权限管理 |
| 赛事详情、预测只读、收藏赛事 | 联赛管理、模型训练触发 |
| 联赛积分榜 / 射手榜 / 球队详情 / 关注联赛 | 风控写操作、采集运维 |

原则：**App = 消费端；Web = 运营端**。

产品文案与 UI 不得构成投注建议，禁止赌博引导。

## 2. 技术选型

| 层 | 选型 |
|---|---|
| UI | Flutter + Material 3（深色主题对齐 Web） |
| 状态 | flutter_riverpod（Notifier，禁用已移除的 StateProvider） |
| 路由 | go_router（含登录守卫 / 强制改密） |
| 网络 | dio → FastAPI `/api/v1` |
| Token | flutter_secure_storage |
| 图片 | cached_network_image |
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
| 联赛 | `GET /leagues/` |
| 积分榜 / 射手榜 | `GET /standings/league/{id}`、`/scorers/league/{id}` |
| 球队 | `GET /teams/{id}`、`/teams/league/{id}` |
| 关注 | `GET/POST/DELETE /follows/leagues*`、`GET /follows/summary` |
| 收藏赛事 | `GET/POST/DELETE /favorites/user/{id}/match*` |

BaseUrl 默认见 `AppConfig`；真机用 `--dart-define=API_BASE_URL=...`。

## 5. 信息架构

```
Login → (must_change_password?) ChangePassword
     → Shell: [首页] [赛事] [数据] [我的]
                  ↓              ↓
            MatchDetail     积分榜/射手榜
                  ↓              ↓
            TeamDetail ←———————┘
```

## 6. 路线图

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 1 | 登录 + 赛事列表/详情 + 个人中心 | 完成 |
| Phase 2.1～2.4 | 积分榜/射手/球队/关注/收藏 | 完成 |
| Phase 2.5～2.8 | 列表筛选增强、预测图表、关于页 | 待做 |
| Phase 3 | 模拟预测、竞彩只读 | 待做 |
| Phase 4+ | 工程化发布、推送、篮球 | 待做 |
