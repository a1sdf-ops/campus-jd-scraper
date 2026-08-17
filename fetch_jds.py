"""
字节跳动校招JD抓取 - 快捷脚本
等价于: python job_tool/scraper.py bytedance -k "Agent" -c 后端
关键词/分类从 config.json 读取，改关键词不用改代码。
"""
import sys, os, json

sys.path.insert(0, os.path.dirname(__file__))

from adapters.bytedance import ByteDanceAdapter

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.json")


def load_config():
    # 优先读私有 config.json；仓库里没有 config.json 时回退到模板示例
    for path in (CONFIG, os.path.join(HERE, "config.example.json")):
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        tasks = cfg.get("tasks") or []
        if tasks:
            t = tasks[0]
            return t.get("keywords") or [], t.get("category", "后端")
    print(f"[错误] 没找到可用配置。请复制 config.example.json 为 config.json，填入你的关键词后重试")
    sys.exit(1)


def main():
    keywords, category = load_config()
    OUTPUT_DIR = os.path.join(HERE, "jd_output")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    adapter = ByteDanceAdapter(output_dir=OUTPUT_DIR)
    seen = set()
    for kw in keywords:
        print(f"\n搜索: {kw} (分类: {category})")
        results = adapter.fetch(keyword=kw, category=category, max_results=500)
        for p in results:
            seen.add(p.id)
    print(f"\n总计 {len(seen)} 个不重复岗位, 已保存到 {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
