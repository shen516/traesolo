# 500.com 与 ESPN 数据源能力梳理

> 目的：对照当前代码实现，归纳 **500.com / ESPN 各自能提供什么、联赛覆盖差异、对后续开发方向的影响**。  
> 基准：仓库代码（`real_team_crawler.py`、`crawler_service.py`、`five00_fenxi_crawler.py`、`injury_crawler_service.py`、`live_500_crawler.py`、`real_crawler.py`、`league_crawler.py`、`media_crawler.py`）及采集 Skill。  
> 整理日期：2026-09-07  
> **声明**：赔率等字段仅作竞技分析与风控展示，不构成投注建议。

---

## 1. 总体策略（当前实现）

系统采用 **「500 主骨架 + ESPN 富化/兜底」** 的分域双源，而不是二选一。

| 域 | 主源 | 辅源 / 兜底 |
|----|------|-------------|
| 联赛目录 | **500** `liansai.500.com` | — |
| 赛程骨架 / 赛果 / `fixture_id` | **500** 轮次接口 | 空结果且有映射时 → ESPN scoreboard |
| 球队名单（中文名） | **500** 积分榜/联赛页 | ESPN 补 `espn_id`、队徽 |
| 阵容名单 | **500** 球队页 | — |
| 积分榜 | **500** | ESPN standings |
| 球员赛季统计 | **ESPN** roster | 500 阵容页聚合 |
| 射手榜 | **ESPN** statistics | 阵容进球聚合 |
| 逐场射门 / 球员 boxscore | **ESPN** summary | 500 fenxi（球队级射门/射正） |
| 伤病 | **ESPN** injuries | — |
| Live 比分回写 | **Live500** | — |
| 竞彩赔率 / 让球 | **trade.500.com** | — |
| 场馆 / `process_id` | ESPN enrich | 500 赛程本身通常无 venue |
| 气象环境 | Open-Meteo（第三方） | 非 500/ESPN |

重点联赛（默认）：`EPL / LALIGA / BUNDES / SERIEA / LIGUE1 / UCL / UEL`。  
Skill 明确结论：**纯 500、无 ESPN 映射的联赛通常拿不到可靠射门/伤病，不宜默认进入重点 xG 训练。**

---

## 2. 数据能力对照表

### 2.1 可由 500.com 获取的数据

| 能力 | 入口 / 实现 | 写入 / 用途 | 说明 |
|------|-------------|-------------|------|
| 联赛目录（全球大量联赛） | `LeagueCrawler` → `liansai.500.com` | `leagues`（大量 `LS*`） | 库内联赛规模可达千级，远超 ESPN 映射集 |
| 赛程 / 赛果骨架 | `RealTeamCrawler._crawl_500_fixtures` | `matches` + **`fixture_id`** | 主用；含轮次、比分、状态 |
| 中文队名 / 球队名单 | `_crawl_500` | `teams` | 中文名优先保留 |
| 阵容名单 | `crawl_squads` → 球队页 / teamlineup | `players` | 依赖 500 球队 ID |
| 积分榜 | `_crawl_500_standings` | `standings` | 有 `source_url` 时主用 |
| 球队级射门/射正（第二源） | `Five00FenxiCrawler`（`odds.500.com/fenxi`） | `match_team_stats`（`source=500_fenxi`） | 需有 `fixture_id`；无球员行 |
| Live 比分回写 | `Live500MatchCrawler` → `live.500.com` | 更新已有场次状态/比分 | 轻量；重点联赛定向 |
| 竞彩列表赔率 / 让球 | `RealMatchCrawler` → `trade.500.com/jczq` | `odds_*`、`handicap`、`odds_snapshots` | 分析用，非建议 |
| 队徽 / 球员头像（部分） | `MediaCrawler` 500 静态图 | `static/media` | 有源 ID 时可下 |

**500 侧关键不提供（或未接入）：**

- ESPN `event_id` / 球员级逐场 boxscore（射门、助攻、犯规、出场分钟等完整行）
- 伤病名单
- 官方英文队徽体系（有自有图，但与 ESPN `espn_id` 体系分离）
- 可靠的联盟级射手榜 API（当前射手榜走 ESPN）

### 2.2 可由 ESPN 获取的数据

| 能力 | API / 实现 | 写入 / 用途 | 说明 |
|------|------------|-------------|------|
| 赛程兜底 | `…/soccer/{code}/scoreboard` | `matches` | 无 500 URL，或 500 空结果时 |
| 场馆 / `process_id` / 完赛比分 enrich | scoreboard 轻量合并 | 补空字段 | **永不覆盖** `fixture_id` |
| 球队英文名 / `espn_id` / 队徽 | `…/teams` | `teams.espn_id`、logo | 叠在 500 名单上 |
| 积分榜兜底 | `…/standings` | `standings` | 500 空时 |
| 射手榜 | `…/statistics`（goalsLeaders） | `top_scorers` | 优先 |
| 球员赛季统计 | `…/teams/{id}/roster` | `players` 聚合字段 | 优先；失败回退 500 |
| **逐场球员/球队统计** | `…/summary?event=` | `match_player_stats`、`match_team_stats` | **xG 训练主原料** |
| 伤病 | `…/injuries` | `risk_alerts(type=injury)` | 仅重点且在 `ESPN_LEAGUE_MAP` 内 |
| 联赛/队徽 CDN | espncdn | 媒体 | 与 FD crest 互补 |

**ESPN 侧基本不提供（或未接入）：**

- 中文队名 / 中文联赛目录全量
- `fixture_id`（500 场次主键；fenxi 依赖它）
- 竞彩让球与赔率盘口
- Live500 同构的中文即时比分页

### 2.3 第三方（非 500 / ESPN）

| 能力 | 来源 | 说明 |
|------|------|------|
| 天气 / 气温 / 草坪粗估 | Open-Meteo | `crawl_environment`；依赖场馆坐标等 |

---

## 3. 联赛覆盖对照（代码硬编码映射）

定义位置：`backend/services/real_team_crawler.py`

### 3.1 规范联赛 ↔ 双源映射一览

| 规范 ID | 名称 | 500 URL（`CANONICAL_FIVE00_URL`） | ESPN code（`ESPN_LEAGUE_MAP`） | 默认重点 | 能力结论 |
|---------|------|----------------------------------|-------------------------------|----------|----------|
| EPL | 英超 | ✅ zuqiu-19906 | eng.1 | ✅ | 双源完整 |
| LALIGA | 西甲 | ✅ zuqiu-19947 | esp.1 | ✅ | 双源完整 |
| BUNDES | 德甲 | ✅ zuqiu-19951 | ger.1 | ✅ | 双源完整 |
| SERIEA | 意甲 | ✅ zuqiu-19826 | ita.1 | ✅ | 双源完整 |
| LIGUE1 | 法甲 | ✅ zuqiu-19835 | fra.1 | ✅ | 双源完整 |
| UCL | 欧冠 | ✅ zuqiu-19943 | uefa.champions | ✅ | 双源；资格赛统计策略特殊 |
| UEL | 欧联 | ✅ zuqiu-20000 | uefa.europa | ✅ | 双源；P3 已纳入重点 |
| WC | 世界杯 | ✅ zuqiu-19476 | fifa.world | ❌（SLA 软配额） | 双源；非默认重点训 |
| MLS | 美职联 | ✅ zuqiu-19471 | usa.1 | ❌（进 `extended_leagues`） | P2 扩展双源 |
| BRA | 巴甲 | ✅ zuqiu-19498 | bra.1 | ❌（extended） | P2 |
| SWE | 瑞典超 | ✅ zuqiu-19501 | swe.1 | ❌（extended） | P2 |
| FIN | 芬兰超 | ✅ zuqiu-19506 | fin.1 | ❌（extended） | P2 |
| NOR | 挪威超 | ✅ zuqiu-19507 | nor.1 | ❌（P3 双源） | 已补 500；`get_p3_dual_leagues` |
| EC | 欧洲杯 | ❌ 无硬编码 500 URL | uefa.euro | ❌ | **仅 ESPN**；`init_db` 默认未启用 |
| K1 | 韩职 | ✅ zuqiu-19554 | kor.1 | ❌（P3 双源） | ESPN+500 已映射 |
| CA / AFC | 美洲杯 / 亚洲杯 | ❌ | ❌ | ❌ | 仅占位；默认未启用 |

`FIVE00_TO_CANONICAL` 把部分历史 `LS*`（如 `LS9124`→西甲、`LS9117`→德甲）归并到上表规范 ID，避免同一联赛两套球队。

### 3.2 集合关系（硬编码层）

```text
CANONICAL_FIVE00_URL ∩ ESPN_LEAGUE_MAP
  = EPL, LALIGA, BUNDES, SERIEA, LIGUE1, UCL, UEL, WC, MLS, BRA, SWE, FIN, NOR, K1

仅 ESPN（有映射、无规范 500 URL）
  = EC

仅 500（有规范 500 URL、无 ESPN）
  = （空集）  ← 规范深度接入联赛全部也有 ESPN
```

---

## 4. 「500 有、ESPN 无」联赛分析

### 4.1 硬编码深度映射层

在 `CANONICAL_FIVE00_URL` / `ESPN_LEAGUE_MAP` 这一层：

- **不存在**「有规范 500 URL、却完全没有 ESPN code」的联赛。
- 开发上若只扩展「已有 500 URL 的规范联赛」，xG / 伤病路径在映射齐全时是通的。

### 4.2 目录层（真正的缺口）

`league_crawl` 从 **liansai.500.com** 拉全站联赛目录，入库后可达 **千级 `LS*` 联赛**（历史实测量级约 1400+）。  
其中 **仅上表约 12～14 个规范联赛** 进入 ESPN 深度管线。

因此：

| 类别 | 规模感 | ESPN 深度能力 | 典型后果 |
|------|--------|---------------|----------|
| 双源规范联赛 | ~14 | ✅ scoreboard / summary / injuries 等 | 可训 xG、可采伤病（含 P2/P3 扩展） |
| 500 目录其余联赛（`LS*` 及未映射规范项） | ~千级 | ❌ 无 `ESPN_LEAGUE_MAP` | 可有赛程/球队/阵容（若有 URL），**无球员级逐场统计、无伤病**；fenxi 仅球队级且依赖 `fixture_id` |
| 系统占位仍无双源（CA、AFC） | 少数 | ❌ | 不宜当重点 xG 联赛 |

**结论（回答「哪些联赛 500 有、ESPN 没有」）：**

1. **几乎全部** `liansai.500.com` 目录联赛（除上表已映射者）都属于「500 可采目录/赛程，ESPN 无深度覆盖」。  
2. ~~韩职 K1~~：P3 已补 `kor.1` + 500 URL；占位缺口代表转为 **CA / AFC**。  
3. 硬编码「深度 500」列表里 **没有** 单独缺 ESPN 的项；扩围时要警惕的是 **只挂了 500 URL、却忘了加 ESPN map** 的新联赛。

缺数联赛的预测场景策略见 [预测分析场景规则.md](./预测分析场景规则.md)（自动切泊松/ELO，详情页多场景对照）。

### 4.3 反向：ESPN 有、规范 500 无

| ID | 含义 | 现状 |
|----|------|------|
| EC | 欧洲杯 | 届次制，无常驻 500 赛季页；默认 `is_active=False` |

---

## 5. 按开发目标的数据可用性矩阵

| 目标能力 | 双源联赛（核心+扩展+NOR/K1） | 纯 500（海量 `LS*`） | 仅 ESPN（EC） |
|----------|---------------------------|----------------------|---------------|
| ELO / 泊松（完赛比分） | ✅ | ✅（有赛果即可） | ✅ |
| xG（球员/球队射门） | ✅ ESPN 主 + fenxi 辅 | ⚠️ 仅 fenxi 球队级，覆盖与质量弱 → **泊松主结论** | ✅ ESPN |
| 伤病风控 | ✅ | ❌ | ✅（若启用且有 map） |
| 中文 UI / 队名 | ✅ 500 主 | ✅ | ⚠️ 英文化，需别名 |
| 赔率时序 | ✅ 竞彩重叠场次 | 视是否进竞彩列表 | ❌ |
| Live 比分回写 | ✅ | 视 Live500 映射 | 弱 |

---

## 6. 对后续开发方向的建议（决策输入）

以下不直接改代码，供产品/研发定优先级时对照。

### 方向 A — 深耕双源联赛（推荐主线）

- 继续优先：`PRIORITY_LEAGUES`（五大 + UCL + UEL）。  
- 投入：射门覆盖 SLA、UEL/UCL 阶段策略、队名别名、伤病与环境补全、训练滞后追平。  
- 理由：两端数据最全，xG 与风控可闭环。

### 方向 B — 扩展「已有双源映射」的联赛（**P2 已落地**）

候选：`MLS / BRA / SWE / FIN`（`crawler.extended_leagues`；进 `get_stats_leagues` / SLA / 质量看板）。  
- 入口：`POST /crawler/extended/catchup`；质量页「扩展联赛补齐」。  
- **不**进默认 `priority_leagues` / `priority_train`，以免抢核心配额。

### 方向 C — 补齐「仅 ESPN」的 500 中文骨架（**P3 部分落地**）

- **NOR**：已补 `CANONICAL_FIVE00_URL` / `FIVE00_TO_CANONICAL`（`zuqiu-19507` / `LS19507`）→ 双源。  
- **EC**：仍 **ESPN-only**（届次制，无常驻赛季页）；赛程以 `uefa.euro` 为主。

### 方向 D — 纯 500 海量联赛（**P3 策略已标记**）

- 管线档 `five00_only`；预测 `meta_json.five00_only` / `data_policy`。  
- 主结论强制 **泊松**；`ensemble`/`xg` 标为不可用主结论。  
- **不**默认进重点 xG 训。

### 方向 E — 无双源占位联赛（**P3：K1 已双源**）

- **K1**：ESPN `kor.1` + 500 `zuqiu-19554` / `LS19554`；与 NOR 同属 `get_p3_dual_leagues()`。  
- CA / AFC 等仍待映射。

---

## 7. 一页纸速查

| 问题 | 答案 |
|------|------|
| 赛程主源是谁？ | **500**（有 URL 时）；否则 ESPN |
| xG 主源是谁？ | **ESPN** summary；500 fenxi 仅球队级兜底 |
| 伤病谁有？ | **仅 ESPN** |
| 赔率谁有？ | **仅 500 竞彩** |
| 「ESPN 有 500 规范 URL 无」？ | **仅 EC**（NOR/K1 已补） |
| 扩统计配额最省事？ | `extended_leagues` + `get_stats_leagues()`（MLS/BRA/SWE/FIN/NOR/K1） |
| 纯 500 联赛能否当 xG 重点？ | **不建议**；产品上泊松主结论 |

---

## 8. 相关代码索引

| 文件 | 内容 |
|------|------|
| `backend/services/real_team_crawler.py` | 映射表、`get_extended_leagues` / `get_stats_leagues` / `league_pipeline_tier` |
| `backend/services/crawler_service.py` | `run_extended_catchup` |
| `backend/api/crawler.py` | `POST /extended/catchup`、`/uel/catchup` |
| `backend/services/analysis_scenarios.py` | 纯 500 → 泊松策略 |
| `backend/services/five00_fenxi_crawler.py` | 500 单场球队射门第二源 |
| `backend/services/injury_crawler_service.py` | ESPN 伤病 |
| `.cursor/skills/traesolo-data-crawler/SKILL.md` | 采集规范摘要 |

---

*本文档随代码映射表变更应同步更新；新增规范联赛时请同时维护 500 URL 与 ESPN code，并明确是否进入 `priority_leagues` 或 `extended_leagues`。*
