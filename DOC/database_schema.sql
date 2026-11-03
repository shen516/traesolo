-- ================================================
-- 足球纯竞技量化分析工具 5.0 职业版
-- 数据库建库建表脚本 (MySQL)
-- ================================================

-- 创建数据库
CREATE DATABASE IF NOT EXISTS football_analytics 
  DEFAULT CHARACTER SET utf8mb4 
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE football_analytics;

-- ================================================
-- 1. 联赛表 (leagues)
-- ================================================
CREATE TABLE IF NOT EXISTS leagues (
  id VARCHAR(20) PRIMARY KEY COMMENT '联赛ID',
  name VARCHAR(100) NOT NULL COMMENT '联赛名称',
  icon VARCHAR(50) COMMENT '联赛图标/国旗',
  region VARCHAR(50) COMMENT '所属地区',
  level INT DEFAULT 1 COMMENT '联赛等级(1-5)',
  avg_goals DECIMAL(4,2) DEFAULT 2.70 COMMENT '联赛场均进球数',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_league_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='联赛信息表';

-- 插入初始数据
INSERT INTO leagues (id, name, icon, region, level, avg_goals) VALUES
('EPL', '英超联赛', '🏴', '欧洲', 1, 2.85),
('LALIGA', '西甲联赛', '🇪🇸', '欧洲', 1, 2.50),
('BUNDES', '德甲联赛', '🇩🇪', '欧洲', 1, 3.10),
('SERIEA', '意甲联赛', '🇮🇹', '欧洲', 1, 2.60),
('LIGUE1', '法甲联赛', '🇫🇷', '欧洲', 1, 2.70),
('UCL', '欧冠联赛', '🏆', '欧洲', 1, 2.80),
('UEL', '欧联杯', '🥈', '欧洲', 2, 2.55),
('EFLCUP', '英联杯', '🏆', '欧洲', 3, 2.60),
('COPADEL', '国王杯', '🏆', '欧洲', 3, 2.50),
-- 国际赛事
('WC', '世界杯', '🌍', '国际', 1, 2.65),
('WCU23', 'U23世界杯', '🌍', '国际', 2, 2.80),
('EC', '欧洲杯', '🇪🇺', '欧洲', 1, 2.50),
('CA', '美洲杯', '🌎', '美洲', 1, 2.55),
('ACN', '非洲杯', '🌍', '非洲', 1, 2.40),
('AFC', '亚洲杯', '🌏', '亚洲', 1, 2.60),
('CONCACAF', '中北美金杯赛', '🌎', '中北美', 1, 2.50);

-- ================================================
-- 2. 球队表 (teams)
-- ================================================
CREATE TABLE IF NOT EXISTS teams (
  id VARCHAR(20) PRIMARY KEY COMMENT '球队ID',
  name VARCHAR(100) NOT NULL COMMENT '球队全称',
  short_name VARCHAR(20) NOT NULL COMMENT '球队简称',
  logo VARCHAR(255) COMMENT '球队logo URL或emoji',
  league_id VARCHAR(20) COMMENT '所属联赛ID',
  country VARCHAR(50) COMMENT '所属国家',
  elo_rating INT DEFAULT 1500 COMMENT 'ELO评级',
  attack_strength DECIMAL(4,3) DEFAULT 1.000 COMMENT '攻击强度',
  defense_strength DECIMAL(4,3) DEFAULT 1.000 COMMENT '防守强度',
  home_ground VARCHAR(100) COMMENT '主场球场',
  founded_year INT COMMENT '成立年份',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_team_league (league_id),
  INDEX idx_team_name (name),
  INDEX idx_elo_rating (elo_rating),
  CONSTRAINT fk_team_league FOREIGN KEY (league_id) REFERENCES leagues(id) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='球队信息表';

-- 插入初始数据
INSERT INTO teams (id, name, short_name, logo, league_id, country, elo_rating, attack_strength, defense_strength, home_ground) VALUES
('MCI', '曼彻斯特城', '曼城', '🔵', 'EPL', '英格兰', 2085, 1.350, 0.750, '伊蒂哈德球场'),
('ARS', '阿森纳', '阿森纳', '🔴', 'EPL', '英格兰', 2020, 1.200, 0.800, '酋长球场'),
('LIV', '利物浦', '利物浦', '🔴', 'EPL', '英格兰', 2050, 1.280, 0.850, '安菲尔德球场'),
('CHE', '切尔西', '切尔西', '🔵', 'EPL', '英格兰', 1880, 1.000, 0.950, '斯坦福桥球场'),
('MUN', '曼彻斯特联', '曼联', '🔴', 'EPL', '英格兰', 1860, 0.950, 1.000, '老特拉福德球场'),
('TOT', '托特纳姆热刺', '热刺', '⚪', 'EPL', '英格兰', 1900, 1.100, 0.920, '热刺球场'),
('RMA', '皇家马德里', '皇马', '⚪', 'LALIGA', '西班牙', 2100, 1.380, 0.720, '伯纳乌球场'),
('BAR', '巴塞罗那', '巴萨', '🔵', 'LALIGA', '西班牙', 2030, 1.300, 0.780, '诺坎普球场'),
('ATM', '马德里竞技', '马竞', '🔴', 'LALIGA', '西班牙', 1950, 1.100, 0.850, '万达大都会球场'),
('BAY', '拜仁慕尼黑', '拜仁', '🔴', 'BUNDES', '德国', 2090, 1.420, 0.700, '安联球场'),
('DOR', '多特蒙德', '多特', '🟡', 'BUNDES', '德国', 1880, 1.150, 0.950, '信号伊杜纳公园球场'),
('JUV', '尤文图斯', '尤文', '⚪', 'SERIEA', '意大利', 1920, 1.050, 0.880, '安联球场'),
('INT', '国际米兰', '国米', '🔵', 'SERIEA', '意大利', 1960, 1.180, 0.820, '梅阿查球场'),
('MIL', 'AC米兰', '米兰', '🔴', 'SERIEA', '意大利', 1890, 1.080, 0.900, '圣西罗球场'),
('PSG', '巴黎圣日耳曼', '巴黎', '🔵', 'LIGUE1', '法国', 2000, 1.320, 0.800, '王子公园球场');

-- 世界杯国家队数据
INSERT INTO teams (id, name, short_name, logo, league_id, country, elo_rating, attack_strength, defense_strength, home_ground) VALUES
-- 南美强队
('BRA', '巴西国家队', '巴西', '🇧🇷', 'WC', '巴西', 2150, 1.400, 0.780, '马拉卡纳球场'),
('ARG', '阿根廷国家队', '阿根廷', '🇦🇷', 'WC', '阿根廷', 2120, 1.350, 0.800, '纪念碑球场'),
('URU', '乌拉圭国家队', '乌拉圭', '🇺🇾', 'WC', '乌拉圭', 1930, 1.100, 0.900, '百年纪念球场'),
('COL', '哥伦比亚国家队', '哥伦比亚', '🇨🇴', 'WC', '哥伦比亚', 1880, 1.080, 0.920, '埃尔坎潘球场'),
('CHI', '智利国家队', '智利', '🇨🇱', 'WC', '智利', 1840, 1.020, 0.950, '莫纽门塔尔球场'),
('ECU', '厄瓜多尔国家队', '厄瓜多尔', '🇪🇨', 'WC', '厄瓜多尔', 1800, 0.980, 0.980, '罗德里戈球场'),
('PER', '秘鲁国家队', '秘鲁', '🇵🇪', 'WC', '秘鲁', 1790, 0.950, 0.990, '国立球场'),
-- 欧洲强队
('FRA', '法国国家队', '法国', '🇫🇷', 'WC', '法国', 2100, 1.330, 0.760, '法兰西体育场'),
('ENG', '英格兰国家队', '英格兰', '🏴', 'WC', '英格兰', 2070, 1.280, 0.790, '温布利球场'),
('ESP', '西班牙国家队', '西班牙', '🇪🇸', 'WC', '西班牙', 2050, 1.250, 0.810, '伯纳乌球场'),
('GER', '德国国家队', '德国', '🇩🇪', 'WC', '德国', 2010, 1.220, 0.830, '安联球场'),
('NED', '荷兰国家队', '荷兰', '🇳🇱', 'WC', '荷兰', 1980, 1.200, 0.850, '克鲁伊夫竞技场'),
('POR', '葡萄牙国家队', '葡萄牙', '🇵🇹', 'WC', '葡萄牙', 1960, 1.180, 0.860, '光明球场'),
('ITA', '意大利国家队', '意大利', '🇮🇹', 'WC', '意大利', 1940, 1.100, 0.880, '奥林匹克球场'),
('BEL', '比利时国家队', '比利时', '🇧🇪', 'WC', '比利时', 1920, 1.120, 0.870, '博杜安国王体育场'),
('CRO', '克罗地亚国家队', '克罗地亚', '🇭🇷', 'WC', '克罗地亚', 1890, 1.080, 0.900, '马克西米尔球场'),
('SUI', '瑞士国家队', '瑞士', '🇨🇭', 'WC', '瑞士', 1850, 1.020, 0.930, '万克多夫球场'),
('DEN', '丹麦国家队', '丹麦', '🇩🇰', 'WC', '丹麦', 1840, 1.000, 0.940, '帕肯球场'),
('SRB', '塞尔维亚国家队', '塞尔维亚', '🇷🇸', 'WC', '塞尔维亚', 1820, 0.980, 0.950, '马拉卡纳球场'),
-- 亚洲球队
('JPN', '日本国家队', '日本', '🇯🇵', 'WC', '日本', 1870, 1.050, 0.910, '国立竞技场'),
('KOR', '韩国国家队', '韩国', '🇰🇷', 'WC', '韩国', 1840, 1.000, 0.930, '首尔世界杯球场'),
('IRN', '伊朗国家队', '伊朗', '🇮🇷', 'WC', '伊朗', 1780, 0.920, 0.980, '阿扎迪球场'),
('KSA', '沙特阿拉伯国家队', '沙特', '🇸🇦', 'WC', '沙特阿拉伯', 1760, 0.900, 0.990, '法赫德国王球场'),
('AUS', '澳大利亚国家队', '澳大利亚', '🇦🇺', 'WC', '澳大利亚', 1770, 0.910, 0.970, '澳大利亚体育场'),
-- 非洲球队
('MAR', '摩洛哥国家队', '摩洛哥', '🇲🇦', 'WC', '摩洛哥', 1860, 1.030, 0.920, '穆罕默德五世球场'),
('SEN', '塞内加尔国家队', '塞内加尔', '🇸🇳', 'WC', '塞内加尔', 1830, 0.990, 0.940, '桑戈尔球场'),
('NGA', '尼日利亚国家队', '尼日利亚', '🇳🇬', 'WC', '尼日利亚', 1810, 0.970, 0.950, '阿布贾球场'),
('CAM', '喀麦隆国家队', '喀麦隆', '🇨🇲', 'WC', '喀麦隆', 1780, 0.930, 0.970, '奥伦贝球场'),
-- 中北美球队
('USA', '美国国家队', '美国', '🇺🇸', 'WC', '美国', 1850, 1.020, 0.920, '玫瑰碗球场'),
('MEX', '墨西哥国家队', '墨西哥', '🇲🇽', 'WC', '墨西哥', 1830, 0.990, 0.940, '阿兹特克球场'),
('CAN', '加拿大国家队', '加拿大', '🇨🇦', 'WC', '加拿大', 1770, 0.910, 0.970, 'BMO球场');

-- ================================================
-- 3. 赛事表 (matches)
-- ================================================
CREATE TABLE IF NOT EXISTS matches (
  id VARCHAR(50) PRIMARY KEY COMMENT '赛事ID',
  league_id VARCHAR(20) COMMENT '联赛ID',
  home_team_id VARCHAR(20) NOT NULL COMMENT '主队ID',
  away_team_id VARCHAR(20) NOT NULL COMMENT '客队ID',
  match_date DATE NOT NULL COMMENT '比赛日期',
  match_time TIME COMMENT '比赛时间',
  venue VARCHAR(100) COMMENT '比赛场地',
  weather VARCHAR(50) COMMENT '天气状况',
  temperature VARCHAR(20) COMMENT '温度',
  pitch_condition VARCHAR(20) COMMENT '场地条件(优秀/良好/一般/较差)',
  status ENUM('upcoming', 'live', 'finished') DEFAULT 'upcoming' COMMENT '赛事状态',
  home_goals INT DEFAULT 0 COMMENT '主队进球数(实际)',
  away_goals INT DEFAULT 0 COMMENT '客队进球数(实际)',
  result ENUM('H', 'A', 'D') COMMENT '比赛结果(H=主队胜,A=客队胜,D=平局)',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_match_date (match_date),
  INDEX idx_match_status (status),
  INDEX idx_home_team (home_team_id),
  INDEX idx_away_team (away_team_id),
  INDEX idx_league_date (league_id, match_date),
  CONSTRAINT fk_match_league FOREIGN KEY (league_id) REFERENCES leagues(id) ON UPDATE CASCADE,
  CONSTRAINT fk_match_home FOREIGN KEY (home_team_id) REFERENCES teams(id) ON UPDATE CASCADE,
  CONSTRAINT fk_match_away FOREIGN KEY (away_team_id) REFERENCES teams(id) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='赛事信息表';

-- ================================================
-- 4. 赛事预测表 (match_predictions)
-- ================================================
CREATE TABLE IF NOT EXISTS match_predictions (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '预测记录ID',
  match_id VARCHAR(50) NOT NULL COMMENT '关联赛事ID',
  model_version VARCHAR(20) DEFAULT 'v5.0.0' COMMENT '模型版本',
  lambda_home DECIMAL(4,2) COMMENT '主队预期进球数λ',
  lambda_away DECIMAL(4,2) COMMENT '客队预期进球数λ',
  home_win_prob DECIMAL(6,4) COMMENT '主队胜概率(0-1)',
  draw_prob DECIMAL(6,4) COMMENT '平局概率(0-1)',
  away_win_prob DECIMAL(6,4) COMMENT '客队胜概率(0-1)',
  main_score VARCHAR(10) COMMENT '主线比分预测',
  alt_scores TEXT COMMENT '备选比分(JSON数组)',
  total_goals VARCHAR(20) COMMENT '总进球区间',
  tendency VARCHAR(200) COMMENT '倾向描述',
  confidence ENUM('high', 'mid', 'low') COMMENT '信心等级',
  risk_level ENUM('high', 'mid', 'low') COMMENT '风险等级',
  key_variables TEXT COMMENT '关键变量(JSON数组)',
  analysis TEXT COMMENT '简要分析',
  score_matrix TEXT COMMENT '比分概率矩阵(5x5 JSON)',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_pred_match (match_id),
  INDEX idx_pred_confidence (confidence),
  INDEX idx_pred_risk (risk_level),
  CONSTRAINT fk_pred_match FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='赛事预测结果表';

-- ================================================
-- 5. 用户表 (users)
-- ================================================
CREATE TABLE IF NOT EXISTS users (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '用户ID',
  username VARCHAR(50) UNIQUE NOT NULL COMMENT '用户名',
  email VARCHAR(100) UNIQUE NOT NULL COMMENT '邮箱',
  password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希(BCrypt)',
  avatar VARCHAR(255) COMMENT '头像URL',
  level VARCHAR(20) DEFAULT 'free' COMMENT '用户等级(free/pro/professional)',
  favorite_team_id VARCHAR(20) COMMENT '喜爱球队ID',
  join_date DATE COMMENT '加入日期',
  total_analysis INT DEFAULT 0 COMMENT '总分析次数',
  subscription_plan VARCHAR(30) DEFAULT 'free' COMMENT '订阅套餐',
  subscription_expire DATE COMMENT '订阅到期日期',
  subscription_status ENUM('active', 'expired', 'cancelled') DEFAULT 'expired' COMMENT '订阅状态',
  is_active TINYINT(1) DEFAULT 1 COMMENT '是否激活',
  last_login_at TIMESTAMP NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_user_username (username),
  INDEX idx_user_email (email),
  CONSTRAINT fk_user_team FOREIGN KEY (favorite_team_id) REFERENCES teams(id) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户信息表';

-- ================================================
-- 5b. 订阅套餐 (subscription_plans)
-- ================================================
CREATE TABLE IF NOT EXISTS subscription_plans (
  code VARCHAR(30) PRIMARY KEY COMMENT '套餐码 free/pro_month/flag_year 等',
  name VARCHAR(50) NOT NULL COMMENT '展示名',
  tier VARCHAR(20) NOT NULL DEFAULT 'free' COMMENT 'free/pro/flagship',
  duration_days INT DEFAULT 0 COMMENT '时长天数，0=不限',
  price DECIMAL(10,2) DEFAULT 0 COMMENT '标价（展示用）',
  features_json TEXT COMMENT '权益码 JSON 列表',
  description VARCHAR(255),
  is_active TINYINT(1) DEFAULT 1,
  sort_order INT DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订阅套餐定义';

-- ================================================
-- 5c. 订阅流水 (subscription_records)
-- ================================================
CREATE TABLE IF NOT EXISTS subscription_records (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  plan_code VARCHAR(30) NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE COMMENT 'free 套餐为 NULL',
  status ENUM('active', 'expired', 'cancelled') DEFAULT 'active' NOT NULL,
  source VARCHAR(20) DEFAULT 'admin_grant',
  operator_id BIGINT,
  note VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_sub_records_user (user_id),
  INDEX idx_sub_records_status (status),
  CONSTRAINT fk_sub_rec_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_sub_rec_plan FOREIGN KEY (plan_code) REFERENCES subscription_plans(code),
  CONSTRAINT fk_sub_rec_op FOREIGN KEY (operator_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订阅开通/续费/取消流水';

-- ================================================
-- 6. 用户收藏表 (user_favorites)
-- ================================================
CREATE TABLE IF NOT EXISTS user_favorites (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '收藏ID',
  user_id BIGINT NOT NULL COMMENT '用户ID',
  match_id VARCHAR(50) COMMENT '收藏赛事ID',
  team_id VARCHAR(20) COMMENT '收藏球队ID',
  type ENUM('match', 'team') NOT NULL COMMENT '收藏类型',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_fav_user (user_id),
  INDEX idx_fav_match (match_id),
  INDEX idx_fav_team (team_id),
  UNIQUE KEY uk_fav_user_match (user_id, match_id),
  UNIQUE KEY uk_fav_user_team (user_id, team_id),
  CONSTRAINT fk_fav_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_fav_match FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
  CONSTRAINT fk_fav_team FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户收藏表';

-- ================================================
-- 6b. 用户关注联赛 (user_followed_leagues)
-- ================================================
CREATE TABLE IF NOT EXISTS user_followed_leagues (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '关注ID',
  user_id BIGINT NOT NULL COMMENT '用户ID',
  league_id VARCHAR(20) NOT NULL COMMENT '联赛ID',
  sort_order INT DEFAULT 0 COMMENT '展示顺序',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_user_followed_league (user_id, league_id),
  INDEX idx_followed_user (user_id),
  CONSTRAINT fk_followed_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_followed_league FOREIGN KEY (league_id) REFERENCES leagues(id) ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户关注的联赛';

-- ================================================
-- 7. 用户历史分析记录 (user_history)
-- ================================================
CREATE TABLE IF NOT EXISTS user_history (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '记录ID',
  user_id BIGINT NOT NULL COMMENT '用户ID',
  match_id VARCHAR(50) NOT NULL COMMENT '赛事ID',
  match_name VARCHAR(200) COMMENT '赛事名称(显示用)',
  prediction VARCHAR(20) COMMENT '预测比分',
  actual VARCHAR(20) COMMENT '实际比分',
  result ENUM('correct', 'partial', 'wrong') COMMENT '预测结果',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_history_user (user_id),
  INDEX idx_history_match (match_id),
  INDEX idx_history_date (created_at),
  CONSTRAINT fk_history_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_history_match FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户历史分析记录表';

-- ================================================
-- 8. 用户偏好设置 (user_preferences)
-- ================================================
CREATE TABLE IF NOT EXISTS user_preferences (
  user_id BIGINT PRIMARY KEY COMMENT '用户ID',
  push_notification TINYINT(1) DEFAULT 1 COMMENT '推送通知开关',
  refresh_interval INT DEFAULT 5 COMMENT '数据刷新频率(分钟)',
  default_league_id VARCHAR(20) DEFAULT 'EPL' COMMENT '默认联赛',
  follow_include_children TINYINT(1) DEFAULT 0 COMMENT '关注过滤是否展开下级联赛',
  theme VARCHAR(20) DEFAULT 'dark' COMMENT '主题(light/dark)',
  language VARCHAR(20) DEFAULT 'zh-CN' COMMENT '语言',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_pref_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_pref_league FOREIGN KEY (default_league_id) REFERENCES leagues(id) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户偏好设置表';

-- ================================================
-- 9. 模型版本表 (model_versions)
-- ================================================
CREATE TABLE IF NOT EXISTS model_versions (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '版本ID',
  version VARCHAR(20) UNIQUE NOT NULL COMMENT '版本号',
  description TEXT COMMENT '更新描述',
  accuracy DECIMAL(5,2) COMMENT '模型准确率(%)',
  status ENUM('current', 'archived') DEFAULT 'current' COMMENT '状态',
  training_data_start DATE COMMENT '训练数据起始日期',
  training_data_end DATE COMMENT '训练数据结束日期',
  weights_json TEXT COMMENT '融合权重(JSON)',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_version (version),
  INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='模型版本记录表';

-- 插入初始数据
INSERT INTO model_versions (version, description, accuracy, status, weights_json) VALUES
('v5.0.3', '优化蒙特卡洛模拟参数，提升预测精度2.3%', 73.5, 'current', '{"elo":0.30,"xg":0.40,"poisson":0.30}'),
('v5.0.2', '修复xG模型射门距离权重计算问题', 71.2, 'archived', '{"elo":0.30,"xg":0.40,"poisson":0.30}'),
('v5.0.1', '新增ELO联赛等级系数动态调整', 70.8, 'archived', '{"elo":0.30,"xg":0.35,"poisson":0.35}'),
('v5.0.0', '初始职业版发布，集成泊松、ELO、xG三模型', 69.5, 'archived', '{"elo":0.33,"xg":0.34,"poisson":0.33}');

-- ================================================
-- 10. 风险预警表 (risk_alerts)
-- ================================================
CREATE TABLE IF NOT EXISTS risk_alerts (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '预警ID',
  match_id VARCHAR(50) COMMENT '关联赛事ID',
  match_name VARCHAR(200) COMMENT '赛事名称',
  type ENUM('data_abnormal', 'high_risk', 'weather', 'pitch', 'injury') NOT NULL COMMENT '风险类型',
  level ENUM('high', 'mid', 'low') NOT NULL COMMENT '风险等级',
  description TEXT COMMENT '风险描述',
  recommended_action TEXT COMMENT '建议操作',
  is_processed TINYINT(1) DEFAULT 0 COMMENT '是否已处理',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_risk_match (match_id),
  INDEX idx_risk_level (level),
  INDEX idx_risk_type (type),
  INDEX idx_risk_processed (is_processed),
  CONSTRAINT fk_risk_match FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='风险预警表';

-- ================================================
-- 11. 积分榜 (standings)
-- ================================================
CREATE TABLE IF NOT EXISTS standings (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '记录ID',
  league_id VARCHAR(20) NOT NULL COMMENT '联赛ID',
  team_id VARCHAR(20) NOT NULL COMMENT '球队ID',
  season VARCHAR(20) NOT NULL COMMENT '赛季(如2026-2027)',
  rank INT DEFAULT 0 COMMENT '排名',
  played INT DEFAULT 0 COMMENT '场次',
  won INT DEFAULT 0 COMMENT '胜场',
  drawn INT DEFAULT 0 COMMENT '平局',
  lost INT DEFAULT 0 COMMENT '负场',
  goals_for INT DEFAULT 0 COMMENT '进球数',
  goals_against INT DEFAULT 0 COMMENT '失球数',
  goal_diff INT DEFAULT 0 COMMENT '净胜球',
  points INT DEFAULT 0 COMMENT '积分',
  update_date DATE COMMENT '更新日期',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_standings_league (league_id),
  INDEX idx_standings_team (team_id),
  INDEX idx_standings_season (season),
  UNIQUE KEY uk_standings_league_team_season (league_id, team_id, season),
  CONSTRAINT fk_standings_league FOREIGN KEY (league_id) REFERENCES leagues(id) ON UPDATE CASCADE,
  CONSTRAINT fk_standings_team FOREIGN KEY (team_id) REFERENCES teams(id) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='积分榜表';

-- ================================================
-- 12. 射手榜 (top_scorers)
-- ================================================
CREATE TABLE IF NOT EXISTS top_scorers (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '记录ID',
  player_name VARCHAR(100) NOT NULL COMMENT '球员姓名',
  team_id VARCHAR(20) COMMENT '所属球队ID',
  league_id VARCHAR(20) NOT NULL COMMENT '联赛ID',
  season VARCHAR(20) NOT NULL COMMENT '赛季',
  goals INT DEFAULT 0 COMMENT '进球数',
  assists INT DEFAULT 0 COMMENT '助攻数',
  games_played INT DEFAULT 0 COMMENT '出场次数',
  rank INT DEFAULT 0 COMMENT '排名',
  update_date DATE COMMENT '更新日期',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_scorer_league (league_id),
  INDEX idx_scorer_team (team_id),
  INDEX idx_scorer_season (season),
  CONSTRAINT fk_scorer_team FOREIGN KEY (team_id) REFERENCES teams(id) ON UPDATE CASCADE,
  CONSTRAINT fk_scorer_league FOREIGN KEY (league_id) REFERENCES leagues(id) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='射手榜表';

-- ================================================
-- 13. 模型准确率趋势 (accuracy_trend)
-- ================================================
CREATE TABLE IF NOT EXISTS accuracy_trend (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '记录ID',
  model_version VARCHAR(20) NOT NULL COMMENT '模型版本',
  date DATE NOT NULL COMMENT '日期',
  accuracy DECIMAL(5,2) COMMENT '准确率(%)',
  total_matches INT DEFAULT 0 COMMENT '当日比赛数',
  correct_matches INT DEFAULT 0 COMMENT '预测正确数',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_trend_date (date),
  INDEX idx_trend_version (model_version),
  UNIQUE KEY uk_trend_date_version (date, model_version),
  CONSTRAINT fk_trend_version FOREIGN KEY (model_version) REFERENCES model_versions(version) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='模型准确率趋势表';

-- ================================================
-- 14. 操作日志表 (operation_logs)
-- ================================================
CREATE TABLE IF NOT EXISTS operation_logs (
  id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '日志ID',
  user_id BIGINT COMMENT '操作用户ID',
  action VARCHAR(100) NOT NULL COMMENT '操作类型',
  resource_type VARCHAR(50) COMMENT '资源类型',
  resource_id VARCHAR(100) COMMENT '资源ID',
  detail TEXT COMMENT '操作详情',
  ip_address VARCHAR(50) COMMENT 'IP地址',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_log_user (user_id),
  INDEX idx_log_action (action),
  INDEX idx_log_date (created_at),
  CONSTRAINT fk_log_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='操作日志表';

-- ================================================
-- 创建视图
-- ================================================

-- 赛事详情视图（含球队名称）
CREATE VIEW vw_match_detail AS
SELECT
  m.id,
  m.league_id,
  l.name AS league_name,
  l.icon AS league_icon,
  m.home_team_id,
  ht.name AS home_team_name,
  ht.short_name AS home_team_short,
  ht.logo AS home_team_logo,
  ht.elo_rating AS home_elo,
  m.away_team_id,
  at.name AS away_team_name,
  at.short_name AS away_team_short,
  at.logo AS away_team_logo,
  at.elo_rating AS away_elo,
  m.match_date,
  m.match_time,
  m.venue,
  m.weather,
  m.temperature,
  m.pitch_condition,
  m.status,
  m.home_goals,
  m.away_goals,
  m.result
FROM matches m
LEFT JOIN leagues l ON m.league_id = l.id
LEFT JOIN teams ht ON m.home_team_id = ht.id
LEFT JOIN teams at ON m.away_team_id = at.id;

-- 预测详情视图（含赛事信息）
CREATE VIEW vw_prediction_detail AS
SELECT
  p.*,
  m.league_id,
  l.name AS league_name,
  ht.name AS home_team_name,
  ht.short_name AS home_team_short,
  at.name AS away_team_name,
  at.short_name AS away_team_short,
  m.match_date,
  m.match_time,
  m.status
FROM match_predictions p
LEFT JOIN matches m ON p.match_id = m.id
LEFT JOIN leagues l ON m.league_id = l.id
LEFT JOIN teams ht ON m.home_team_id = ht.id
LEFT JOIN teams at ON m.away_team_id = at.id;

-- 用户统计视图
CREATE VIEW vw_user_stats AS
SELECT
  u.id AS user_id,
  u.username,
  u.level,
  u.total_analysis,
  COUNT(h.id) AS history_count,
  SUM(CASE WHEN h.result = 'correct' THEN 1 ELSE 0 END) AS correct_count,
  SUM(CASE WHEN h.result = 'partial' THEN 0.5 ELSE 0 END) AS partial_count,
  COUNT(f.id) AS favorite_count,
  u.join_date
FROM users u
LEFT JOIN user_history h ON u.id = h.user_id
LEFT JOIN user_favorites f ON u.id = f.user_id
GROUP BY u.id, u.username, u.level, u.total_analysis, u.join_date;

-- ================================================
-- 创建存储过程
-- ================================================

-- 获取赛事预测（如果不存在则生成）
DELIMITER //
CREATE PROCEDURE sp_get_prediction(IN p_match_id VARCHAR(50))
BEGIN
  DECLARE pred_count INT;
  
  SELECT COUNT(*) INTO pred_count FROM match_predictions WHERE match_id = p_match_id;
  
  IF pred_count > 0 THEN
    SELECT * FROM match_predictions WHERE match_id = p_match_id ORDER BY created_at DESC LIMIT 1;
  ELSE
    SELECT NULL AS id, p_match_id AS match_id, 'no_prediction' AS message;
  END IF;
END //
DELIMITER ;

-- 获取用户准确率
DELIMITER //
CREATE PROCEDURE sp_get_user_accuracy(IN p_user_id BIGINT)
BEGIN
  SELECT
    COALESCE(
      (SUM(CASE WHEN result = 'correct' THEN 1 WHEN result = 'partial' THEN 0.5 ELSE 0 END) / COUNT(*)) * 100,
      0
    ) AS accuracy_rate
  FROM user_history
  WHERE user_id = p_user_id;
END //
DELIMITER ;

-- 更新球队ELO评级
DELIMITER //
CREATE PROCEDURE sp_update_team_elo(
  IN p_team_id VARCHAR(20),
  IN p_new_elo INT
)
BEGIN
  UPDATE teams SET elo_rating = p_new_elo, updated_at = CURRENT_TIMESTAMP WHERE id = p_team_id;
END //
DELIMITER ;

-- ================================================
-- 初始化示例数据
-- ================================================

-- 插入示例赛事
INSERT INTO matches (id, league_id, home_team_id, away_team_id, match_date, match_time, venue, weather, temperature, pitch_condition, status) VALUES
('M001', 'EPL', 'MCI', 'ARS', '2026-07-15', '22:00:00', '伊蒂哈德球场', '晴', '18°C', '良好', 'upcoming'),
('M002', 'LALIGA', 'RMA', 'BAR', '2026-07-15', '23:00:00', '伯纳乌球场', '多云', '22°C', '良好', 'upcoming'),
('M003', 'BUNDES', 'BAY', 'DOR', '2026-07-15', '21:30:00', '安联球场', '晴', '19°C', '优秀', 'upcoming'),
('M004', 'SERIEA', 'INT', 'JUV', '2026-07-16', '02:45:00', '梅阿查球场', '阴', '16°C', '良好', 'upcoming'),
('M005', 'LIGUE1', 'PSG', 'MIL', '2026-07-16', '03:00:00', '王子公园球场', '晴', '20°C', '优秀', 'upcoming'),
('M006', 'EPL', 'LIV', 'CHE', '2026-07-16', '19:30:00', '安菲尔德球场', '小雨', '15°C', '一般', 'upcoming'),
('M007', 'EPL', 'TOT', 'MUN', '2026-07-16', '22:00:00', '热刺球场', '晴', '17°C', '良好', 'upcoming'),
('M008', 'UCL', 'RMA', 'BAY', '2026-07-17', '03:00:00', '伯纳乌球场', '晴', '21°C', '优秀', 'upcoming');

-- 世界杯赛事数据 (2026美加墨世界杯)
INSERT INTO matches (id, league_id, home_team_id, away_team_id, match_date, match_time, venue, weather, temperature, pitch_condition, status) VALUES
-- 小组赛A组
('WC001', 'WC', 'MEX', 'COL', '2026-06-11', '20:00:00', '阿兹特克球场', '晴', '24°C', '优秀', 'upcoming'),
('WC002', 'WC', 'CAN', 'ECU', '2026-06-12', '15:00:00', 'BMO球场', '多云', '18°C', '良好', 'upcoming'),
-- 小组赛B组
('WC003', 'WC', 'USA', 'SEN', '2026-06-12', '20:00:00', '玫瑰碗球场', '晴', '22°C', '优秀', 'upcoming'),
('WC004', 'WC', 'IRN', 'AUS', '2026-06-13', '15:00:00', '澳大利亚体育场', '晴', '20°C', '良好', 'upcoming'),
-- 小组赛C组
('WC005', 'WC', 'ARG', 'MAR', '2026-06-13', '20:00:00', '纪念碑球场', '晴', '15°C', '优秀', 'upcoming'),
('WC006', 'WC', 'CRO', 'CAM', '2026-06-14', '15:00:00', '马克西米尔球场', '多云', '17°C', '良好', 'upcoming'),
-- 小组赛D组
('WC007', 'WC', 'FRA', 'PER', '2026-06-14', '20:00:00', '法兰西体育场', '晴', '19°C', '优秀', 'upcoming'),
('WC008', 'WC', 'DEN', 'KSA', '2026-06-15', '15:00:00', '帕肯球场', '阴', '14°C', '良好', 'upcoming'),
-- 小组赛E组
('WC009', 'WC', 'ESP', 'NGA', '2026-06-15', '20:00:00', '伯纳乌球场', '晴', '25°C', '优秀', 'upcoming'),
('WC010', 'WC', 'NED', 'URU', '2026-06-16', '15:00:00', '克鲁伊夫竞技场', '多云', '16°C', '良好', 'upcoming'),
-- 小组赛F组
('WC011', 'WC', 'BRA', 'SRB', '2026-06-16', '20:00:00', '马拉卡纳球场', '晴', '28°C', '优秀', 'upcoming'),
('WC012', 'WC', 'SUI', 'CHI', '2026-06-17', '15:00:00', '万克多夫球场', '晴', '18°C', '良好', 'upcoming'),
-- 小组赛G组
('WC013', 'WC', 'ENG', 'JPN', '2026-06-17', '20:00:00', '温布利球场', '多云', '17°C', '优秀', 'upcoming'),
('WC014', 'WC', 'POR', 'KOR', '2026-06-18', '15:00:00', '光明球场', '晴', '22°C', '良好', 'upcoming'),
-- 小组赛H组
('WC015', 'WC', 'GER', 'BEL', '2026-06-18', '20:00:00', '安联球场', '晴', '20°C', '优秀', 'upcoming'),
('WC016', 'WC', 'ITA', 'KOR', '2026-06-19', '15:00:00', '奥林匹克球场', '晴', '24°C', '良好', 'upcoming'),
-- 焦点对决
('WC017', 'WC', 'BRA', 'ARG', '2026-06-25', '20:00:00', '马拉卡纳球场', '晴', '26°C', '优秀', 'upcoming'),
('WC018', 'WC', 'FRA', 'ENG', '2026-06-26', '20:00:00', '法兰西体育场', '多云', '18°C', '优秀', 'upcoming'),
('WC019', 'WC', 'ESP', 'GER', '2026-06-27', '20:00:00', '伯纳乌球场', '晴', '23°C', '优秀', 'upcoming'),
('WC020', 'WC', 'POR', 'NED', '2026-06-28', '20:00:00', '光明球场', '晴', '21°C', '良好', 'upcoming');

-- 插入示例积分榜数据（英超）
INSERT INTO standings (league_id, team_id, season, rank, played, won, drawn, lost, goals_for, goals_against, goal_diff, points, update_date) VALUES
('EPL', 'MCI', '2026-2027', 1, 24, 18, 4, 2, 58, 22, 36, 58, '2026-07-15'),
('EPL', 'ARS', '2026-2027', 2, 24, 16, 5, 3, 52, 24, 28, 53, '2026-07-15'),
('EPL', 'LIV', '2026-2027', 3, 24, 15, 6, 3, 55, 28, 27, 51, '2026-07-15'),
('EPL', 'TOT', '2026-2027', 4, 24, 13, 5, 6, 48, 35, 13, 44, '2026-07-15'),
('EPL', 'CHE', '2026-2027', 5, 24, 12, 6, 6, 42, 33, 9, 42, '2026-07-15'),
('EPL', 'MUN', '2026-2027', 6, 24, 11, 6, 7, 38, 36, 2, 39, '2026-07-15');

-- 插入示例射手榜数据（英超）
INSERT INTO top_scorers (player_name, team_id, league_id, season, goals, assists, games_played, rank, update_date) VALUES
('哈兰德', 'MCI', 'EPL', '2026-2027', 22, 5, 20, 1, '2026-07-15'),
('萨拉赫', 'LIV', 'EPL', '2026-2027', 18, 9, 22, 2, '2026-07-15'),
('萨卡', 'ARS', 'EPL', '2026-2027', 15, 8, 23, 3, '2026-07-15'),
('孙兴慜', 'TOT', 'EPL', '2026-2027', 14, 6, 21, 4, '2026-07-15'),
('沃特金斯', NULL, 'EPL', '2026-2027', 13, 4, 20, 5, '2026-07-15');

-- 插入示例准确率趋势数据
INSERT INTO accuracy_trend (model_version, date, accuracy, total_matches, correct_matches) VALUES
('v5.0.3', '2026-07-01', 71.2, 8, 6),
('v5.0.3', '2026-07-02', 70.8, 10, 7),
('v5.0.3', '2026-07-03', 72.1, 12, 9),
('v5.0.3', '2026-07-04', 71.5, 9, 6),
('v5.0.3', '2026-07-05', 73.0, 11, 8),
('v5.0.3', '2026-07-06', 72.3, 10, 7),
('v5.0.3', '2026-07-07', 71.8, 8, 6),
('v5.0.3', '2026-07-08', 73.5, 10, 7),
('v5.0.3', '2026-07-09', 72.9, 12, 9),
('v5.0.3', '2026-07-10', 73.2, 11, 8),
('v5.0.3', '2026-07-11', 72.6, 9, 7),
('v5.0.3', '2026-07-12', 73.5, 10, 7),
('v5.0.3', '2026-07-13', 73.1, 11, 8),
('v5.0.3', '2026-07-14', 73.5, 10, 7);

-- ================================================
-- 创建索引优化查询性能
-- ================================================
CREATE INDEX IF NOT EXISTS idx_match_league_status_date ON matches(league_id, status, match_date);
CREATE INDEX IF NOT EXISTS idx_prediction_match_version ON match_predictions(match_id, model_version);
CREATE INDEX IF NOT EXISTS idx_user_level_active ON users(level, is_active);
CREATE INDEX IF NOT EXISTS idx_history_user_date ON user_history(user_id, created_at);

-- ================================================
-- 创建用户和权限
-- ================================================
-- CREATE USER 'football_user'@'localhost' IDENTIFIED BY 'your_password_here';
-- GRANT SELECT, INSERT, UPDATE, DELETE ON football_analytics.* TO 'football_user'@'localhost';
-- FLUSH PRIVILEGES;

-- ================================================
-- 脚本结束
-- ================================================
SELECT '数据库建表完成' AS message;
