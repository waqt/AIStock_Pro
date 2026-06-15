/**
 * 产业图谱 — ECharts force-directed graph 渲染
 * 依赖: GraphBridge → /api/graph/{run_id}
 */
window.GraphApp = {
    chart: null,
    currentRunId: null,

    // 节点类型 → 颜色映射
    NODE_COLORS: {
        chain: '#5B8FF9',
        process: '#5AD8A6',
        stock: '#F6BD16',
        industry: '#9270CA',
    },

    // 边类型 → 颜色
    EDGE_COLORS: {
        feeds_to: '#4a5a7a',
        belongs_to: '#3a6a5a',
        maps_to: '#8a7a3a',
        sales_chain: '#5a8a3a',
        expansion_chain: '#8a5a3a',
    },

    // 严重度 → 边框宽度
    SEVERITY_BORDER: {
        extreme: 5,
        very_high: 4,
        high: 3,
        medium: 2,
        low: 1,
        '': 0,
    },

    // 严重度 → 文本颜色 class
    SEVERITY_CLASS: {
        extreme: 'severe',
        very_high: 'severe',
        high: 'severe',
        medium: 'medium',
        low: 'good',
        '': '',
    },

    init() {
        this.loadRuns();
    },

    async loadRuns() {
        const sel = document.getElementById('run-selector');
        try {
            const res = await API.get('/graph/runs');
            if (res.success && res.data) {
                sel.innerHTML = '<option value="">— 选择 Run —</option>';
                res.data.forEach(r => {
                    const opt = document.createElement('option');
                    opt.value = r.run_id;
                    opt.textContent = `${r.run_id} (${r.type_count} 类型, ${r.updated_at?.slice(0, 16) || ''})`;
                    sel.appendChild(opt);
                });
            }
        } catch (e) {
            console.error('[Graph] loadRuns failed:', e);
        }
    },

    async loadGraph() {
        const runId = document.getElementById('run-selector').value;
        if (!runId) return;
        this.currentRunId = runId;
        document.getElementById('empty-state')?.remove();

        try {
            const res = await API.get(`/graph/${runId}`);
            if (res.success && res.data) {
                this.render(res.data.nodes, res.data.edges);
                document.getElementById('graph-stats').textContent =
                    `${res.data.nodes.length} 节点 · ${res.data.edges.length} 边`;
            }
        } catch (e) {
            console.error('[Graph] loadGraph failed:', e);
            document.getElementById('graph-container').innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-exclamation-triangle"></i>
                    <div class="hint">加载失败: ${e.message || e}</div>
                </div>`;
        }
    },

    render(nodes, edges) {
        const container = document.getElementById('graph-container');
        if (!container) return;

        if (this.chart) this.chart.dispose();
        this.chart = echarts.init(container, 'dark');

        // 归一化 centrality 到 [20, 60] 范围
        const cVals = nodes.map(n => n.centrality || 0).filter(v => v > 0);
        const cMin = cVals.length ? Math.min(...cVals) : 0;
        const cMax = cVals.length ? Math.max(...cVals) : 1;
        const cRange = cMax - cMin || 1;

        // 构建 categories
        const typeSet = new Set(nodes.map(n => n.node_type));
        const categories = Array.from(typeSet).map(t => ({
            name: t,
            itemStyle: { color: this.NODE_COLORS[t] || '#888' },
        }));

        // 节点数据
        const echartsNodes = nodes.map(n => ({
            id: n.id,
            name: n.label,
            value: n.label,
            category: n.node_type,
            symbolSize: 20 + ((n.centrality || 0) - cMin) / cRange * 40,
            itemStyle: {
                borderColor: n.severity === 'extreme' ? '#F46649' :
                             n.severity === 'very_high' ? '#ff7c5a' :
                             n.severity === 'high' ? '#ffa07a' : '#333',
                borderWidth: this.SEVERITY_BORDER[n.severity] || 0,
                // 瓶颈子类型特殊标记
                color: n.subtype === 'bottleneck'
                    ? '#F46649'
                    : (this.NODE_COLORS[n.node_type] || '#888'),
            },
            // 额外数据存到 raw 供点击使用
            raw: n,
        }));

        // 边数据
        const echartsEdges = edges.map(e => ({
            source: e.source_id,
            target: e.target_id,
            value: e.edge_type,
            lineStyle: {
                color: this.EDGE_COLORS[e.edge_type] || '#555',
                width: Math.max(1, Math.min(5, (e.weight || 1) * 2)),
                curveness: e.edge_type === 'belongs_to' ? 0.2 : 0.1,
                opacity: 0.6,
            },
            raw: e,
        }));

        const option = {
            title: { show: false },
            tooltip: {
                formatter: params => {
                    if (params.dataType === 'node') {
                        const n = params.data.raw;
                        let html = `<b>${n.label}</b><br/>`;
                        html += `<span style="color:${this.NODE_COLORS[n.node_type] || '#888'}">${n.node_type}</span>`;
                        if (n.subtype) html += ` · <span style="color:#F46649">${n.subtype}</span>`;
                        if (n.severity) html += ` · 严重度: <b>${n.severity}</b>`;
                        if (n.level) html += `<br/>层级: L${n.level}`;
                        if (n.industry) html += `<br/>产业: ${n.industry}`;
                        if (n.centrality) html += `<br/>中心性: ${n.centrality.toFixed(3)}`;
                        const props = n.properties || {};
                        if (props.bottleneck_narrative) html += `<br/><i>${props.bottleneck_narrative}</i>`;
                        if (props.investment_logic) html += `<br/><span style="color:#5AD8A6">→ ${props.investment_logic}</span>`;
                        return html;
                    }
                    if (params.dataType === 'edge') {
                        const e = params.data.raw;
                        return `<b>${e.edge_type}</b> · 权重: ${e.weight}<br/>${JSON.stringify(e.properties || {})}`;
                    }
                    return '';
                },
            },
            series: [{
                type: 'graph',
                layout: 'force',
                force: {
                    repulsion: 400,
                    edgeLength: [80, 250],
                    layoutAnimation: false,
                },
                roam: true,
                draggable: true,
                focusNodeAdjacency: true,
                categories: categories,
                data: echartsNodes,
                edges: echartsEdges,
                label: {
                    show: true,
                    position: 'right',
                    fontSize: 9,
                    color: '#aaa',
                    formatter: params => params.name.length > 12 ? params.name.slice(0, 12) + '…' : params.name,
                },
                edgeLabel: {
                    show: false,
                },
                lineStyle: {
                    color: 'source',
                },
                emphasis: {
                    focus: 'adjacency',
                    lineStyle: { width: 2 },
                },
                blur: {
                    opacity: 0.1,
                },
            }],
        };

        this.chart.setOption(option);

        // 节点点击事件
        this.chart.on('click', params => {
            if (params.dataType === 'node') {
                this.showNodeDetail(params.data.raw);
            }
        });

        // 窗口自适应
        window.addEventListener('resize', () => this.chart?.resize());
    },

    showNodeDetail(node) {
        const detailDiv = document.getElementById('node-detail');
        const edgeDiv = document.getElementById('edge-list');
        if (!detailDiv) return;

        const props = node.properties || {};
        let html = `<div style="margin-bottom:8px">`;
        html += `<b style="color:#fff;font-size:12px">${node.label}</b><br/>`;
        html += `<span style="color:${this.NODE_COLORS[node.node_type] || '#888'}">${node.node_type}</span>`;
        if (node.subtype) html += ` · <span style="color:#F46649">${node.subtype}</span>`;
        if (node.severity) html += ` · 严重度: <span class="val ${this.SEVERITY_CLASS[node.severity] || ''}">${node.severity}</span>`;
        html += '</div>';

        // 节点属性
        const fields = [
            { key: '产业', val: node.industry },
            { key: '层级', val: node.level ? `L${node.level}` : '' },
            { key: '中心性', val: node.centrality ? node.centrality.toFixed(4) : '' },
            { key: '瓶颈描述', val: props.bottleneck_narrative, cls: node.severity ? 'severe' : '' },
            { key: '国产替代率', val: props.china_substitution_rate },
            { key: '投资逻辑', val: props.investment_logic },
            { key: '稀缺排名', val: props.scarcity_rank ? `#${props.scarcity_rank}` : '' },
        ];
        fields.forEach(f => {
            if (!f.val) return;
            html += `<div class="field"><span class="key">${f.key}: </span><span class="val ${f.cls || ''}">${f.val}</span></div>`;
        });

        // 利润池
        if (props.profit_pool && Object.keys(props.profit_pool).length) {
            const pp = props.profit_pool;
            html += `<div class="field"><span class="key">利润份额: </span><span class="val">${pp.share_of_industry_profit || '?'}</span></div>`;
            html += `<div class="field"><span class="key">利润率: </span><span class="val">${pp.margin_level || '?'}</span></div>`;
            if (pp.pricing_power_narrative) {
                html += `<div class="field"><span class="key">定价权: </span><span class="val">${pp.pricing_power_narrative}</span></div>`;
            }
        }

        // 竞争格局
        if (props.competitive_landscape && Object.keys(props.competitive_landscape).length) {
            const cl = props.competitive_landscape;
            html += `<div class="field"><span class="key">竞争结构: </span><span class="val">${cl.structure || '?'}</span></div>`;
            if (cl.global_leaders?.length) {
                html += `<div class="field"><span class="key">全球龙头: </span><span class="val">${cl.global_leaders.join(', ')}</span></div>`;
            }
        }

        // 子工艺价值标签
        if (props.value_node_tags?.length) {
            html += `<div class="field" style="margin-top:6px"><span class="key">价值标签: </span>`;
            html += props.value_node_tags.map(t => `<span style="color:var(--accent-yellow);font-size:9px;background:rgba(246,189,22,0.1);padding:1px 4px;border-radius:2px;margin:1px 2px;display:inline-block">${t}</span>`).join('');
            html += '</div>';
        }

        detailDiv.innerHTML = html;

        // 关联边 — 需要在渲染时关联
        if (this.chart) {
            const allEdges = this.chart.getOption().series[0].edges || [];
            const relatedEdges = allEdges.filter(e =>
                (e.source === node.id || e.target === node.id) && e.raw
            );
            if (relatedEdges.length) {
                let ehtml = '';
                relatedEdges.forEach(e => {
                    const r = e.raw;
                    const otherId = r.source_id === node.id ? r.target_id : r.source_id;
                    // 从 nodes 找关联节点名
                    const echartsNodes = this.chart.getOption().series[0].data || [];
                    const otherNode = echartsNodes.find(n => n.id === otherId);
                    const otherName = otherNode ? otherNode.name : otherId.slice(0, 12);
                    const direction = r.source_id === node.id ? '→' : '←';
                    const color = this.EDGE_COLORS[r.edge_type] || '#555';
                    ehtml += `<div style="margin:2px 0;font-size:10px">`;
                    ehtml += `<span style="color:${color};font-weight:bold">${r.edge_type}</span> ${direction} `;
                    ehtml += `<span style="color:#ccc">${otherName}</span>`;
                    ehtml += ` <span style="color:var(--text-micro)">w=${r.weight}</span>`;
                    ehtml += '</div>';
                });
                edgeDiv.innerHTML = ehtml;
            } else {
                edgeDiv.innerHTML = '<span style="color:var(--text-micro)">无关联边</span>';
            }
        }
    },
};

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', () => GraphApp.init());
