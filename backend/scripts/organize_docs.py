import os
import shutil

base_path = r"e:\workspace\AIResearch\AIStock_Pro"
docs_path = os.path.join(base_path, "docs")
artifact_path = r"C:\Users\86157\.gemini\antigravity\brain\aa4c6a30-932a-49b4-ac88-0af84e47c8f5\task_system_v5_spec.md"

folders = [
    "01_Requirements",
    "02_Architecture",
    "03_API_Specifications",
    "04_Frontend_UI",
    "05_Engineering",
    "06_Quant_Research",
    "Archive"
]

def organize():
    # 1. 创建目录
    for f in folders:
        p = os.path.join(docs_path, f)
        if not os.path.exists(p):
            os.makedirs(p)
            print(f"Created: {p}")

    # 2. 移动旧文档 (归类)
    moves = {
        "architecture_v2.md": "02_Architecture",
        "engineering_standards.md": "05_Engineering",
        "data_sync_spec.md": "Archive",
        "roadmap_v2.md": "Archive"
    }

    for src_name, dst_folder in moves.items():
        src = os.path.join(docs_path, src_name)
        dst = os.path.join(docs_path, dst_folder, src_name)
        if os.path.exists(src):
            shutil.move(src, dst)
            print(f"Moved: {src_name} -> {dst_folder}")

    # 3. 将 V5.0 规格书正式存入项目
    if os.path.exists(artifact_path):
        # 存入 Requirements
        shutil.copy(artifact_path, os.path.join(docs_path, "01_Requirements", "2026-05-16_Task_V5_Spec.md"))
        # 存入 Architecture (作为设计基准)
        shutil.copy(artifact_path, os.path.join(docs_path, "02_Architecture", "Task_V5_Engine_Design.md"))
        print(f"Persisted: Task V5 Specs")

if __name__ == "__main__":
    organize()
