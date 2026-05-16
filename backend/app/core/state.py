import asyncio

# 全局内存状态中心
# key: task_id (str), value: asyncio.Event()
task_stop_events = {}
