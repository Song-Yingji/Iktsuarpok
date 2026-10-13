-- ============================================================
-- Iktsuarpok 智能量化投资系统 - MySQL 数据库建表脚本
-- 数据库版本：MySQL 5.7+（JSON 类型需 5.7+，推荐 8.0）
-- 字符集：utf8mb4（支持中文与 emoji），排序规则 utf8mb4_unicode_ci
-- 覆盖范围：仅用户动态数据（静态配置如股票清单/策略模板/回测框架仍留在代码）
--
-- 建表顺序说明：
--   users（无外键依赖）先建；
--   preference_sets / user_settings / saved_strategies / watchlist / accounts 只依赖 users；
--   account_credentials 依赖 accounts，故在 accounts 之后；
--   quant_tasks 无外键，逻辑关联 saved_strategies.id / accounts.id（引用失效由后端置空处理）。
--
-- 注意：偏好支持多套（1 用户 : N 套），交易提醒开关已从偏好中剥离，
--       作为与偏好无关的全局设置存入 user_settings。
--       账户凭证与账户本体分离加密存储（见 account_credentials），
--       账户的策略绑定与自动交易开关已迁移至 quant_tasks。
-- ============================================================

CREATE DATABASE IF NOT EXISTS xb_quant
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE xb_quant;

-- ------------------------------------------------------------
-- 1. 用户表
-- 对应后端 /api/auth/register 的 username/password/phone
-- 密码只存哈希（PBKDF2 加盐），绝不存明文
-- role：权限等级，0 普通用户 / 1 管理员 / 2 超级管理员
--       1 及以上可登录 /admin/login 进入管理后台
--       2 为超级管理员，全局唯一（由后端启动时播种），不可删除、不可取消管理员身份
-- ------------------------------------------------------------
CREATE TABLE users (
  id            INT UNSIGNED     NOT NULL AUTO_INCREMENT COMMENT '用户ID（自增）',
  username      VARCHAR(50)      NOT NULL                COMMENT '用户名（唯一，登录凭证）',
  password_hash VARCHAR(255)     NOT NULL                COMMENT '密码哈希（PBKDF2 加盐）',
  phone         VARCHAR(20)      DEFAULT NULL            COMMENT '手机号（注册选填，1 开头的 11 位）',
  avatar        VARCHAR(10)      DEFAULT NULL            COMMENT '头像字符（用户名首字母大写）',
  role          TINYINT UNSIGNED NOT NULL DEFAULT 0      COMMENT '权限等级：0普通用户 1管理员 2超级管理员',
  created_at    DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at    DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='用户表';

-- ------------------------------------------------------------
-- 2. 投资偏好表（1 用户 : N 套）
-- 对应 data.py 的 DEFAULT_PREFS、/api/prefs
-- name 为用户自定义的偏好名称，同一用户下唯一
-- is_default 标记荐股时默认使用的那一套，同一用户至多一套为 1（由后端保证）
-- sectors（偏好行业数组）用 JSON 存，如 ["新能源","人工智能","医药生物"]
-- 注意：交易提醒开关不在此表，见 user_settings
-- ------------------------------------------------------------
CREATE TABLE preference_sets (
  id           INT UNSIGNED    NOT NULL AUTO_INCREMENT COMMENT '偏好ID',
  user_id      INT UNSIGNED    NOT NULL                COMMENT '所属用户ID',
  name         VARCHAR(50)     NOT NULL DEFAULT '默认偏好' COMMENT '偏好名称（用户自定义，同用户下唯一）',
  risk         VARCHAR(20)     NOT NULL DEFAULT '稳健型' COMMENT '风险等级：保守型/稳健型/平衡型/进取型/激进型',
  horizon      VARCHAR(30)     NOT NULL DEFAULT '中线（1-6个月）' COMMENT '投资期限：短线/中线/长线',
  benchmark    VARCHAR(20)     NOT NULL DEFAULT '沪深300' COMMENT '业绩比较基准',
  sectors      JSON            DEFAULT NULL            COMMENT '偏好行业数组（JSON）',
  max_position TINYINT UNSIGNED NOT NULL DEFAULT 25     COMMENT '单票最大仓位（%）',
  stop_loss    TINYINT UNSIGNED NOT NULL DEFAULT 8      COMMENT '止损线（%）',
  take_profit  TINYINT UNSIGNED NOT NULL DEFAULT 30     COMMENT '止盈线（%）',
  is_default   TINYINT(1)      NOT NULL DEFAULT 1       COMMENT '荐股默认偏好：1是 0否',
  created_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_prefset_user_name (user_id, name),
  KEY idx_prefset_user (user_id),
  CONSTRAINT fk_prefs_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='用户投资偏好（1 用户 : N 套）';

-- ------------------------------------------------------------
-- 2.1 用户全局设置表（1 用户 : 1）
-- 与投资偏好无关的开关，目前承载「交易提醒」
-- ------------------------------------------------------------
CREATE TABLE user_settings (
  id           INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '设置ID',
  user_id      INT UNSIGNED NOT NULL                COMMENT '所属用户ID',
  trade_notify TINYINT(1)   NOT NULL DEFAULT 1      COMMENT '交易提醒开关：1开 0关',
  updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_settings_user (user_id),
  CONSTRAINT fk_settings_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='用户全局设置（与偏好无关）';

-- ------------------------------------------------------------
-- 3. 已保存的量化策略表（1 用户 : N 策略）
-- 对应后端 /api/strategy/saved，由「AI 智能体」生成后保存
-- params/rules 用 JSON 存；code 存策略伪代码
-- ------------------------------------------------------------
CREATE TABLE saved_strategies (
  id         INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '策略ID',
  user_id    INT UNSIGNED NOT NULL                COMMENT '所属用户ID',
  name       VARCHAR(100) NOT NULL                COMMENT '策略名称',
  type       VARCHAR(30)  DEFAULT NULL            COMMENT '策略类型：趋势跟踪/动量轮动等',
  engine_id  VARCHAR(30)  NOT NULL DEFAULT 'ma_cross' COMMENT '回测引擎：ma_cross/macd/boll/rsi/momentum',
  params     JSON         DEFAULT NULL            COMMENT '策略参数（JSON，如 {fast:5,slow:20}）',
  rules      JSON         DEFAULT NULL            COMMENT '策略规则描述数组（JSON）',
  code       TEXT                                 COMMENT '策略伪代码',
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  KEY idx_strategy_user (user_id),
  CONSTRAINT fk_strategy_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='用户已保存的量化策略';

-- ------------------------------------------------------------
-- 4. 交易账户表（1 用户 : N 账户）
-- 对应后端 /api/accounts，账户本体只存名称/类型/平台/资金等资料
-- 登录凭证分离加密存储于 account_credentials（方案 C），
-- 策略绑定与自动交易开关在 quant_tasks，不在本表
-- 资金（total_assets/cash）由连接器层读取后回填：
--   模拟盘固定 1,000,000；实盘经 GenericHttpConnector 拉取
-- ------------------------------------------------------------
CREATE TABLE accounts (
  id            INT UNSIGNED     NOT NULL AUTO_INCREMENT COMMENT '账户ID',
  user_id       INT UNSIGNED     NOT NULL                COMMENT '所属用户ID',
  name          VARCHAR(50)      NOT NULL                COMMENT '账户名称',
  type          VARCHAR(20)      NOT NULL DEFAULT '模拟盘' COMMENT '账户类型：模拟盘/实盘·A股/实盘·美股',
  platform_url  VARCHAR(255)     DEFAULT NULL            COMMENT '交易平台地址（选填）',
  status        VARCHAR(20)      NOT NULL DEFAULT 'connected' COMMENT '状态：connected/active/disconnected',
  connect_status VARCHAR(20)     NOT NULL DEFAULT 'untested'  COMMENT '连接测试结果：untested/success/failed',
  last_checked  DATETIME         DEFAULT NULL            COMMENT '最近一次连接测试时间',
  total_assets  DECIMAL(18,2)    NOT NULL DEFAULT 0      COMMENT '总资产',
  cash          DECIMAL(18,2)    NOT NULL DEFAULT 0      COMMENT '可用资金',
  created_at    DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at    DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  KEY idx_account_user (user_id),
  CONSTRAINT fk_account_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='交易账户';

-- ------------------------------------------------------------
-- 4.1 账户凭证表（1 账户 : 1 凭证，与账户本体分离）
-- 对应后端 credentials.py：password_enc 为 Fernet 加密串
-- 密钥来自环境变量 CRED_SECRET_KEY 或 db_config.CRED_SECRET_KEY（已 gitignore）
-- login_account 存登录账号（明文，仅用于连接回显）；密码只存密文
-- ------------------------------------------------------------
CREATE TABLE account_credentials (
  id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
  account_id    INT UNSIGNED NOT NULL,
  login_account VARCHAR(128) DEFAULT NULL            COMMENT '登录账号',
  password_enc  TEXT                                 COMMENT '登录密码（Fernet 加密串）',
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_cred_account (account_id),
  CONSTRAINT fk_cred_account FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='账户登录凭证（加密存储，与账户本体分离）';

-- ------------------------------------------------------------
-- 4.2 量化交易任务表（1 用户 : N 任务）
-- 对应后端 /api/quant-tasks，量化交易页面的任务卡片
-- stock_codes 标的代码 JSON 数组，如 ["600519","000001"]
-- strategy_id / account_id 逻辑关联 saved_strategies.id / accounts.id（不设外键），
-- 引用被删除后由后端 _scrub_task_refs 置 NULL
-- auto_trade 自动交易开关：开启需标的+策略+账户三者齐备（前端校验，配置不全保存时强制关闭）
-- ------------------------------------------------------------
CREATE TABLE quant_tasks (
  id           BIGINT       NOT NULL AUTO_INCREMENT,
  user_id      INT          NOT NULL,
  stock_codes  JSON         NOT NULL                COMMENT '标的代码数组（JSON）',
  strategy_id  BIGINT       DEFAULT NULL            COMMENT '策略ID（逻辑关联 saved_strategies.id）',
  account_id   BIGINT       DEFAULT NULL            COMMENT '账户ID（逻辑关联 accounts.id）',
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  auto_trade   TINYINT(1)   NOT NULL DEFAULT 0      COMMENT '自动交易开关：1开 0关',
  PRIMARY KEY (id),
  KEY idx_qt_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='量化交易任务';

-- ------------------------------------------------------------
-- 5. 自选股表（1 用户 : N 自选股）
-- 对应后端 /api/watchlist，同一用户同一股票唯一
-- ------------------------------------------------------------
CREATE TABLE watchlist (
  id         INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '记录ID',
  user_id    INT UNSIGNED NOT NULL                COMMENT '所属用户ID',
  stock_code VARCHAR(10)  NOT NULL                COMMENT '股票代码（如 600519 / SH000001）',
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '加入时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_watch_user_code (user_id, stock_code),
  CONSTRAINT fk_watch_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='用户自选股';
