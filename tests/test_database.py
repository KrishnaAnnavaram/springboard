"""Tests for database models and repositories."""

from datetime import datetime, timedelta

import pytest

from src.database.models import Application, LinkedInJob, Resume, User
from src.database.repositories.application_repository import ApplicationRepository
from src.database.repositories.job_repository import JobRepository
from src.database.repositories.resume_repository import ResumeRepository
from src.database.repositories.user_repository import UserRepository


class TestUserRepository:
    """Tests for UserRepository."""

    def test_create_user(self, db_session):
        repo = UserRepository(db_session)
        user = repo.create(
            email="new@example.com",
            name="New User",
            phone="555-0101",
        )
        assert user.id is not None
        assert user.email == "new@example.com"
        assert user.name == "New User"

    def test_get_by_id(self, db_session, sample_user):
        repo = UserRepository(db_session)
        user = repo.get_by_id(sample_user.id)
        assert user is not None
        assert user.email == sample_user.email

    def test_get_by_email(self, db_session, sample_user):
        repo = UserRepository(db_session)
        user = repo.get_by_email("testuser@example.com")
        assert user is not None
        assert user.name == "Test User"

    def test_get_default_user(self, db_session, sample_user):
        repo = UserRepository(db_session)
        user = repo.get_default_user()
        assert user is not None

    def test_update_profile(self, db_session, sample_user):
        repo = UserRepository(db_session)
        updated = repo.update_profile(sample_user.id, name="Updated Name", phone="555-9999")
        assert updated.name == "Updated Name"
        assert updated.phone == "555-9999"

    def test_update_preferences(self, db_session, sample_user):
        repo = UserRepository(db_session)
        repo.update_preferences(sample_user.id, {"salary_min": 150000})
        user = repo.get_by_id(sample_user.id)
        assert user.preferences["salary_min"] == 150000

    def test_update_profile_data(self, db_session, sample_user):
        repo = UserRepository(db_session)
        repo.update_profile_data(sample_user.id, {"skills": ["Python", "Go"]})
        user = repo.get_by_id(sample_user.id)
        assert "Go" in user.profile_data["skills"]

    def test_delete_user(self, db_session, sample_user):
        repo = UserRepository(db_session)
        result = repo.delete(sample_user.id)
        assert result is True
        assert repo.get_by_id(sample_user.id) is None

    def test_delete_nonexistent(self, db_session):
        repo = UserRepository(db_session)
        result = repo.delete(9999)
        assert result is False


class TestJobRepository:
    """Tests for JobRepository."""

    def test_create_job(self, db_session):
        repo = JobRepository(db_session)
        job = repo.create(
            linkedin_job_id="new_job_001",
            title="New Role",
            company="Test Co",
            job_url="https://linkedin.com/jobs/view/new_job_001",
        )
        assert job.id is not None
        assert job.title == "New Role"
        assert job.status == "new"

    def test_get_by_id(self, db_session, sample_jobs):
        repo = JobRepository(db_session)
        job = repo.get_by_id(sample_jobs[0].id)
        assert job is not None
        assert job.title == "Senior Software Engineer"

    def test_get_by_linkedin_id(self, db_session, sample_jobs):
        repo = JobRepository(db_session)
        job = repo.get_by_linkedin_id("job_001")
        assert job is not None
        assert job.company == "Google"

    def test_get_all(self, db_session, sample_jobs):
        repo = JobRepository(db_session)
        jobs = repo.get_all()
        assert len(jobs) == 3

    def test_get_all_pagination(self, db_session, sample_jobs):
        repo = JobRepository(db_session)
        page1 = repo.get_all(limit=2, offset=0)
        page2 = repo.get_all(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 1

    def test_get_by_status(self, db_session, sample_jobs):
        repo = JobRepository(db_session)
        jobs = repo.get_by_status("new")
        assert len(jobs) == 3

    def test_get_matched_jobs(self, db_session, sample_jobs):
        repo = JobRepository(db_session)
        repo.update_match_score(sample_jobs[0].id, 85.0, "Great match")
        repo.update_match_score(sample_jobs[1].id, 50.0, "Partial match")
        matched = repo.get_matched_jobs(min_score=60.0)
        assert len(matched) == 1
        assert matched[0].match_score == 85.0

    def test_update_match_score(self, db_session, sample_jobs):
        repo = JobRepository(db_session)
        job = repo.update_match_score(sample_jobs[0].id, 92.5, "Excellent fit")
        assert job.match_score == 92.5
        assert job.match_reasoning == "Excellent fit"
        assert job.status == "matched"

    def test_update_status(self, db_session, sample_jobs):
        repo = JobRepository(db_session)
        job = repo.update_status(sample_jobs[0].id, "applied")
        assert job.status == "applied"

    def test_count_all(self, db_session, sample_jobs):
        repo = JobRepository(db_session)
        assert repo.count_all() == 3

    def test_count_today(self, db_session, sample_jobs):
        repo = JobRepository(db_session)
        assert repo.count_today() == 3

    def test_count_by_status(self, db_session, sample_jobs):
        repo = JobRepository(db_session)
        assert repo.count_by_status("new") == 3
        assert repo.count_by_status("applied") == 0

    def test_search_by_title(self, db_session, sample_jobs):
        repo = JobRepository(db_session)
        results = repo.search("Software Engineer")
        assert len(results) == 1
        assert results[0].title == "Senior Software Engineer"

    def test_search_by_company(self, db_session, sample_jobs):
        repo = JobRepository(db_session)
        results = repo.search("Google")
        assert len(results) == 1

    def test_search_with_filters(self, db_session, sample_jobs):
        repo = JobRepository(db_session)
        repo.update_match_score(sample_jobs[0].id, 90.0, "Match")
        results = repo.search("", min_score=80.0)
        assert len(results) == 1

    def test_get_unmatched_jobs(self, db_session, sample_jobs):
        repo = JobRepository(db_session)
        unmatched = repo.get_unmatched_jobs()
        assert len(unmatched) == 3
        repo.update_match_score(sample_jobs[0].id, 80.0, "Matched")
        unmatched = repo.get_unmatched_jobs()
        assert len(unmatched) == 2

    def test_get_top_companies(self, db_session, sample_jobs):
        repo = JobRepository(db_session)
        companies = repo.get_top_companies(limit=5)
        assert len(companies) == 3


class TestApplicationRepository:
    """Tests for ApplicationRepository."""

    def test_create_application(self, db_session, sample_user, sample_jobs):
        repo = ApplicationRepository(db_session)
        app = repo.create(
            job_id=sample_jobs[0].id,
            user_id=sample_user.id,
            status="pending",
        )
        assert app.id is not None
        assert app.status == "pending"

    def test_get_by_id(self, db_session, sample_application):
        repo = ApplicationRepository(db_session)
        app = repo.get_by_id(sample_application.id)
        assert app is not None
        assert app.status == "submitted"

    def test_get_by_job_id(self, db_session, sample_application):
        repo = ApplicationRepository(db_session)
        app = repo.get_by_job_id(sample_application.job_id)
        assert app is not None

    def test_get_all(self, db_session, sample_application):
        repo = ApplicationRepository(db_session)
        apps = repo.get_all()
        assert len(apps) == 1

    def test_get_by_status(self, db_session, sample_application):
        repo = ApplicationRepository(db_session)
        apps = repo.get_by_status("submitted")
        assert len(apps) == 1

    def test_update_status(self, db_session, sample_application):
        repo = ApplicationRepository(db_session)
        app = repo.update_status(sample_application.id, "interview")
        assert app.status == "interview"
        assert app.response_date is not None

    def test_update_status_sets_applied_date(self, db_session, sample_user, sample_jobs):
        repo = ApplicationRepository(db_session)
        app = repo.create(job_id=sample_jobs[1].id, user_id=sample_user.id, status="pending")
        updated = repo.update_status(app.id, "submitted")
        assert updated.applied_date is not None

    def test_add_note(self, db_session, sample_application):
        repo = ApplicationRepository(db_session)
        app = repo.add_note(sample_application.id, "Recruiter responded")
        assert "Recruiter responded" in app.notes

    def test_count_all(self, db_session, sample_application):
        repo = ApplicationRepository(db_session)
        assert repo.count_all() == 1

    def test_count_by_status(self, db_session, sample_application):
        repo = ApplicationRepository(db_session)
        assert repo.count_by_status("submitted") == 1
        assert repo.count_by_status("rejected") == 0

    def test_get_response_rate(self, db_session, sample_user, sample_jobs):
        repo = ApplicationRepository(db_session)
        # Create applications with different statuses
        statuses = ["submitted", "interview", "rejected"]
        for i, status in enumerate(statuses):
            app = Application(
                job_id=sample_jobs[i].id,
                user_id=sample_user.id,
                status=status,
                applied_date=datetime.utcnow(),
            )
            db_session.add(app)
        db_session.flush()

        rate = repo.get_response_rate()
        # 2 responded (interview + rejected) out of 3 total = 66.7%
        assert rate == pytest.approx(66.7, abs=0.1)

    def test_get_status_breakdown(self, db_session, sample_application):
        repo = ApplicationRepository(db_session)
        breakdown = repo.get_status_breakdown()
        assert "submitted" in breakdown
        assert breakdown["submitted"] == 1


class TestResumeRepository:
    """Tests for ResumeRepository."""

    def test_create_resume(self, db_session, sample_user):
        repo = ResumeRepository(db_session)
        resume = repo.create(
            user_id=sample_user.id,
            version_name="Test Resume",
            content_text="Resume content here",
            is_primary=True,
        )
        assert resume.id is not None
        assert resume.version_name == "Test Resume"

    def test_get_by_id(self, db_session, sample_resume):
        repo = ResumeRepository(db_session)
        resume = repo.get_by_id(sample_resume.id)
        assert resume is not None
        assert "Test User" in resume.content_text

    def test_get_primary(self, db_session, sample_resume):
        repo = ResumeRepository(db_session)
        primary = repo.get_primary(sample_resume.user_id)
        assert primary is not None
        assert primary.is_primary is True

    def test_get_all_for_user(self, db_session, sample_user, sample_resume):
        repo = ResumeRepository(db_session)
        # Add another resume
        repo.create(
            user_id=sample_user.id,
            version_name="Custom v2",
            content_text="Customized content",
        )
        resumes = repo.get_all_for_user(sample_user.id)
        assert len(resumes) == 2

    def test_set_primary(self, db_session, sample_user, sample_resume):
        repo = ResumeRepository(db_session)
        new_resume = repo.create(
            user_id=sample_user.id,
            version_name="New Primary",
            content_text="New content",
        )
        repo.set_primary(new_resume.id, sample_user.id)
        old = repo.get_by_id(sample_resume.id)
        assert old.is_primary is False
        assert new_resume.is_primary is True

    def test_update_content(self, db_session, sample_resume):
        repo = ResumeRepository(db_session)
        repo.update_content(sample_resume.id, "Updated content")
        resume = repo.get_by_id(sample_resume.id)
        assert resume.content_text == "Updated content"

    def test_delete_resume(self, db_session, sample_resume):
        repo = ResumeRepository(db_session)
        result = repo.delete(sample_resume.id)
        assert result is True
        assert repo.get_by_id(sample_resume.id) is None

    def test_count_for_user(self, db_session, sample_user, sample_resume):
        repo = ResumeRepository(db_session)
        assert repo.count_for_user(sample_user.id) == 1


class TestFeedPostRepository:
    """Tests for FeedPostRepository."""

    def test_create_post(self, db_session):
        from src.database.repositories.feed_repository import FeedPostRepository
        repo = FeedPostRepository(db_session)
        post = repo.create(
            post_url="https://linkedin.com/feed/update/test1",
            author_name="Recruiter Test",
            post_text="We are hiring engineers!",
            keywords_found=["hiring"],
            is_hiring_post=True,
            status="new",
            platform="linkedin_feed",
        )
        assert post.id is not None
        assert post.author_name == "Recruiter Test"
        assert post.status == "new"

    def test_get_by_url(self, db_session, sample_feed_posts):
        from src.database.repositories.feed_repository import FeedPostRepository
        repo = FeedPostRepository(db_session)
        post = repo.get_by_url("https://linkedin.com/feed/update/1")
        assert post is not None
        assert post.author_name == "John Recruiter"

    def test_get_all(self, db_session, sample_feed_posts):
        from src.database.repositories.feed_repository import FeedPostRepository
        repo = FeedPostRepository(db_session)
        posts = repo.get_all()
        assert len(posts) == 2

    def test_get_by_status(self, db_session, sample_feed_posts):
        from src.database.repositories.feed_repository import FeedPostRepository
        repo = FeedPostRepository(db_session)
        posts = repo.get_by_status("new")
        assert len(posts) == 2

    def test_update_status(self, db_session, sample_feed_posts):
        from src.database.repositories.feed_repository import FeedPostRepository
        repo = FeedPostRepository(db_session)
        post = repo.update_status(sample_feed_posts[0].id, "reviewed")
        assert post.status == "reviewed"

    def test_count_all(self, db_session, sample_feed_posts):
        from src.database.repositories.feed_repository import FeedPostRepository
        repo = FeedPostRepository(db_session)
        assert repo.count_all() == 2

    def test_count_by_status(self, db_session, sample_feed_posts):
        from src.database.repositories.feed_repository import FeedPostRepository
        repo = FeedPostRepository(db_session)
        assert repo.count_by_status("new") == 2
        assert repo.count_by_status("reviewed") == 0


class TestJobRepositoryMultiPlatform:
    """Tests for multi-platform additions to JobRepository."""

    def test_create_with_platform(self, db_session):
        repo = JobRepository(db_session)
        job = repo.create(
            linkedin_job_id="dice_123",
            title="Dice Engineer",
            company="DiceCo",
            job_url="https://dice.com/jobs/123",
            platform="dice",
            platform_job_id="d_123",
        )
        assert job.platform == "dice"
        assert job.platform_job_id == "d_123"

    def test_get_by_platform_job_id(self, db_session):
        repo = JobRepository(db_session)
        repo.create(
            linkedin_job_id="indeed_456",
            title="Indeed Role",
            company="IndeedCo",
            job_url="https://indeed.com/jobs/456",
            platform="indeed",
            platform_job_id="i_456",
        )
        job = repo.get_by_platform_job_id("i_456", "indeed")
        assert job is not None
        assert job.title == "Indeed Role"

    def test_filter_by_platform(self, db_session, sample_jobs):
        repo = JobRepository(db_session)
        # sample_jobs default to "linkedin" platform
        linkedin_jobs = repo.filter_by_platform("linkedin")
        assert len(linkedin_jobs) == 3

        # No dice jobs exist
        dice_jobs = repo.filter_by_platform("dice")
        assert len(dice_jobs) == 0


class TestModelRelationships:
    """Tests for model relationships and constraints."""

    def test_user_applications_relationship(self, db_session, sample_user, sample_application):
        apps = sample_user.applications.all()
        assert len(apps) == 1

    def test_user_resumes_relationship(self, db_session, sample_user, sample_resume):
        resumes = sample_user.resumes.all()
        assert len(resumes) == 1

    def test_job_applications_relationship(self, db_session, sample_jobs, sample_application):
        apps = sample_jobs[0].applications.all()
        assert len(apps) == 1

    def test_application_job_backref(self, db_session, sample_application):
        assert sample_application.job is not None
        assert sample_application.job.title == "Senior Software Engineer"

    def test_application_user_backref(self, db_session, sample_application):
        assert sample_application.user is not None
        assert sample_application.user.name == "Test User"

    def test_model_repr(self, db_session, sample_user, sample_jobs, sample_application, sample_resume):
        assert "Test User" in repr(sample_user)
        assert "Senior Software Engineer" in repr(sample_jobs[0])
        assert "submitted" in repr(sample_application)
        assert "Base Resume" in repr(sample_resume)
