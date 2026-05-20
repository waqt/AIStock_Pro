# 前端开发规范

## JS 加载顺序 (关键!)

每个 HTML 页面必须按此顺序加载:
```html
<script src="js/framework/api.js"></script>
<script src="js/framework/modal.js"></script>
<script src="js/framework/task_monitor.js"></script>
<script src="js/framework/markdown.js"></script>
<script src="js/ui.js"></script>
<script src="js/common.js"></script>
<!-- 页面业务 JS 放在最后 -->
```

## 页面模板

```html
<body data-page-id="xxx">  <!-- 与 ui.js sidebar menuItems 的 id 对应 -->
  <div class="app-container">
    <aside class="sidebar"></aside>
    <main class="main-content">
      <div class="top-bar"></div>
      <div class="workspace"><!-- 正文 --></div>
    </main>
  </div>
  <script src="js/framework/api.js"></script>
  ...
  <script>/* 页面业务 JS */</script>
</body>
```

## 组件使用

### 弹窗
```javascript
await Modal.alert('标题', '消息内容');
const ok = await Modal.confirm('确认', '确认此操作?');
const ok = await Modal.danger('危险', '删除不可撤销');
```
- 禁止使用 `alert()` / `confirm()` (白色原生弹窗)

### API 调用
```javascript
const data = await API.get('/positions');
const result = await API.post('/data/sync/daily/auto', { type: 'AUTO' });
```
- `API_BASE` 在 `framework/api.js` 中定义为 `/api`
- 禁止硬编码 `http://localhost:8000/api`

### 任务监控
- 由 `framework/task_monitor.js` 自动初始化 (`initCommon()` 触发)
- 轮询间隔: 8s

### 市场跑马灯
- 由 `common.js` 的 `initCommon()` 自动触发
- 刷新间隔: 30s
- 更新函数: `UI_COMPONENTS.updateMarketTicker()`

## 样式规范

- 颜色: 使用 CSS 变量 — `var(--accent-green)`, `var(--text-dim)`, `var(--border-color)` 等
- 字体: 正文 `var(--font-main)`, 数字 `var(--font-mono)`
- 禁止硬编码颜色值 (`#fff`, `#000` 除外)
- 新页面必须使用暗色主题 (黑色/深灰底色)

## 新增页面检查清单

- [ ] `<body data-page-id>` 与 `ui.js` sidebar menuItems 的 id 对应
- [ ] JS 加载顺序正确 (api → modal → task_monitor → ui → common → page)
- [ ] 使用 Modal 替代 alert/confirm
- [ ] API 路径以 `API_BASE` 开头
- [ ] 使用 CSS 变量而非硬编码颜色

## Markdown 渲染

复杂文本内容使用 `MD.render(markdownText)` 渲染, 不要手写 HTML 拼接:

```javascript
// ✅ 正确: 使用 MD 组件
document.getElementById('content').innerHTML = MD.render(d.summary);

// ❌ 错误: 手动 replace 正则
d.summary.replace(/### (.+)/g, '<h3>$1</h3>').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')...
```

需要特殊样式时, 给容器加 `class="md-content"` 即可自动应用暗色主题。
