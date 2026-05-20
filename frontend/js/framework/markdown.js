/**
 * Markdown 渲染组件 — 将 Markdown 文本转为 HTML, 支持暗色主题
 * 支持: 标题 / 粗体 / 斜体 / 表格 / 列表 / 代码块 / 链接 / 分割线 / 引用
 */

const MD = {
    render(md) {
        if (!md) return '';
        let html = md;

        // 代码块 (```...```) — 必须先处理, 避免内部被其他规则破坏
        html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
            const escaped = this._escHtml(code.trim());
            return `<pre><code class="language-${lang}">${escaped}</code></pre>`;
        });

        // 行内代码
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

        // 标题
        html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
        html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
        html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
        html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

        // 粗体 / 斜体
        html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

        // 链接
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

        // 图片
        html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" style="max-width:100%;border-radius:4px;">');

        // 分割线
        html = html.replace(/^---$/gm, '<hr>');

        // 引用块
        html = html.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');

        // 无序列表 — 合并连续项
        html = html.replace(/((?:^- .+\n?)+)/gm, (match) => {
            const items = match.trim().split('\n')
                .filter(l => l.startsWith('- '))
                .map(l => '<li>' + l.slice(2) + '</li>')
                .join('');
            return '<ul>' + items + '</ul>';
        });

        // 有序列表
        html = html.replace(/((?:^\d+\. .+\n?)+)/gm, (match) => {
            const items = match.trim().split('\n')
                .filter(l => /^\d+\./.test(l))
                .map(l => '<li>' + l.replace(/^\d+\.\s*/, '') + '</li>')
                .join('');
            return '<ol>' + items + '</ol>';
        });

        // 表格 (Markdown table → HTML table)
        html = html.replace(/((?:^\|.+\|\n?)+)/gm, (match) => {
            const lines = match.trim().split('\n').filter(l => l.includes('|'));
            if (lines.length < 2) return match;
            // 跳过分隔行
            const dataLines = lines.filter(l => !/^[\|\s\-:]+$/.test(l));
            if (dataLines.length < 1) return match;
            const renderRow = (row, tag) => {
                const cells = row.split('|').filter(c => c.trim()).map(c => `<${tag}>${c.trim()}</${tag}>`).join('');
                return `<tr>${cells}</tr>`;
            };
            const thead = renderRow(dataLines[0], 'th');
            const tbody = dataLines.slice(1).map(r => renderRow(r, 'td')).join('');
            return `<table class="md-table"><thead>${thead}</thead><tbody>${tbody}</tbody></table>`;
        });

        // 段落 (连续的非空行)
        html = html.replace(/\n\n+/g, '</p><p>');
        html = '<p>' + html + '</p>';

        // 清理空段落
        html = html.replace(/<p>\s*<\/p>/g, '');
        // 合并被块级元素打断的段落
        html = html.replace(/<\/p><(h[1-4]|pre|ul|ol|table|blockquote|hr)/g, '</p>\n<$1');
        html = html.replace(/<\/(h[1-4]|pre|ul|ol|table|blockquote)>(\s*)<p>/g, '</$1>$2<p>');

        return html;
    },

    // 快捷方法: 渲染并返回 HTML 字符串
    toHTML(md) {
        return this.render(md);
    },

    // 快捷方法: 直接设置元素的 innerHTML
    mount(elementId, md) {
        const el = document.getElementById(elementId);
        if (el) el.innerHTML = this.render(md);
    },

    _escHtml(s) {
        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
};
