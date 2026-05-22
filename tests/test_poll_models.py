####################################################################################
# Unit tests for PollOption and PollVote models, 
# focusing on percentage calculation and database-level duplicate vote protection.
####################################################################################
import pytest
from easy_social.models import Post, PollOption, PollVote
from easy_social.extensions import db
from sqlalchemy.exc import IntegrityError

def test_poll_option_percentage_calculation(app, db_session, sample_user):
    """測試投票百分比計算與防範除以 0 錯誤"""
    # 1. 建立一則投票貼文
    poll_post = Post(body="今天晚餐吃什麼？", post_type="poll", author=sample_user)
    db_session.add(poll_post)
    db_session.commit()

    # 2. 建立兩個選項
    opt1 = PollOption(option_text="火鍋", post=poll_post)
    opt2 = PollOption(option_text="燒肉", post=poll_post)
    db_session.add_all([opt1, opt2])
    db_session.commit()

    # 驗收條件：尚未有人投票時，所有選項顯示 0.0%，且不可發生除以 0 錯誤
    assert poll_post.total_votes == 0
    assert opt1.vote_percentage == 0.0
    assert opt2.vote_percentage == 0.0

    # 3. 模擬投票：投給選項 1 一票
    vote1 = PollVote(user_id=sample_user.id, post_id=poll_post.id, option_id=opt1.id)
    db_session.add(vote1)
    db_session.commit()

    # 驗收條件：即時更新計算結果
    assert poll_post.total_votes == 1
    assert opt1.vote_percentage == 100.0
    assert opt2.vote_percentage == 0.0


def test_database_level_duplicate_vote_protection(app, db_session, sample_user):
    """測試資料庫層級的複合唯一約束 (UniqueConstraint)，防止重複洗票"""
    poll_post = Post(body="支援終身只能投一次嗎？", post_type="poll", author=sample_user)
    db_session.add(poll_post)
    db_session.commit()

    opt = PollOption(option_text="支援", post=poll_post)
    db_session.add(opt)
    db_session.commit()

    # 第一票：正常寫入
    vote1 = PollVote(user_id=sample_user.id, post_id=poll_post.id, option_id=opt.id)
    db_session.add(vote1)
    db_session.commit()

    # 第二票：同一個 user_id 對同一個 post_id 企圖投第二次
    vote2 = PollVote(user_id=sample_user.id, post_id=poll_post.id, option_id=opt.id)
    db_session.add(vote2)
    
    # 預期會因為 UniqueConstraint 噴出 IntegrityError
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()