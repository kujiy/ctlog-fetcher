#!/usr/bin/env python3
"""
Test configuration for GitHub Actions
"""
import pytest
import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_database_connection():
    """Test that database configuration is properly set"""
    try:
        from src.config import MYSQL_URL
        assert MYSQL_URL is not None
        assert "mysql" in MYSQL_URL.lower()
        print(f"Database URL configured: {MYSQL_URL}")
    except ImportError as e:
        pytest.fail(f"Failed to import MYSQL_URL from config: {e}")

def test_config_import():
    """Test that all required config values can be imported"""
    try:
        from src.config import (
            MYSQL_URL,
            MANAGER_API_URL,
            DASHBOARD_URL,
            BATCH_SIZE
        )
        assert MYSQL_URL is not None
        assert MANAGER_API_URL is not None
        assert DASHBOARD_URL is not None
        assert BATCH_SIZE > 0
        print("All config values imported successfully")
    except ImportError as e:
        pytest.fail(f"Failed to import config values: {e}")

@pytest.mark.asyncio
async def test_database_engine_initialization():
    """Test that database engine can be initialized"""
    try:
        from src.manager_api.db import init_engine, dispose_engines_sync
        
        # Clean up any existing engines
        dispose_engines_sync()
        
        # Initialize engine
        init_engine()
        
        # Clean up
        dispose_engines_sync()
        
        print("Database engine initialization test passed")
    except Exception as e:
        pytest.fail(f"Database engine initialization failed: {e}")
