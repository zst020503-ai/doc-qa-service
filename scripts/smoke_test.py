#!/usr/bin/env python3
"""不依赖数据库的冒烟测试：验证应用能加载、路由已注册、参数校验与鉴权生效。

用途：交付前快速自检，或 CI 里当第一道关卡。
不覆盖数据库读写，那部分需要真实 PostgreSQL（见 scripts/eval_qa.py）。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import decode_access_token, create_access_token, hash_password, verify_password  # noqa: E402
from app.main import app  # noqa: E402
from app.providers.llm import embed_one, embed_texts  # noqa: E402
from app.services.ingest_service import split_text  # noqa: E402

client = TestClient(app)

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  ok   {name}")
    else:
        failed += 1
        print(f"  FAIL {name} {detail}")


def main() -> int:
    print("[1] 基础探针")
    response = client.get("/healthz")
    check("GET /healthz 返回 200", response.status_code == 200, response.text)
    check("healthz 内容正确", response.json() == {"status": "ok"}, response.text)

    response = client.get("/")
    check("GET / 返回服务信息", response.status_code == 200 and "docs" in response.json(), response.text)

    print("[2] 路由与 OpenAPI")
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"].keys())
    expected = {
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/me",
        "/api/v1/documents",
        "/api/v1/qa/ask",
        "/healthz",
    }
    missing = expected - paths
    check(f"路由齐全（共 {len(paths)} 条）", not missing, f"缺失 {missing}")

    print("[3] 参数校验")
    response = client.post("/api/v1/auth/register", json={"email": "x", "password": "1"})
    check("弱密码被拒绝 422", response.status_code == 422, response.text)

    print("[4] 鉴权")
    response = client.get("/api/v1/documents")
    check("无令牌访问返回 401", response.status_code == 401, response.text)
    check("错误体含 code 与 request_id", response.json().get("code") == "UNAUTHORIZED" and "request_id" in response.json(), response.text)
    check("响应头带 x-request-id", "x-request-id" in response.headers, str(response.headers))

    token = create_access_token(999, "user")
    payload = decode_access_token(token)
    check("JWT 签发与解析一致", payload["sub"] == "999" and payload["role"] == "user")

    print("[5] 口令哈希")
    stored = hash_password("hello-world-123")
    check("正确口令校验通过", verify_password("hello-world-123", stored))
    check("错误口令校验失败", not verify_password("hello-world-124", stored))
    check("哈希不重复（含随机盐）", hash_password("hello-world-123") != stored)

    print("[6] 切分与向量")
    chunks = split_text("a" * 1500, 800, 100)
    check("长文本切分为 2 段", len(chunks) == 2, str(len(chunks)))
    check("相邻段重叠 100 字符", chunks[1][:100] == chunks[0][-100:])

    vectors = embed_texts(["年假有几天", "住宿标准是多少"])
    check("向量维度一致", len(vectors[0]) == len(vectors[1]) == 1536, str(len(vectors[0])))
    near = sum(a * b for a, b in zip(embed_one("年假有几天"), embed_one("年假需要提前几天申请")))
    far = sum(a * b for a, b in zip(embed_one("年假有几天"), embed_one("服务器端口 80")))
    check(f"相关文本相似度高于无关文本（{near:.2f} > {far:.2f}）", near > far)

    print()
    print(f"通过 {passed} 项，失败 {failed} 项")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
