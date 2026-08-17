#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
牛客校招日程抓取 + 画像推荐 —— 自动收集各公司秋招时间表

数据源: https://www.nowcoder.com/jobs/school/schedule （牛客公开校招日程页）
服务端渲染的 window.__INITIAL_STATE__ 内嵌了日程 JSON，直接解析，无需 JS/无需登录。
纯标准库（urllib），无第三方依赖，无反爬对抗。

为什么做这个:
  各公司秋招开始时间分散在各家官网/公众号，人工一个个查极费时间。
  牛客是公开聚合源，一次拿到 公司+网申起止+内推码+网申链接+城市+方向，
  再按「我的画像」（方向/城市/专业弹性/内推码）排序推荐。

用法:
  python nowcoder_schedule.py                  # 抓取 + 画像推荐，输出到控制台并落盘快照
  python nowcoder_schedule.py --out 日程.txt   # 指定输出文件
  python nowcoder_schedule.py --all            # 显示全部公司（不做画像过滤）
"""
import re
import sys
import json
import io
import urllib.request
import argparse
import datetime
from pathlib import Path

SCHEDULE_URL = "https://www.nowcoder.com/jobs/school/schedule"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
SNAPSHOT_GLOB = "_牛客日程_*.txt"   # 历史快照，用于对比「今天新开了哪些公司」

# ============================================================
#  个人画像 —— 按需修改
# ============================================================
PROFILE = {
    "name": "陈磊",
    # 目标方向：牛客日程表 careerNameList 里的标签
    "direction_keywords": ["人工智能/算法", "后端开发", "研发工程师", "测试"],
    # 期望城市
    "cities": ["北京"],
    # 专业弹性：方向列表里出现"机械"，说明机械专业有对应岗位（非科班友好信号）
    "major_tag": "机械",
}

# ============================================================
#  抓取与解析
# ============================================================

def fetch_schedule(timeout=20):
    """抓取牛客日程页，返回 scheduleData dict（含 datas / totalPage / currentPage）。"""
    req = urllib.request.Request(
        SCHEDULE_URL,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        html = resp.read().decode("utf-8", "replace")

    i = html.find("window.__INITIAL_STATE__")
    if i == -1:
        raise RuntimeError("页面结构变化：未找到 window.__INITIAL_STATE__")
    start = html.find("=", i) + 1

    # 平衡括号定位 JSON 对象
    depth = 0
    end = None
    in_str = False
    esc = False
    for j in range(start, len(html)):
        ch = html[j]
        if esc:
            esc = False
            continue
        if ch == chr(92):   # backslash
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

    # 递归查找 scheduleData（不依赖 app 里的数字 key，防页面 key 漂移）
    schedule = {}

    def find(o):
        nonlocal schedule
        if schedule:
            return
        if isinstance(o, dict):
            if "scheduleData" in o:
                schedule = o["scheduleData"]
                return
            for v in o.values():
                find(v)
        elif isinstance(o, list):
            for v in o:
                find(v)

    find(data)
    if not schedule:
        raise RuntimeError("页面结构变化：未找到 scheduleData")
    return schedule


def parse_dates(entry):
    """把 epoch 毫秒转成 YYYY-MM-DD，返回 (begin, end)。非法值返回 (None, None)。"""

    def conv(ms):
        try:
            return datetime.datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            return None

    return conv(entry.get("wangshenBeginDate")), conv(entry.get("wangshenEndDate"))


def status_of(begin, end, end_flag, supplement_begin, supplement_end):
    """按当前时间判断网申状态: 未开始 / 进行中 / 已结束 / 补录中。"""
    today = datetime.date.today()
    now = datetime.datetime.now()

    def to_date(v):
        if v is None:
            return None
        if isinstance(v, (int, float)):  # epoch 毫秒
            return datetime.datetime.fromtimestamp(int(v) / 1000).date()
        try:
            return datetime.datetime.strptime(str(v), "%Y-%m-%d").date()
        except ValueError:
            return None

    b, e = to_date(begin), to_date(end)
    if b and e:
        if today < b:
            return "未开始"
        if today > e:
            return "已结束"
    # 补录期单独看
    sb, se = to_date(supplement_begin), to_date(supplement_end)
    if sb and se and sb <= now.date() <= se:
        return "补录中"
    if end_flag == 1:
        return "已结束"
    return "进行中"


def rank(entries, profile):
    """画像打分排序。返回 [(entry, score, reasons), ...]，按分降序。"""
    dir_kws = profile["direction_keywords"]
    cities = profile["cities"]
    major = profile["major_tag"]

    ranked = []
    for e in entries:
        careers = e.get("careerNameList") or []
        cities_hit = [c for c in cities if c in (e.get("cityList") or [])]
        dir_hit = [kw for kw in dir_kws if kw in careers]
        major_hit = major in careers
        has_code = bool(e.get("referralCode"))

        score = 0
        reasons = []
        if dir_hit:
            score += 3
            reasons.append("方向✓(" + "/".join(dir_hit) + ")")
        if cities_hit:
            score += 2
            reasons.append("城市✓")
        if major_hit:
            score += 2
            reasons.append("专业弹性✓")
        if has_code:
            score += 1
            reasons.append("有内推码")

        # 网申状态：未开始/进行中 可投 → 加分；已结束 → 一票否决
        begin, end = parse_dates(e)
        st = status_of(begin, end, e.get("end"), e.get("supplementBeginDate"), e.get("supplementEndDate"))
        if st == "已结束":
            score = -1
            reasons.append("已结束")
        elif st == "未开始":
            score += 2
            reasons.append("即将开始")
        else:
            score += 1
            reasons.append("进行中")

        ranked.append((e, score, reasons, begin, end, st))

    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked


def render(ranked, all_flag):
    lines = []
    today = datetime.date.today().isoformat()
    lines.append("=" * 70)
    lines.append(f"牛客校招日程 · {today} · 共 {len(ranked)} 家")
    lines.append("=" * 70)
    for e, score, reasons, begin, end, st in ranked:
        if not all_flag and score < 3:
            continue
        name = e.get("name") or "?"
        flag = "" if score >= 3 else "  [低于推荐线]"
        lines.append("")
        lines.append(f"■ {name}  (分{score}){flag}")
        lines.append(f"  批次: {e.get('batchName')} | 状态: {st} | {begin or '?'} ~ {end or '?'}")
        city = ",".join(e.get("cityList") or []) or "-"
        career = ",".join(e.get("careerNameList") or []) or "-"
        lines.append(f"  城市: {city}")
        lines.append(f"  方向: {career[:150]}")
        lines.append(f"  网申: {e.get('customWangshenLink') or '（未提供）'}")
        if reasons:
            lines.append(f"  推荐: {' | '.join(reasons)}")
    return "\n".join(lines)


def diff_with_previous(entries, snapshot_dir):
    """和最近一次快照对比，找出「新进入进行中/未开始状态」的公司（即今天新开的）。"""
    snaps = sorted(snapshot_dir.glob(SNAPSHOT_GLOB)) if snapshot_dir.exists() else []
    if not snaps:
        return []
    try:
        prev = set()
        for line in snaps[-1].read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("■ "):
                prev.add(line[2:].split("  ")[0])
    except OSError:
        return []
    cur = set(e.get("name") or "" for e in entries)
    return sorted(cur - prev)


def main():
    parser = argparse.ArgumentParser(description="牛客校招日程抓取 + 画像推荐")
    parser.add_argument("--out", default=None, help="结果输出文件（默认输出到控制台 + 自动落盘快照）")
    parser.add_argument("--all", action="store_true", help="显示全部公司（不按画像过滤）")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    try:
        sched = fetch_schedule()
    except Exception as e:
        print(f"[错误] 抓取失败: {e}")
        sys.exit(1)

    entries = sched.get("datas") or []
    if not entries:
        print("[错误] 日程数据为空，可能页面结构已变化")
        sys.exit(1)

    print(f"共 {len(entries)} 家（牛客日程首页，按相关度排序）")

    ranked = rank(entries, PROFILE)
    text = render(ranked, args.all)

    # 快照落盘（用于下次对比新开公司）
    snapshot_dir = Path(__file__).parent
    today = datetime.date.today().strftime("%Y%m%d")
    snap_path = snapshot_dir / f"_牛客日程_{today}.txt"

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"\n已保存: {args.out}")
    else:
        print(text)
        snap_path.write_text(text, encoding="utf-8")
        print(f"\n快照已保存: {snap_path}")

    # 对比上次快照，提示新开公司
    new_ones = diff_with_previous(entries, snapshot_dir)
    if new_ones:
        print("\n[新增] 相比上次快照，今天新出现的公司: " + ", ".join(new_ones))
    else:
        print("\n[对比] 无新增公司（或首次运行）")


if __name__ == "__main__":
    main()
