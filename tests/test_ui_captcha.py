# tests/test_unit_captcha.py
import pytest
from flask import session

def test_get_captcha_generates_image_and_session(client):
    """測試驗證碼路由是否正確生成圖片並寫入 Session"""
    response = client.get("/auth/captcha")
    
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/png"
    assert "no-store" in response.headers["Cache-Control"]
    
    # 🔒 修正點：必須在 client.session_transaction() 的上下文中存取 session
    with client.session_transaction() as sess:
        assert "captcha_text" in sess
        assert len(sess["captcha_text"]) == 4
        assert sess["captcha_text"].isupper() or sess["captcha_text"].isdigit()