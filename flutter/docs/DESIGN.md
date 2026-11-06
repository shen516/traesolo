# 欢哥竞球（TraeSolo）Flutter 设计方案

> 状态：Phase 2～3 + Phase 4 已落地；Phase 5 推送与篮球专项待做  






> 应用名：**欢哥竞球**（英文品牌 TraeSolo；当前足球，后续篮球）  
> 工程目录：仓库根 `flutter/`（勿与 Web 运维端混淆）  
> 路线图权威：`DOC/2026-11-06 欢哥竞球APP后续开发方案.md`

## 1. 目标与边界

| 纳入 App（P0–P2） | 留在 Web |
|---|---|
| 登录、验证码、强制改密、个人中心、关于页 | 定时任务 / 爬虫调度 |
| 首页关注流、赛事筛选（联赛/日期/关键词） | 用户 / 角色权限管理 |
| 赛事详情、预测只读增强、收藏赛事 | 联赛管理、模型训练触发 |
| 联赛积分榜 / 射手榜 / 球队详情 / 关注联赛 | 风控写操作、采集运维 |

原则：**App = 消费端；Web = 运营端**。

产品文案与 UI 不得构成投注建议，禁止赌博引导。

## 2. 技术选型

| 层 | 选型 |
|---|---|
| UI | Flutter + Material 3（深色主题对齐 Web） |
| 状态 | flutter_riverpod（Notifier） |
| 路由 | go_router（登录守卫 / 强制改密；自愿改密可进） |
| 网络 | dio → FastAPI `/api/v1` |
| Token | flutter_secure_storage |
| 图片 | cached_network_image |
| 用户缓存 | shared_preferences |

不在 App 内跑 ELO/泊松等模型；全部走后端接口。预测图用不引入 `fl_chart`，用自绘堆叠胜平负条。

## 3. 信息架构

```
Login → (must_change_password?) ChangePassword
     → Shell: [首页] [赛事] [数据] [竞彩] [我的]
                  ↓         ↓        ↓
            MatchDetail   数据榜   在赛/历史只读
                  ↓
            TeamDetail / 模拟推演
     → /about（关于与免责声明）
```

## 4. 路线图

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 1 | 登录 + 赛事列表/详情 + 个人中心 | 完成 |
| Phase 2 | 数据/关注/筛选/预测面板/关于 | 完成 |
| Phase 3.1～3.2 | 单场模拟推演 + 本场历史 | 完成 |
| Phase 3.3 | λ 敏感性扫描（表格 + 胜平负条） | 完成 |
| Phase 3.4 | 竞彩只读（在赛/历史） | 完成 |
| Phase 3.5 | 赔率快照只读（权益门控） | 完成 |
| Phase 4.1 | 赛事/竞彩下拉刷新 + 分页加载更多 | 完成 |
| Phase 4.2 | `TeamLogo` + `/static/` 解析 + 列表/详情接入 | 完成 |
| Phase 4.4 | 深链 `huange://open/match/{id}` → `/match/:id` | 完成 |
| Phase 4.5 / 4.7 | `APP_ENV`/`API_BASE_URL` dart-define；release 禁 cleartext + 签名/混淆 | 完成 |
| Phase 4.6 | CI `flutter analyze` + `flutter test` | 完成 |
| Phase 4.8 | Semantics、字号缩放钳制、底栏 tooltip | 完成 |
| Phase 4.3 | 最近赛事详情本地 JSON 缓存（LRU 20 / TTL 24h） | 完成 |
| Phase 5 / B | 推送、篮球 | 待做 |
