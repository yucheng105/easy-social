###########################################################################
# End to End test 
# simulating a real user 
#   - creating a poll post, 
#   - voting, and 
#   - seeing the progress bar update in real-time without page refresh.
###########################################################################
import pytest

pytestmark = pytest.mark.ui

playwright_sync_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is required for E2E browser tests"
)
Page = playwright_sync_api.Page
expect = playwright_sync_api.expect

def test_user_poll_interaction_lifecycle(page: Page, live_server):
    """模擬真實使用者建立投票貼文、點擊投票、即時看到進度條的完整生命週期"""
    
    # 1. 登入系統
    page.goto(f"{live_server.url}/login")
    page.fill("input[name='username']", "testuser")
    page.fill("input[name='password']", "password123")
    page.click("button[type='submit']")
    
    # 2. 來到主首頁，點擊切換為「投票貼文」模式並填寫內容
    page.goto(f"{live_server.url}/")
    page.click("#toggle-poll-mode-btn") # 假設你的前端切換按鈕識別字為此
    page.fill("textarea[name='body']", "大三下最硬的課？")
    
    # 動態填寫投票選項 (2個)
    page.fill("input[name='options'][index='0']", "系統開發與設計")
    page.fill("input[name='options'][index='1']", "高等資料庫")
    page.click("#submit-post-btn")
    
    # 3. 驗證貼文成功出現在 Feed 流中
    expect(page.locator(".post-body")).to_contain_text("大三下最硬的課？")
    
    # 驗收條件：未投票前，投票結果百分比應處於「隱藏」狀態
    expect(page.locator(".poll-results")).to_be_hidden()
    expect(page.locator(".vote-btn").first).to_be_visible()
    
    # 4. 關鍵互動：模擬使用者點選第一個選項進行投票
    page.click(".vote-btn:has-text('系統開發與設計')")
    
    # 驗收條件（近即時更新）：網頁不可重新整理，按鈕應自動轉化為百分比進度條
    expect(page.locator(".poll-results")).to_be_visible()
    expect(page.locator(".vote-btn")).to_be_hidden() # 按鈕應隱藏或停用
    
    # 驗收計算公式：此時該選項應顯示為 100% (1 票 / 總共 1 票)
    expect(page.locator(".option-percentage").first).to_contain_text("100%")
    expect(page.locator(".total-votes-count")).to_contain_text("Total Votes: 1")