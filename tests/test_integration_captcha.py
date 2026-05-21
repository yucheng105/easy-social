# tests/test_integration_captcha.py
import pytest
from easy_social.models import User

def test_register_validation_with_wrong_captcha(client, app):
    """整合測試：當驗證碼輸入錯誤時，應該拒絕註冊並回傳錯誤訊息"""
    client.get("/auth/register")
    
    with client.session_transaction() as sess:
        sess["captcha_text"] = "A1B2"
    
    response = client.post("/auth/register", data={
        "username": "testbot",
        "email": "bot@example.com",
        "password": "SecurePassword123",
        "captcha": "WONG" # 故意輸入錯誤
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b"Incorrect security CAPTCHA." in response.data
    
    # 🔒 修正點：資料庫查詢必須包在 app.app_context() 裡面
    with app.app_context():
        assert User.query.filter_by(username="testbot").first() is None


def test_register_validation_with_correct_captcha(client, app):
    """整合測試：當驗證碼完全正確時，應允許註冊並導向動態時報"""
    client.get("/auth/register")
    
    with client.session_transaction() as sess:
        sess["captcha_text"] = "X9Y8"
        
    response = client.post("/auth/register", data={
        "username": "realhuman",
        "email": "human@example.com",
        "password": "SecurePassword123",
        "captcha": "x9y8"
    }, follow_redirects=True)
    
    assert response.status_code == 200
    
    with app.app_context():
        assert User.query.filter_by(username="realhuman").first() is not None