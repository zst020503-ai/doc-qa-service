#!/usr/bin/env python3
"""问答质量评测：跑一遍测试问题集，输出命中率、误拒率、编造率。

用法:
    python scripts/eval_qa.py --base-url http://localhost
    python scripts/eval_qa.py --base-url http://localhost --top-k 5 --report docs/eval-report.md
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
QUESTIONS = ROOT / "tests" / "questions.jsonl"

EMAIL = "eval@example.com"
PASSWORD = "eval-password-123"


def load_questions() -> list[dict]:
    items = []
    with QUESTIONS.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def get_token(client: httpx.Client, base_url: str) -> str:
    payload = {"email": EMAIL, "password": PASSWORD}
    response = client.post(f"{base_url}/api/v1/auth/register", json=payload)
    if response.status_code == 409:
        response = client.post(f"{base_url}/api/v1/auth/login", json=payload)
    response.raise_for_status()
    return response.json()["access_token"]


def upload_samples(client: httpx.Client, base_url: str, headers: dict) -> None:
    existing = client.get(f"{base_url}/api/v1/documents", headers=headers, params={"limit": 100})
    existing.raise_for_status()
    filenames = {item["filename"] for item in existing.json()["items"]}

    for path in sorted(SAMPLES.glob("*")):
        if path.name in filenames:
            continue
        with path.open("rb") as handle:
            response = client.post(
                f"{base_url}/api/v1/documents",
                headers=headers,
                files={"file": (path.name, handle, "text/markdown")},
            )
        response.raise_for_status()
        print(f"  上传 {path.name} -> id={response.json()['id']}")


def wait_ready(client: httpx.Client, base_url: str, headers: dict, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"{base_url}/api/v1/documents", headers=headers, params={"limit": 100})
        response.raise_for_status()
        items = response.json()["items"]
        pending = [item for item in items if item["status"] in ("pending", "processing")]
        if not pending:
            failed = [item for item in items if item["status"] == "failed"]
            if failed:
                for item in failed:
                    print(f"  [警告] {item['filename']} 处理失败: {item['error']}")
            return
        time.sleep(2)
    raise TimeoutError("文档索引超时，检查 worker 是否在运行")


def evaluate(client: httpx.Client, base_url: str, headers: dict, top_k: int | None) -> list[dict]:
    results = []
    for item in load_questions():
        payload = {"question": item["question"]}
        if top_k:
            payload["top_k"] = top_k
        started = time.perf_counter()
        response = client.post(f"{base_url}/api/v1/qa/ask", headers=headers, json=payload)
        cost_ms = int((time.perf_counter() - started) * 1000)
        response.raise_for_status()
        data = response.json()

        blob = data["answer"] + " " + " ".join(c["snippet"] for c in data["citations"])
        hit = all(keyword in blob for keyword in item["expect_keywords"]) if item["expect_keywords"] else None

        results.append(
            {
                "id": item["id"],
                "question": item["question"],
                "should_answer": item["should_answer"],
                "refused": data["refused"],
                "hit": hit,
                "latency_ms": data["elapsed_ms"],
                "wall_ms": cost_ms,
                "top_score": data["citations"][0]["score"] if data["citations"] else 0.0,
            }
        )
        flag = "拒答" if data["refused"] else ("命中" if hit else "未命中")
        print(f"  {item['id']:>2}. [{flag}] {item['question']}")
    return results


def summarize(results: list[dict]) -> dict:
    answerable = [r for r in results if r["should_answer"]]
    unanswerable = [r for r in results if not r["should_answer"]]

    answered = [r for r in answerable if not r["refused"]]
    hits = [r for r in answered if r["hit"]]
    wrong_refusal = [r for r in answerable if r["refused"]]
    hallucination = [r for r in unanswerable if not r["refused"]]

    latencies = [r["latency_ms"] for r in results]
    return {
        "total": len(results),
        "answerable": len(answerable),
        "unanswerable": len(unanswerable),
        "answered": len(answered),
        "hits": len(hits),
        "hit_rate": len(hits) / len(answerable) if answerable else 0.0,
        "wrong_refusal_rate": len(wrong_refusal) / len(answerable) if answerable else 0.0,
        "hallucination_rate": len(hallucination) / len(unanswerable) if unanswerable else 0.0,
        "refusal_accuracy": 1 - (len(hallucination) / len(unanswerable)) if unanswerable else 0.0,
        "latency_avg_ms": int(statistics.mean(latencies)) if latencies else 0,
        "latency_p95_ms": int(sorted(latencies)[int(len(latencies) * 0.95) - 1]) if latencies else 0,
    }


def render(summary: dict, results: list[dict]) -> str:
    lines = [
        "## 评测结果",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        f"| 测试问题数 | {summary['total']}（可答 {summary['answerable']} / 不可答 {summary['unanswerable']}） |",
        f"| 命中率 hit@k | {summary['hit_rate']:.1%} |",
        f"| 误拒率（该答却拒答） | {summary['wrong_refusal_rate']:.1%} |",
        f"| 编造率（该拒却回答） | {summary['hallucination_rate']:.1%} |",
        f"| 拒答准确率 | {summary['refusal_accuracy']:.1%} |",
        f"| 平均响应 | {summary['latency_avg_ms']} ms |",
        f"| P95 响应 | {summary['latency_p95_ms']} ms |",
        "",
        "## 逐题明细",
        "",
        "| # | 问题 | 应回答 | 实际拒答 | 命中 | top1 相似度 | 耗时(ms) |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in results:
        hit = "-" if row["hit"] is None else ("是" if row["hit"] else "否")
        lines.append(
            f"| {row['id']} | {row['question']} | {'是' if row['should_answer'] else '否'} "
            f"| {'是' if row['refused'] else '否'} | {hit} | {row['top_score']:.3f} | {row['latency_ms']} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost")
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--report", default=None, help="把 markdown 结果写到文件")
    parser.add_argument(
        "--max-hallucination",
        type=float,
        default=0.10,
        help="编造率超过此值返回非 0；CI 里只验证链路时传 1.0",
    )
    parser.add_argument("--skip-upload", action="store_true")
    args = parser.parse_args()

    with httpx.Client(timeout=120.0) as client:
        token = get_token(client, args.base_url)
        headers = {"Authorization": f"Bearer {token}"}

        if not args.skip_upload:
            print("准备样例文档...")
            upload_samples(client, args.base_url, headers)
        print("等待索引完成...")
        wait_ready(client, args.base_url, headers)

        print("开始评测...")
        results = evaluate(client, args.base_url, headers, args.top_k)

    summary = summarize(results)
    report = render(summary, results)
    print()
    print(report)

    if args.report:
        Path(args.report).write_text(report, encoding="utf-8")
        print(f"\n报告已写入 {args.report}")

    return 0 if summary["hallucination_rate"] <= args.max_hallucination else 1


if __name__ == "__main__":
    sys.exit(main())
