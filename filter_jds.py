#!/usr/bin/env python3
"""
JD 筛选器 —— 5 维匹配度评分

针对「AI 应用 / Agent 工程岗」定制，把一个 JD 拆成 5 个维度打分，
替代「关键词黑白名单」的粗暴过滤，让匹配度可解释、可排序。

用法:
  python filter_jds.py                     # 默认读 ./jd_output，输出 ./jd_output_筛选结果
  python filter_jds.py -i 字节JD -o 筛选结果
  python filter_jds.py -i 字节JD --threshold 10

5 维评分:
  1. 方向命中 (0-5)   核心方向词命中数（Agent/RAG/MCP/大模型应用...）
  2. 工程信号 (0-3)   偏工程落地（含"工程化/落地/不涉及训练"等 +3）
  3. 专业弹性 (0-2)   "等相关专业"=2（非科班有机会）; "计算机相关专业"=0（硬卡）; 未提=1
  4. 技能命中 (0-10)  个人技术栈命中（权重=熟练度，封顶 10）
  5. 城市匹配 (0-2)   北京=2; 其他=0

  一票否决: 模型研究/训练、学历硬门槛(硕士+)、非应用方向(嵌入式/芯片/测试...)
"""
import os, shutil, argparse


# ===================== 一票否决（排除） =====================
# 这些方向不是 AI 应用工程岗，投了也是浪费
EXCLUDE_KEYWORDS = [
    # --- 模型研究 / 训练 ---
    "模型训练", "预训练", "微调", "fine-tun", "finetun",
    "RLHF", "SFT", "LoRA", "大模型训练", "模型研发",
    "研究员", "算法工程师", "NLP算法", "CV算法", "语音算法",
    "机器学习算法", "深度学习算法", "强化学习",
    # --- AI Infra / 底层 ---
    "AI Infra", "AI infra", "推理引擎", "训练引擎", "训练框架",
    "GPU", "CUDA", "算子", "分布式训练", "高性能计算",
    "模型部署", "推理优化", "推理加速", "模型加速",
    "深度学习框架", "神经网络", "编译器", "MLIR", "TVM",
    "模型量化", "模型压缩", "剪枝", "蒸馏",
    # --- 学历硬门槛 ---
    "硕士及以上学历", "硕士及以上", "硕士研究生及以上",
    "博士研究生学历", "博士学位", "博士及以上学历",
    # --- 非应用方向 ---
    "全栈", "客户端开发", "可观测", "基础架构", "云原生基础设施",
    "消息队列", "ACM/ICPC", "ACM-ICPC", "ICPC", "竞赛获奖",
    "音视频", "图形学", "渲染", "嵌入式", "驱动", "固件",
    "芯片", "硬件", "安全", "渗透", "逆向", "测试开发",
    "测试工程师", "运维", "SRE",
    # --- 数据工程（非应用） ---
    "数据标注", "数据清洗", "数据采集",
]


# ===================== 5 维评分 =====================

# 维度1: 方向命中 —— 岗位是不是 AI 应用 / Agent 方向（每命中 +1，封顶 5）
DIRECTION_KEYWORDS = [
    "Agent", "智能体", "RAG", "检索增强", "MCP",
    "大模型应用", "LLM应用", "AI应用", "研发效能", "Coding Agent",
    "工作流编排",
]

# 维度2: 工程信号 —— 偏工程落地（而非模型研究），命中任一 +3
ENGINEERING_KEYWORDS = [
    "不涉及", "工程化", "落地", "工具链",
    "API调用", "应用开发", "应用落地",
]

# 维度3: 专业弹性 —— "等相关专业" 表示非科班有机会
MAJOR_FLEXIBLE = "等相关专业"     # 有"等"字 → 机械等专业有机会
MAJOR_STRICT = "计算机相关专业"    # 无"等"字 → 硬卡科班

# 维度4: 技能命中 —— 个人技术栈，权重 = 熟练度
SKILL_KEYWORDS = {
    "Claude Code": 3, "Cursor": 3, "Codex": 3,       # AI Coding 工具（核心优势）
    "LangGraph": 3, "MCP": 3, "RAG": 3,               # Agent 工程框架
    "LangChain": 2, "ChromaDB": 2, "Docker": 2, "CI/CD": 2,
    "Python": 1, "Go": 1, "Golang": 1, "FastAPI": 1, "SSE": 1,
}

# 维度5: 城市 —— 北京优先
PREFERRED_CITY = "北京"


def load_jds(directory):
    """加载目录下所有 JD 的 txt 文件"""
    jds = []
    if not os.path.exists(directory):
        print(f"[错误] 目录不存在: {directory}")
        return jds
    for filename in os.listdir(directory):
        if filename.endswith(".txt"):
            filepath = os.path.join(directory, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            jds.append({"filename": filename, "content": content})
    return jds


# 否定词：排除词前面出现这些词时，表示「不做这件事」，不应触发排除
# 例：「不涉及模型训练」是工程岗的正面信号，不能因「模型训练」被误杀
NEGATIONS = ["不涉及", "无需", "无须", "不包含", "不要求",
             "不包括", "不做", "不负责", "不需要", "不参与"]


def _is_negated(text, idx):
    """检查 keyword 命中位置前 6 个字符内是否有否定词"""
    window = text[max(0, idx - 6):idx]
    return any(neg in window for neg in NEGATIONS)


def should_exclude(content):
    """一票否决检查，返回 (是否排除, 触发词)。否定语境下的关键词不触发排除。"""
    content_lower = content.lower()
    for kw in EXCLUDE_KEYWORDS:
        kl = kw.lower()
        start = 0
        while True:
            idx = content_lower.find(kl, start)
            if idx == -1:
                break
            if not _is_negated(content_lower, idx):
                return True, kw
            start = idx + len(kl)
    return False, None


def score_dimensions(content):
    """5 维打分，返回 (总分, 各维度明细)"""
    content_lower = content.lower()

    # 维度1: 方向命中
    direction_hits = [kw for kw in DIRECTION_KEYWORDS if kw.lower() in content_lower]
    direction_score = min(len(direction_hits), 5)

    # 维度2: 工程信号
    engineering_hits = [kw for kw in ENGINEERING_KEYWORDS if kw.lower() in content_lower]
    engineering_score = 3 if engineering_hits else 0

    # 维度3: 专业弹性
    if MAJOR_FLEXIBLE in content_lower:
        major_score = 2
        major_note = "等相关专业"
    elif MAJOR_STRICT in content_lower:
        major_score = 0
        major_note = "计算机相关专业(硬卡)"
    else:
        major_score = 1
        major_note = "未提专业要求"

    # 维度4: 技能命中
    skill_hits = {kw: w for kw, w in SKILL_KEYWORDS.items() if kw.lower() in content_lower}
    skill_score = min(sum(skill_hits.values()), 10)

    # 维度5: 城市
    city_score = 2 if PREFERRED_CITY in content else 0

    total = direction_score + engineering_score + major_score + skill_score + city_score

    detail = {
        "方向命中": f"{direction_score}/5",
        "工程信号": f"{engineering_score}/3",
        "专业弹性": f"{major_score}/2 ({major_note})",
        "技能命中": f"{skill_score}/10",
        "城市匹配": f"{city_score}/2",
    }
    return total, detail, direction_hits, list(skill_hits.keys())


def build_report(jd, total, detail):
    """生成 JD 文件末尾的评分报告"""
    lines = [f"\n\n{'='*40}", f"[总分]: {total}/22"]
    for dim, score in detail.items():
        lines.append(f"[{dim}]: {score}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="JD 筛选器 —— 5 维匹配度评分")
    parser.add_argument("-i", "--input", default="./jd_output", help="JD 输入目录 (默认 ./jd_output)")
    parser.add_argument("-o", "--output", default="./jd_output_筛选结果", help="结果输出目录")
    parser.add_argument("--threshold", type=int, default=8, help="高匹配分数线 (默认 8)")
    args = parser.parse_args()

    jds = load_jds(args.input)
    if not jds:
        return
    print(f"读取到 {len(jds)} 个 JD")

    if os.path.exists(args.output):
        shutil.rmtree(args.output)
    os.makedirs(args.output)

    high_dir = os.path.join(args.output, "1-高匹配")
    cand_dir = os.path.join(args.output, "2-候选")
    excl_dir = os.path.join(args.output, "3-已排除")

    excluded, scored = [], []
    for jd in jds:
        is_excluded, reason = should_exclude(jd["content"])
        if is_excluded:
            excluded.append((jd, reason))
        else:
            total, detail, d_hits, s_hits = score_dimensions(jd["content"])
            jd["total"] = total
            jd["detail"] = detail
            scored.append(jd)

    scored.sort(key=lambda x: x["total"], reverse=True)

    # 保存
    for jd in scored:
        report = build_report(jd, jd["total"], jd["detail"])
        dest_dir = high_dir if jd["total"] >= args.threshold else cand_dir
        os.makedirs(dest_dir, exist_ok=True)
        fname = f"[{jd['total']:02d}分] {jd['filename']}"
        with open(os.path.join(dest_dir, fname), "w", encoding="utf-8") as f:
            f.write(jd["content"] + report)

    for jd, reason in excluded:
        os.makedirs(excl_dir, exist_ok=True)
        with open(os.path.join(excl_dir, jd["filename"]), "w", encoding="utf-8") as f:
            f.write(jd["content"] + f"\n\n[排除原因]: {reason}")

    # 控制台汇总
    high = [j for j in scored if j["total"] >= args.threshold]
    print(f"\n{'='*50}")
    print(f"  筛选 + 评分完成")
    print(f"{'='*50}")
    print(f"  高匹配 (≥{args.threshold}分): {len(high)} 个")
    print(f"  候选    (<{args.threshold}分): {len(scored)-len(high)} 个")
    print(f"  已排除: {len(excluded)} 个")

    if high:
        print(f"\n  === 高匹配排名 ===")
        for i, jd in enumerate(high[:20], 1):
            title = jd["filename"]
            print(f"  #{i} [{jd['total']:02d}分] {title}")
            print(f"      {jd['detail']['方向命中']} | {jd['detail']['工程信号']} | "
                  f"{jd['detail']['专业弹性']} | {jd['detail']['技能命中']}")

    print(f"\n结果已保存到: {args.output}")


if __name__ == "__main__":
    main()
