"""
字节跳动校招JD抓取 - 快捷脚本
等价于: python job_tool/scraper.py bytedance -k "Agent" -c 后端
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from adapters.bytedance import ByteDanceAdapter

OUTPUT_DIR = r"D:\桌面\字节JD"
KEYWORDS = ["Agent", "RAG", "LLM应用", "大模型应用", "智能体", "AI应用"]

def main():
    adapter = ByteDanceAdapter(output_dir=OUTPUT_DIR)
    seen = set()
    for kw in KEYWORDS:
        results = adapter.fetch(keyword=kw, category="后端", max_results=500)
        for p in results:
            seen.add(p.id)
        print(f"  累计: {len(seen)} 个不重复岗位")
    print(f"\n总计 {len(seen)} 个, 已保存到 {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
