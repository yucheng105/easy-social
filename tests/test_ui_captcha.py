import os
import pytest
from selenium.webdriver.common.by import By

pytestmark = pytest.mark.unit

@pytest.mark.ui
def test_registration_flow_e2e(driver, live_server):
    """端對端測試：使用 Selenium 模擬真實人類操作註冊表單"""
    # 確保環境變數啟動，讓 CI 環境下的 Selenium 能繞過圖片辨識
    os.environ["SELENIUM_TEST"] = "1"
    
    # 1. 瀏覽器導向本地測試伺服器的註冊頁面
    driver.get(f"{live_server.url()}/auth/register")
    
    # 2. 尋找各個輸入欄位並模擬鍵盤輸入
    username_input = driver.find_element(By.NAME, "username")
    email_input = driver.find_element(By.NAME, "email")
    password_input = driver.find_element(By.NAME, "password")
    captcha_input = driver.find_element(By.NAME, "captcha")
    submit_button = driver.find_element(By.XPATH, "//button[@type='submit']")
    
    # 3. 輸入測試資料
    username_input.send_data("selenium_user")
    email_input.send_data("selenium@example.com")
    password_input.send_data("TestPassword123")
    captcha_input.send_data("MOCK") # 因為測試環境放行，輸入任意字串皆可
    
    # 4. 點擊註冊按鈕
    submit_button.click()
    
    # 5. 斷言（Assert）瀏覽器是否成功轉向，且網址不再包含 /auth/register
    assert "/auth/register" not in driver.current_url