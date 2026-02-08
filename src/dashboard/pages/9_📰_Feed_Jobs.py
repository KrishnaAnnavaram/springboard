"""Feed Jobs page - View and manage hiring posts from LinkedIn feed."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
from datetime import datetime

from src.database.connection import get_db, init_db
from src.database.repositories.feed_repository import FeedPostRepository
from src.utils.config import Config

st.set_page_config(page_title="Springboard - Feed Jobs", page_icon="📰", layout="wide")
st.title("📰 Feed Jobs - Hiring Posts")

try:
    init_db()
except Exception:
    pass

config = Config()

# Summary metrics
with get_db() as session:
    repo = FeedPostRepository(session)
    total = repo.count_all()
    new_count = repo.count_by_status("new")
    reviewed = repo.count_by_status("reviewed")
    applied = repo.count_by_status("applied")

metric_cols = st.columns(4)
with metric_cols[0]:
    st.metric("Total Posts", total)
with metric_cols[1]:
    st.metric("New", new_count)
with metric_cols[2]:
    st.metric("Reviewed", reviewed)
with metric_cols[3]:
    st.metric("Applied", applied)

st.markdown("---")

# Filters
filter_cols = st.columns(3)
with filter_cols[0]:
    status_filter = st.selectbox("Status", ["all", "new", "reviewed", "applied", "dismissed"])
with filter_cols[1]:
    limit = st.number_input("Show", value=50, min_value=10, max_value=500, step=10)
with filter_cols[2]:
    st.markdown("")
    if st.button("🔄 Refresh"):
        st.rerun()

st.markdown("---")

# Fetch posts
with get_db() as session:
    repo = FeedPostRepository(session)
    if status_filter == "all":
        posts = repo.get_all(limit=limit)
    else:
        posts = repo.get_by_status(status_filter, limit=limit)

if not posts:
    st.info(
        "No feed posts found. Run the workflow with feed scraping enabled, "
        "or check that the LinkedIn Feed platform is enabled in config.yaml."
    )
else:
    for post in posts:
        status_icon = {"new": "🆕", "reviewed": "👁️", "applied": "✅", "dismissed": "❌"}.get(
            post.status, "⚪"
        )

        with st.expander(
            f"{status_icon} {post.author_name or 'Unknown'} — "
            f"{(post.post_text or '')[:80]}...",
            expanded=False,
        ):
            info_cols = st.columns([2, 1])
            with info_cols[0]:
                st.markdown(f"**Author:** {post.author_name or 'Unknown'}")
                if post.author_profile_url:
                    st.markdown(f"**Profile:** {post.author_profile_url}")
                if post.company_mentioned:
                    st.markdown(f"**Company:** {post.company_mentioned}")
                if post.posted_date:
                    st.markdown(f"**Posted:** {post.posted_date}")

            with info_cols[1]:
                st.markdown(f"**Likes:** {post.likes or 0}")
                st.markdown(f"**Comments:** {post.comments or 0}")
                if post.keywords_found:
                    keywords = post.keywords_found if isinstance(post.keywords_found, list) else []
                    st.markdown(f"**Keywords:** {', '.join(keywords)}")
                st.markdown(f"**Status:** {post.status}")

            st.markdown("**Post Text:**")
            st.text_area(
                "Content",
                value=post.post_text or "",
                height=150,
                key=f"post_text_{post.id}",
                disabled=True,
                label_visibility="collapsed",
            )

            if post.post_url:
                st.markdown(f"[View Original Post]({post.post_url})")

            # Status actions
            action_cols = st.columns(4)
            with action_cols[0]:
                if post.status != "reviewed" and st.button("👁️ Mark Reviewed", key=f"review_{post.id}"):
                    with get_db() as s:
                        FeedPostRepository(s).update_status(post.id, "reviewed")
                    st.rerun()
            with action_cols[1]:
                if post.status != "applied" and st.button("✅ Mark Applied", key=f"applied_{post.id}"):
                    with get_db() as s:
                        FeedPostRepository(s).update_status(post.id, "applied")
                    st.rerun()
            with action_cols[2]:
                if post.status != "dismissed" and st.button("❌ Dismiss", key=f"dismiss_{post.id}"):
                    with get_db() as s:
                        FeedPostRepository(s).update_status(post.id, "dismissed")
                    st.rerun()
