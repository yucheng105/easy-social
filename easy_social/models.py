from __future__ import annotations

from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, UniqueConstraint
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


followers = db.Table(
    "followers",
    db.Column("follower_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
    db.Column("followed_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
    db.Column(
        "created_at",
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    ),
    CheckConstraint("follower_id != followed_id", name="ck_follow_not_self"),
)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    bio = db.Column(db.String(280), nullable=False, default="")
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    posts = db.relationship("Post", back_populates="author", lazy="dynamic")
    comments = db.relationship("Comment", back_populates="author", lazy="dynamic")
    votes = db.relationship("PollVote", back_populates="user", lazy="dynamic")  # 新增：使用者的所有投票紀錄
    following = db.relationship(
        "User",
        secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref=db.backref("followers", lazy="dynamic"),
        lazy="dynamic",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def follow(self, user: "User") -> None:
        if user.id != self.id and not self.is_following(user):
            self.following.append(user)

    def unfollow(self, user: "User") -> None:
        if self.is_following(user):
            self.following.remove(user)

    def is_following(self, user: "User") -> bool:
        return (
            self.following.filter(followers.c.followed_id == user.id).count() > 0
        )


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False, default="")
    media_filename = db.Column(db.String(255), nullable=True)
    media_type = db.Column(db.String(20), nullable=True)
    
    # 🆕 擴充：識別貼文類型（'text'、'poll' 等），預設為一般文字貼文
    post_type = db.Column(db.String(20), nullable=False, default="text")
    
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    repost_of_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=True, index=True)

    author = db.relationship("User", back_populates="posts")
    comments = db.relationship(
        "Comment", back_populates="post", cascade="all, delete-orphan", lazy="dynamic"
    )
    repost_of = db.relationship("Post", remote_side=[id], backref="reposts")
    
    # 🆕 擴充：與投票選項、投票紀錄的關聯
    poll_options = db.relationship(
        "PollOption", back_populates="post", cascade="all, delete-orphan", order_by="PollOption.id"
    )
    poll_votes = db.relationship(
        "PollVote", back_populates="post", cascade="all, delete-orphan", lazy="dynamic"
    )

    __table_args__ = (
        CheckConstraint(
            "(length(body) > 0) OR (media_filename IS NOT NULL) OR (repost_of_id IS NOT NULL) OR (post_type = 'poll')",
            name="ck_post_has_content",
        ),
    )

    @property
    def display_post(self) -> "Post":
        return self.repost_of or self

    @property
    def is_repost(self) -> bool:
        return self.repost_of_id is not None

    # 🆕 擴充屬性：計算這則投票貼文的總票數
    @property
    def total_votes(self) -> int:
        if self.post_type != "poll":
            return 0
        return self.poll_votes.count()

    # 🆕 擴充方法：快速查詢某位使用者在這篇貼文投給了哪個選項（用於 UI 渲染已投票狀態）
    def get_user_voted_option_id(self, user_id: int | None) -> int | None:
        if not user_id or self.post_type != "poll":
            return None
        vote = self.poll_votes.filter_by(user_id=user_id).first()
        return vote.option_id if vote else None


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False, index=True)

    author = db.relationship("User", back_populates="comments")
    post = db.relationship("Post", back_populates="comments")

    __table_args__ = (
        UniqueConstraint("author_id", "post_id", "body", name="uq_comment_duplicate_guard"),
    )


# 🆕 新增：投票選項模型
class PollOption(db.Model):
    __tablename__ = "poll_option"
    
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False, index=True)
    option_text = db.Column(db.String(100), nullable=False)  # 限制選項文字長度

    post = db.relationship("Post", back_populates="poll_options")
    votes = db.relationship("PollVote", back_populates="option", cascade="all, delete-orphan", lazy="dynamic")

    # 🆕 擴充屬性：計算當前選項得票數
    @property
    def vote_count(self) -> int:
        return self.votes.count()

    # 🆕 擴充屬性：計算當前選項得票百分比（依據黛比給的公式）
    @property
    def vote_percentage(self) -> float:
        total = self.post.total_votes
        if total == 0:
            return 0.0
        # 四捨五入到小數點後第一位
        return round((self.vote_count / total) * 100, 1)


# 🆕 新增：投票紀錄模型（多對多關係的中介關聯實體）
class PollVote(db.Model):
    __tablename__ = "poll_vote"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False, index=True)
    option_id = db.Column(db.Integer, db.ForeignKey("poll_option.id"), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    user = db.relationship("User", back_populates="votes")
    post = db.relationship("Post", back_populates="poll_votes")
    option = db.relationship("PollOption", back_populates="votes")

    # 🔒 商業邏輯核心防禦：
    # 限制同一個 user_id 針對同一個 post_id 只能有一筆紀錄，終身只能投一次，徹底絕交洗票。
    __table_args__ = (
        UniqueConstraint("user_id", "post_id", name="uq_user_single_vote_per_poll"),
    )