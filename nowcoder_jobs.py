#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
牛客校招职位抓取 + 方向过滤 —— 找出「正在招 Agent / 大模型应用岗」的公司

数据源: https://www.nowcoder.com/jobs/school/jobs （牛客公开校招职位页）
服务端渲染 INITIAL_STATE 内嵌职位 JSON，纯标准库解析，无第三方依赖、无需登录。

为什么做这个:
  中厂不会在招聘平台打广告，但会在牛客校招频道发岗位。按「Agent应用/大模型应用」
  方向过滤，直接找出「哪些公司真在招这类岗」，而不是漫无目的地等大厂。

策略（诚实边界）:
  牛客 SSR 每页固定 20 条、无服务端分页、keyword 参数不严格过滤。
  所以抓多个关键词（Agent/大模型/AI应用…）合并去重，再在本地按方向关键词过滤。
  结果覆盖有限，但都是「当前在招」的真实职位，且完全公开、无对抗。

用法:
  python nowcoder_jobs.py                  # 默认抓内置关键词，过滤并输出
  python nowcoder_jobs.py --keywords "Agent 大模型" --out 结果.txt
  python nowcoder_jobs.py --all            # 不过滤，输出全部抓到的职位
"""
import re
import sys
import json
import io
import time
import urllib.request
import urllib.parse
import argparse
import datetime
from pathlib import Path

JOBS_URL = "https://www.nowcoder.com/jobs/school/jobs"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"

# ============================================================
#  方向关键词 —— 用户指定的筛选条件：Agent应用 / 大模型应用
#  匹配对象: 岗位名 + jobKeys 标签，均先转小写并去掉空格再匹配
# ============================================================
AGENT_KEYWORDS = [
    "agent", "智能体", "大模型", "llm", "ai应用", "aigc",
    "rag", "mcp", "ai开发", "人工智能",
]

# 标签（jobKeys）里只认强词——"agent" 作为标签太泛（很多后端岗都打），
# 只有岗位名里出现才作数，否则阿里的 Java 岗会因为标签带 agent 被误筛进来。
STRONG_KEYWORDS = ["大模型", "智能体", "llm", "ai应用", "aigc", "rag", "mcp", "人工智能"]

# 抓取时使用的搜索词（多个词合并可扩大覆盖面；SSR 每词只给 20 条）
SEARCH_KEYWORDS = ["Agent", "大模型", "AI应用"]


def norm(s):
    """小写 + 去空白，用于关键词匹配。"""
    return re.sub(r"\s+", "", (s or "").lower())


def fetch_jobs(keyword, timeout=20):
    """抓取牛客职位页，返回原始职位条目列表。"""
    req = urllib.request.Request(
        JOBS_URL + "?keyword=" + urllib.parse.quote(keyword),
        headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        html = resp.read().decode("utf-8", "replace")

    i = html.find("window.__INITIAL_STATE__")
    if i == -1:
        raise RuntimeError("页面结构变化：未找到 window.__INITIAL_STATE__")
    start = html.find("=", i) + 1
    depth = 0
    end = None
    in_str = False
    esc = False
    for j in range(start, len(html)):
        ch = html[j]
        if esc:
            esc = False
            continue
        if ch == chr(92):
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    if end is None:
        raise RuntimeError("页面结构变化：INITIAL_STATE JSON 未闭合")
    data = json.loads(html[start:end])

    jobs = []

    def find(o):
        if jobs:
            return
        if isinstance(o, dict):
            if "jobListData" in o:
                jobs.extend(o["jobListData"])
                return
            for v in o.values():
                find(v)
        elif isinstance(o, list):
            for v in o:
                find(v)

    find(data)
    return jobs


def extract(job):
    """从原始条目提取干净字段。"""
    return {
        "jobName": job.get("jobName") or "",
        "company": job.get("companyNameText") or job.get("companyName") or "",
        "city": ",".join(job.get("jobCityList") or []) or "",
        "salary": job.get("salaryShow") or job.get("salaryText") or "",
        "grad": job.get("graduationYear") or "",
        "career": job.get("careerJobName") or "",
        "keys": job.get("jobKeys") or "",
        "deliver_begin": job.get("deliverBegin") or "",
        "deliver_end": job.get("deliverEnd") or "",
    }


def is_relevant(job, keywords):
    """岗位名命中方向关键词，或标签/类别命中强词，即算相关。"""
    name = norm(job["jobName"])
    for kw in keywords:
        if kw in name:
            return True
    strong = norm(job["keys"]) + " " + norm(job["career"])
    for kw in STRONG_KEYWORDS:
        if kw in strong:
            return True
    return False


def render(results, all_flag):
    lines = []
    today = datetime.date.today().isoformat()
    lines.append("=" * 70)
    lines.append(f"牛客校招职位 · {today} · 方向: Agent应用/大模型应用")
    lines.append("=" * 70)
    lines.append(f"共 {len(results)} 个相关职位，涉及 {len({r['company'] for r in results})} 家公司")
    lines.append("")
    seen_company = set()
    for r in sorted(results, key=lambda x: (x["company"], x["jobName"])):
        mark = "" if r["company"] in seen_company else "★"
        seen_company.add(r["company"])
        lines.append(f"{mark} {r['company']}")
        lines.append(f"    岗位: {r['jobName']}")
        bits = [b for b in [r["city"], r["salary"], r["grad"], r["career"]] if b]
        lines.append(f"    城市: {r['city'] or '-'} | 届别: {r['grad'] or '-'}")
        if r["deliver_begin"] or r["deliver_end"]:
            lines.append(f"    投递: {r['deliver_begin']} ~ {r['deliver_end']}")
    return "\n".join(lines)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="牛客校招职位抓取 + 方向过滤")
    parser.add_argument("--keywords", default=None, help="方向关键词（空格分隔），默认 Agent应用/大模型应用")
    parser.add_argument("--out", default=None, help="结果输出文件")
    parser.add_argument("--all", action="store_true", help="输出全部抓到的职位（不过滤）")
    args = parser.parse_args()

    kw_list = [norm(k) for k in (args.keywords or " ".join(AGENT_KEYWORDS)).split()] if args.keywords else AGENT_KEYWORDS

    raw = []
    seen_ids = set()
    for kw in SEARCH_KEYWORDS:
        try:
            jobs = fetch_jobs(kw)
        except Exception as e:
            print(f"[警告] 关键词 {kw} 抓取失败: {e}")
            continue
        new = 0
        for j in jobs:
            jid = j.get("id")
            if jid in seen_ids:
                continue
            seen_ids.add(jid)
            raw.append(j)
            new += 1
        print(f"关键词 {kw}: 抓取 {len(jobs)} 条，新增 {new} 条")
        time.sleep(1)

    results = [extract(j) for j in raw]
    if not args.all:
        results = [r for r in results if is_relevant(r, kw_list)]
    if not results:
        print("没有命中方向的职位（或抓取失败），请检查网络")
        return

    text = render(results, args.all)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"\n已保存: {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
