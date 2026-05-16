-- V1.0__init_schema.sql
-- 初始数据库结构设计 (AIStock_Pro)

-- 1. 股票基础信息表
CREATE TABLE IF NOT EXISTS `stocks` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `code` VARCHAR(20) NOT NULL UNIQUE COMMENT '股票代码 (如: sh.600000)',
    `name` VARCHAR(50) NOT NULL COMMENT '股票名称',
    `industry` VARCHAR(50) COMMENT '所属行业',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. 核心持仓表
CREATE TABLE IF NOT EXISTS `positions` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `stock_code` VARCHAR(20) NOT NULL,
    `stock_name` VARCHAR(50),
    `volume` DECIMAL(20, 2) DEFAULT 0.00 COMMENT '持仓数量',
    `avg_cost` DECIMAL(20, 4) DEFAULT 0.00 COMMENT '持仓均价',
    `market_value` DECIMAL(20, 2) DEFAULT 0.00 COMMENT '当前市值',
    `profit_loss` DECIMAL(20, 2) DEFAULT 0.00 COMMENT '浮盈损',
    `profit_loss_ratio` DECIMAL(10, 4) DEFAULT 0.00 COMMENT '盈亏比例',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_stock_code` (`stock_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. AI 任务追踪表 (针对建议 1: 任务状态透明化)
CREATE TABLE IF NOT EXISTS `analysis_tasks` (
    `id` VARCHAR(50) PRIMARY KEY COMMENT 'UUID 任务ID',
    `task_type` VARCHAR(50) NOT NULL COMMENT '任务类型: RESEARCH, QUANT, IMPORT',
    `status` VARCHAR(20) DEFAULT 'PENDING' COMMENT 'PENDING, RUNNING, SUCCESS, FAILED',
    `progress` INT DEFAULT 0 COMMENT '进度百分比 0-100',
    `current_step` VARCHAR(200) COMMENT '当前正在执行的步骤描述',
    `result_summary` TEXT COMMENT 'AI 分析结论摘要',
    `error_msg` TEXT COMMENT '错误详情',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. 弹性指标库 (针对策略与指标数据结构建议)
CREATE TABLE IF NOT EXISTS `stock_indicators` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `stock_code` VARCHAR(20) NOT NULL,
    `indicator_type` VARCHAR(50) NOT NULL COMMENT '指标类别: TREND, PATTERN, FUNDAMENTAL',
    `data_json` JSON NOT NULL COMMENT '指标数据详情 (MA, RSI, 筹码分布等)',
    `logic_chain` JSON COMMENT '逻辑链推演记录',
    `analysis_date` DATE NOT NULL COMMENT '分析日期',
    UNIQUE KEY `uk_stock_date_type` (`stock_code`, `analysis_date`, `indicator_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
