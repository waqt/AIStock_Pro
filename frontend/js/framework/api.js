/**
 * API 通信层 — 统一 fetch 封装
 */
const API_BASE = '/api';

const API = {
    async get(path) {
        const res = await fetch(`${API_BASE}${path}`);
        if (!res.ok) throw new Error(`GET ${path}: ${res.status}`);
        return res.json();
    },
    async post(path, body = {}) {
        const res = await fetch(`${API_BASE}${path}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (!res.ok) throw new Error(`POST ${path}: ${res.status}`);
        return res.json();
    },
    async del(path) {
        const res = await fetch(`${API_BASE}${path}`, { method: 'DELETE' });
        if (!res.ok) throw new Error(`DELETE ${path}: ${res.status}`);
        return res.json();
    }
};
