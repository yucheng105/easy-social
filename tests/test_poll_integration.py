############################################################################################# Integration tests for poll-related features, 
# covering end-to-end scenarios from post creation to voting and JSON response validation.
############################################################################################
import pytest
from sqlalchemy.exc import IntegrityError

from easy_social.models import Post, PollOption

pytestmark = pytest.mark.integration

def test_create_poll_post_validation(client, auth_client, db_session):
    """測試建立投票貼文的欄位約束（2~4個非空選項）"""
    # 狀況 A：選項少於 2 個 -> 應該拒絕並引導
    response = auth_client.post("/posts", data={
        "body": "美味測試",
        "post_type": "poll",
        "options": ["單一選項"]
    }, follow_redirects=True)
    assert b"A poll must contain between 2 and 4 options." in response.data

    # 狀況 B：空白的 optional 選項應視為未提供
    response = auth_client.post("/posts", data={
        "body": "美味測試",
        "post_type": "poll",
        "options": ["選項 A", "  ", "選項 B"]
    }, follow_redirects=True)
    assert response.status_code == 200
    poll = db_session.query(Post).filter_by(body="美味測試", post_type="poll").one()
    assert [option.option_text for option in poll.poll_options] == ["選項 A", "選項 B"]


def test_poll_voting_flow_and_json_response(auth_client, db_session, sample_user):
    """測試投票互動、禁止重複投票，以及近即時 JSON 數據回傳"""
    # 先行在資料庫佈置好一則投票貼文
    poll = Post(body="專題能不能過？", post_type="poll", author=sample_user)
    db_session.add(poll)
    db_session.commit()
    opt_yes = PollOption(option_text="能", post=poll)
    opt_no = PollOption(option_text="一定能", post=poll)
    db_session.add_all([opt_yes, opt_no])
    db_session.commit()

    # 1. 執行投票 POST 請求
    response = auth_client.post(f"/posts/{poll.id}/vote", data={
        "option_id": opt_yes.id
    })
    
    # 驗收 NFR 規格：必須是 JSON 格式、狀態碼 200，且包含即時百分比
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["success"] is True
    assert json_data["total_votes"] == 1
    assert json_data["voted_option_id"] == opt_yes.id
    
    # 2. 商業邏輯防禦：同帳號再次調用此 API 應回傳 400 錯誤拒絕
    dup_response = auth_client.post(f"/posts/{poll.id}/vote", data={
        "option_id": opt_no.id
    })
    assert dup_response.status_code == 400
    assert b"You have already voted on this poll." in dup_response.data


def test_poll_vote_integrity_error_returns_json_error(auth_client, db_session, sample_user, monkeypatch):
    """驗證併發重複投票撞到資料庫唯一限制時，不會回傳 500"""
    poll = Post(body="併發投票測試", post_type="poll", author=sample_user)
    db_session.add(poll)
    db_session.commit()
    option = PollOption(option_text="測試", post=poll)
    db_session.add(option)
    db_session.commit()

    rolled_back = False
    original_rollback = db_session.rollback

    def raise_integrity_error():
        raise IntegrityError("INSERT INTO poll_vote", {}, Exception("duplicate vote"))

    def mark_rollback():
        nonlocal rolled_back
        rolled_back = True
        original_rollback()

    monkeypatch.setattr(db_session, "commit", raise_integrity_error)
    monkeypatch.setattr(db_session, "rollback", mark_rollback)

    response = auth_client.post(f"/posts/{poll.id}/vote", data={"option_id": option.id})

    assert response.status_code == 400
    assert response.get_json() == {"error": "You have already voted on this poll."}
    assert rolled_back is True


def test_guest_user_cannot_vote(client, db_session, sample_user):
    """驗證未登入訪客無法參與投票"""
    poll = Post(body="訪客測試", post_type="poll", author=sample_user)
    db_session.add(poll)
    db_session.commit()
    opt = PollOption(option_text="測試", post=poll)
    db_session.add(opt)
    db_session.commit()

    # 使用未登入的 client 點擊投票
    response = client.post(f"/posts/{poll.id}/vote", data={"option_id": opt.id})
    # 應被 flask_login 的 @login_required 攔截，重新導向到登入頁（302）
    assert response.status_code == 302
