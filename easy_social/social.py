from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for, jsonify
from flask_login import current_user, login_required
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import joinedload

from .extensions import db
from .media import save_media
from .models import Comment, Post, User, followers, PollOption, PollVote

bp = Blueprint("social", __name__)


def _post_query():
    # 🆕 擴充優化：加上 joinedload(Post.poll_options)，一次性撈出投票選項，防止 N+1 查詢問題
    return Post.query.options(
        joinedload(Post.author),
        joinedload(Post.repost_of).joinedload(Post.author),
        joinedload(Post.poll_options),
    )


def _comment_counts_for_posts(posts: list[Post]) -> dict[int, int]:
    post_ids = {post.display_post.id for post in posts}
    if not post_ids:
        return {}

    counts = dict.fromkeys(post_ids, 0)
    rows = (
        db.session.query(Comment.post_id, func.count(Comment.id))
        .filter(Comment.post_id.in_(post_ids))
        .group_by(Comment.post_id)
        .all()
    )
    counts.update({post_id: count for post_id, count in rows})
    return counts


def _followed_user_ids(users: list[User]) -> set[int]:
    user_ids = [user.id for user in users]
    if not user_ids:
        return set()

    return {
        followed_id
        for (followed_id,) in db.session.query(followers.c.followed_id)
        .filter(
            followers.c.follower_id == current_user.id,
            followers.c.followed_id.in_(user_ids),
        )
        .all()
    }


@bp.route("/")
@login_required
def feed():
    followed_ids = db.session.query(followers.c.followed_id).filter(
        followers.c.follower_id == current_user.id
    )
    posts = (
        _post_query()
        .filter(or_(Post.author_id == current_user.id, Post.author_id.in_(followed_ids)))
        .order_by(desc(Post.created_at))
        .limit(100)
        .all()
    )
    return render_template(
        "social/feed.html",
        posts=posts,
        comment_counts=_comment_counts_for_posts(posts),
    )


@bp.route("/explore")
@login_required
def explore():
    posts = _post_query().order_by(desc(Post.created_at)).limit(100).all()
    users = User.query.filter(User.id != current_user.id).order_by(User.username).limit(50).all()
    return render_template(
        "social/explore.html",
        posts=posts,
        users=users,
        comment_counts=_comment_counts_for_posts(posts),
        followed_user_ids=_followed_user_ids(users),
    )


@bp.post("/posts")
@login_required
def create_post():
    body = request.form.get("body", "").strip()
    
    # 🆕 1. 識別是否為投票貼文模式 (藉由前端傳入的 post_type 或是檢查有沒有帶選項)
    post_type = request.form.get("post_type", "text")
    
    # 獲取所有填入的投票選項清單
    options_raw = request.form.getlist("options")
    # 過濾出非空白的選項字串
    options = [opt.strip() for opt in options_raw if opt.strip()]

    try:
        media_filename, media_type = save_media(request.files.get("media"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(request.referrer or url_for("social.feed"))

    # 🆕 2. 商業邏輯校驗：如果是投票貼文
    if post_type == "poll" or len(options_raw) > 0:
        post_type = "poll"  # 強制修正型態
        
        # 欄位限制：檢查是否有空欄位 (若原始長度跟過濾後長度不符，代表有使用者填了空字串)
        if len(options) != len(options_raw):
            flash("Poll options cannot be empty strings.", "error")
            return redirect(request.referrer or url_for("social.feed"))
            
        # 欄位限制：限制上限 4 個，下限 2 個
        if len(options) < 2 or len(options) > 4:
            flash("A poll must contain between 2 and 4 options.", "error")
            return redirect(request.referrer or url_for("social.feed"))
    else:
        # 一般文字貼文的防呆
        if not body and not media_filename:
            flash("Add text, an image, or a video before posting.", "error")
            return redirect(request.referrer or url_for("social.feed"))

    # 🆕 3. 建立貼文實體
    post = Post(
        body=body,
        media_filename=media_filename,
        media_type=media_type,
        author=current_user,
        post_type=post_type,  # 寫入貼文類型
    )
    db.session.add(post)

    # 🆕 4. 如果是投票貼文，將選項一併塞入
    if post_type == "poll":
        for option_text in options:
            poll_option = PollOption(option_text=option_text, post=post)
            db.session.add(poll_option)

    db.session.commit()
    return redirect(url_for("social.feed"))


@bp.get("/posts/<int:post_id>")
@login_required
def post_detail(post_id: int):
    post = _post_query().filter(Post.id == post_id).first_or_404()
    comments = post.comments.order_by(Comment.created_at.asc()).all()
    return render_template(
        "social/post_detail.html",
        post=post,
        comments=comments,
        comment_counts={post.display_post.id: len(comments)},
    )


@bp.post("/posts/<int:post_id>/comments")
@login_required
def add_comment(post_id: int):
    post = db.get_or_404(Post, post_id)
    body = request.form.get("body", "").strip()
    if not body:
        flash("Comment cannot be empty.", "error")
    else:
        db.session.add(Comment(body=body, author=current_user, post=post))
        db.session.commit()
    return redirect(url_for("social.post_detail", post_id=post.id))


@bp.post("/posts/<int:post_id>/repost")
@login_required
def repost(post_id: int):
    original = db.get_or_404(Post, post_id).display_post
    if original.author_id == current_user.id:
        flash("You cannot repost your own post.", "error")
        return redirect(request.referrer or url_for("social.feed"))

    existing = Post.query.filter_by(author_id=current_user.id, repost_of_id=original.id).first()
    if existing:
        flash("You already reposted this.", "error")
        return redirect(request.referrer or url_for("social.feed"))

    db.session.add(Post(author=current_user, repost_of=original))
    db.session.commit()
    return redirect(request.referrer or url_for("social.feed"))


@bp.route("/users/<username>")
@login_required
def profile(username: str):
    user = User.query.filter_by(username=username).first_or_404()
    posts = (
        _post_query()
        .filter(Post.author_id == user.id)
        .order_by(desc(Post.created_at))
        .all()
    )
    return render_template(
        "social/profile.html",
        profile_user=user,
        posts=posts,
        comment_counts=_comment_counts_for_posts(posts),
    )


@bp.post("/users/<username>/follow")
@login_required
def follow(username: str):
    user = User.query.filter_by(username=username).first_or_404()
    current_user.follow(user)
    db.session.commit()
    return redirect(request.referrer or url_for("social.profile", username=user.username))


@bp.post("/users/<username>/unfollow")
@login_required
def unfollow(username: str):
    user = User.query.filter_by(username=username).first_or_404()
    current_user.unfollow(user)
    db.session.commit()
    return redirect(request.referrer or url_for("social.profile", username=user.username))


# ==========================================
# 🆕 全新功能：處理使用者點擊參與投票的 API 路由
# ==========================================
@bp.post("/posts/<int:post_id>/vote")
@login_required
def vote_poll(post_id: int):
    # 1. 取得貼文實體，確保為投票貼文
    post = _post_query().filter(Post.id == post_id).first_or_404()
    if post.post_type != "poll":
        return jsonify({"error": "This post is not a poll."}), 400

    # 2. 商業邏輯核心防禦：終身單一投票限制
    # 檢查該使用者是否已經對這篇貼文投過票
    existing_vote = PollVote.query.filter_by(user_id=current_user.id, post_id=post.id).first()
    if existing_vote:
        return jsonify({"error": "You have already voted on this poll."}), 400

    # 3. 獲取使用者選擇的選項 ID
    option_id = request.form.get("option_id")
    if not option_id:
        return jsonify({"error": "Missing option selection."}), 400
    
    try:
        option_id = int(option_id)  # 將字串 '2' 轉為整數 2
    except ValueError:
        return jsonify({"error": "Invalid option format."}), 400

    # 4. 驗證該選項是否真的屬於這篇貼文
    selected_option = PollOption.query.filter_by(id=option_id, post_id=post.id).first()
    if not selected_option:
        return jsonify({"error": "Invalid poll option selected."}), 400

    # 5. 寫入資料庫
    vote = PollVote(
        user_id=current_user.id,
        post_id=post.id,
        option_id=selected_option.id
    )
    db.session.add(vote)
    db.session.commit()

    # 6. 近即時更新回傳 (Near Real-time Response)：
    # 回傳 JSON 統計數據，供前端 JavaScript (fetch) 收到後可以直接在不刷網頁的情況下重新繪製進度條
    options_data = []
    for opt in post.poll_options:
        options_data.append({
            "id": opt.id,
            "text": opt.option_text,
            "votes": opt.vote_count,
            "percentage": opt.vote_percentage
        })

    return jsonify({
        "success": True,
        "total_votes": post.total_votes,
        "voted_option_id": selected_option.id,
        "options": options_data
    })