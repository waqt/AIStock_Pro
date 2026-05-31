# Learnings

Corrections, insights, and knowledge gaps captured during development.

**Categories**: correction | insight | knowledge_gap | best_practice

---

## [LRN-20250530-001] correction

**Logged**: 2025-05-30T15:00:00Z
**Priority**: medium
**Status**: resolved
**Area**: config

### Summary
Claude Code settings.json 不支持 `autoUpdate` 顶层字段，需用环境变量 `CLAUDE_CODE_AUTO_UPDATE=0`

### Details
尝试在 settings.json 添加 `"autoUpdate": false` 时被 schema 校验拒绝。正确做法是写入 `env.CLAUDE_CODE_AUTO_UPDATE` 环境变量。

### Suggested Action
已在 settings.json 中正确配置 `env.CLAUDE_CODE_AUTO_UPDATE: "0"`

### Metadata
- Source: tool_validation_error
- Related Files: C:\Users\86157\.claude\settings.json
- Tags: settings, autocorrelation

## [LRN-20250530-002] best_practice

**Logged**: 2025-05-30T15:00:00Z
**Priority**: medium
**Status**: resolved
**Area**: config

### Summary
Claude Code 会话转录文件 JSONL 可能增长到 100MB+，需要主动管理

### Details
当前项目会话文件达到 122MB，子智能体记录 8.85MB。设置 `cleanupPeriodDays` 控制自动清理周期。设置 `autoCompactEnabled` + `autoCompactWindow` 让上下文超限时自动压缩。删除旧 JSONL 文件不影响项目代码。

### Suggested Action
已在 settings.json 配置 `cleanupPeriodDays: 7`, `autoCompactEnabled: true`, `autoCompactWindow: 200000`

### Metadata
- Source: user_request
- Related Files: C:\Users\86157\.claude\settings.json
- Tags: session_management, disk_space

---
