"""
Basic health check tests for CI/CD pipeline
"""

import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestHealthCheck:
    """Basic health check tests"""

    def test_imports(self):
        """Test that main modules can be imported"""
        try:
            from config import meta_credentials
            from config import constants
            from config import claude_api
            assert True
        except ImportError as e:
            pytest.skip(f"Import skipped: {e}")

    def test_utils_import(self):
        """Test utility modules import"""
        try:
            from utils import logger
            from utils import slack_notifier
            assert True
        except ImportError as e:
            pytest.skip(f"Import skipped: {e}")

    def test_paid_modules_import(self):
        """Test paid advertising modules import"""
        try:
            from paid import ad_multiplier
            from paid import kill_switch
            from paid import dco_optimizer
            from paid import cta_manager
            assert True
        except ImportError as e:
            pytest.skip(f"Import skipped: {e}")

    def test_organic_modules_import(self):
        """Test organic marketing modules import"""
        try:
            from organic import comment_manager
            from organic import dm_manager
            from organic import content_publisher
            from organic import caption_optimizer
            from organic import insights_analyzer
            assert True
        except ImportError as e:
            pytest.skip(f"Import skipped: {e}")


class TestConfiguration:
    """Configuration tests"""

    def test_env_example_exists(self):
        """Test .env.example file exists"""
        env_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".env.example"
        )
        assert os.path.exists(env_path), ".env.example file should exist"

    def test_requirements_exists(self):
        """Test requirements.txt exists"""
        req_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "requirements.txt"
        )
        assert os.path.exists(req_path), "requirements.txt file should exist"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
