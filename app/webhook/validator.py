"""
Xác thực HMAC-SHA256 signature của GitHub webhook.

GitHub gửi header: X-Hub-Signature-256: sha256=<hex_digest>
Ta tính lại và so sánh để chắc chắn request thật sự từ GitHub.
"""

import hashlib
import hmac

from fastapi import HTTPException, Request

from app.config import settings


async def verify_github_signature(request: Request) -> bytes:
    """
    Đọc raw body, kiểm tra signature.
    Trả về raw body để handler tái sử dụng (body chỉ đọc được 1 lần).
    Raise 401 nếu sai signature.
    """
    body = await request.body()

    if not settings.github_webhook_secret:
        # Không config secret → bỏ qua xác thực (chỉ dùng khi dev local)
        return body

    signature_header = request.headers.get("X-Hub-Signature-256", "")
    if not signature_header.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256")

    expected_sig = "sha256=" + hmac.new(
        key=settings.github_webhook_secret.encode(),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, signature_header):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    return body
