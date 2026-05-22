# tests/test_unit_captcha.py
import pytest

pytestmark = pytest.mark.unit

def test_get_captcha_generates_image_and_session(client):
    """測試驗證碼路由是否正確生成圖片並寫入 Session"""
    response = client.get("/auth/captcha")
    
    # 1. 檢查 HTTP 狀態碼與快取機制
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/png"
    assert "no-store" in response.headers["Cache-Control"]
    
    # 2. 🛡️ 修正點：必須使用 session_transaction 內容管理器來存取 Session 記憶體
    with client.session_transaction() as sess:
        assert "captcha_text" in sess
        assert len(sess["captcha_text"]) == 4
        assert sess["captcha_text"].isupper() or sess["captcha_text"].isdigit()