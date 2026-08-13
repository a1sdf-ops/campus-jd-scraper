#!/usr/bin/env python3
"""
通用校招JD抓取工具 — Multi-Company Job Scraper

用法:
  python scraper.py <公司> --keyword <关键词> [选项]
  python scraper.py batch <配置文件.json>

示例:
  python scraper.py bytedance --keyword "Agent" --category 后端
  python scraper.py bytedance --keyword "Agent" --city 北京 --output ./jd_output
  python scraper.py batch config.json

输出: 指定目录下的txt文件，每个JD一个文件。
     配合 filter_jds.py 做关键词筛选和评分排名。
"""
import sys, os, json, argparse
from adapters import ADAPTERS


def build_parser():
    p = argparse.ArgumentParser(description="通用校招JD抓取工具")
    sub = p.add_subparsers(dest="command")

    # ---- single company search ----
    for name, cls in ADAPTERS.items():
        sp = sub.add_parser(name, help=f"搜索{cls.display_name}校招岗位")
        sp.add_argument("--keyword", "-k", required=True, help="搜索关键词")
        sp.add_argument("--category", "-c", default="后端", help="岗位分类 (默认: 后端)")
        sp.add_argument("--city", default="", help="城市 (默认: 不限)")
        sp.add_argument("--limit", type=int, default=50, help="每次请求条数")
        sp.add_argument("--max", type=int, default=500, dest="max_results", help="最大抓取数")
        sp.add_argument("--output", "-o", default="./jd_output", help="输出目录")
        sp.add_argument("--delay", type=float, default=0.5, help="请求间隔(秒)")

    # ---- batch mode ----
    bp = sub.add_parser("batch", help="批量搜索 (从JSON配置文件)")
    bp.add_argument("config", help="JSON配置文件路径")
    bp.add_argument("--output", "-o", default="./jd_output", help="输出目录")

    return p


def run_single(company: str, args):
    adapter_cls = ADAPTERS[company]
    adapter = adapter_cls(output_dir=args.output, delay=args.delay)

    filters = {"category": args.category}
    if args.city:
        filters["city"] = args.city

    results = adapter.fetch(
        keyword=args.keyword,
        limit=args.limit,
        max_results=args.max_results,
        **filters,
    )
    print(f"\n完成! 共获取 {len(results)} 个JD, 保存到 {args.output}")


def run_batch(args):
    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    for entry in config.get("tasks", []):
        company = entry["company"]
        keywords = entry.get("keywords", [])
        category = entry.get("category", "后端")
        adapter_cls = ADAPTERS[company]
        adapter = adapter_cls(output_dir=args.output)

        for kw in keywords:
            adapter.fetch(keyword=kw, category=category)
            adapter._rate_limit()


def list_companies():
    print("支持的公司/平台:")
    for name, cls in ADAPTERS.items():
        print(f"  {name:<15} — {cls.display_name}")


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        list_companies()
        return

    if args.command == "batch":
        run_batch(args)
    elif args.command in ADAPTERS:
        run_single(args.command, args)
    else:
        print(f"未知命令: {args.command}")
        list_companies()


if __name__ == "__main__":
    main()
