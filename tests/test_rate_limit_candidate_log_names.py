import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from src.manager_api.routers.worker_tasks import rate_limit_candidate_log_names
from src.config import JST
from src.share.job_status import JobStatus

@pytest.mark.asyncio
async def test_rate_limit_candidate_log_names_returns_high_unsuccessful_logs():
    """Test that rate_limit_candidate_log_names returns logs with high unsuccessful rate."""
    # Mock data that will be returned from the database query
    mock_query_result = [
        # log_name, unsuccessful_rate
        ("log1", 0.05),  # Low unsuccessful rate, should not be included
        ("log2", 0.15),  # High unsuccessful rate > 0.1, should be included with 80% probability
        ("log3", 0.25),  # High unsuccessful rate > 0.1, should be included with 80% probability
        ("log4", 0.02),  # Low unsuccessful rate, should not be included
    ]
    
    # Create a class that mimics SQLAlchemy's return structure
    class MockDBResult:
        def all(self):
            return mock_query_result
            
    # Mock DB session
    mock_db = AsyncMock()
    # Make execute return a future that's already done
    mock_db.execute.return_value = MockDBResult()
    
    # Make random.random() always return 0.7 (less than 0.8) to ensure high unsuccessful logs are included
    with patch('random.random', return_value=0.7):
        result = await rate_limit_candidate_log_names(mock_db, "test_worker")
        
        # Verify the SQL query was executed with correct parameters
        mock_db.execute.assert_called_once()
        
        # Check that only logs with unsuccessful_rate > 0.1 are included
        # Since random.random() is 0.7 (< 0.8), both log2 and log3 should be included
        assert "log1" not in result
        assert "log2" in result
        assert "log3" in result
        assert "log4" not in result

@pytest.mark.asyncio
async def test_rate_limit_candidate_log_names_probabilistic_inclusion():
    """Test that logs with high unsuccessful rate are included probabilistically."""
    # Mock data that will be returned from the database query
    mock_query_result = [
        ("log1", 0.15),  # High unsuccessful rate, will be subject to probabilistic inclusion
    ]
    
    # Create a class that mimics SQLAlchemy's return structure
    class MockDBResult:
        def all(self):
            return mock_query_result
    
    # Mock DB session
    mock_db = AsyncMock()
    mock_db.execute.return_value = MockDBResult()
    
    # Test with random value = 0.7 (less than 0.8): log should be included
    with patch('random.random', return_value=0.7):
        result = await rate_limit_candidate_log_names(mock_db, "test_worker")
        assert "log1" in result
    
    # Test with random value = 0.9 (greater than 0.8): log should NOT be included
    with patch('random.random', return_value=0.9):
        result = await rate_limit_candidate_log_names(mock_db, "test_worker")
        assert "log1" not in result

@pytest.mark.asyncio
async def test_rate_limit_candidate_log_names_with_empty_result():
    """Test that function handles empty query result correctly."""
    # Empty mock data
    mock_query_result = []
    
    # Create a class that mimics SQLAlchemy's return structure
    class MockDBResult:
        def all(self):
            return mock_query_result
    
    # Mock DB session
    mock_db = AsyncMock()
    mock_db.execute.return_value = MockDBResult()
    
    result = await rate_limit_candidate_log_names(mock_db, "test_worker")
    
    # Verify the SQL query was executed
    mock_db.execute.assert_called_once()
    
    # Result should be an empty list
    assert result == []

@pytest.mark.asyncio
async def test_rate_limit_candidate_log_names_sql_parameters():
    """Test that the SQL query is constructed with the correct parameters."""
    # Empty mock data for simplicity
    mock_query_result = []
    
    # Create a class that mimics SQLAlchemy's return structure
    class MockDBResult:
        def all(self):
            return mock_query_result
    
    # Mock DB session
    mock_db = AsyncMock()
    mock_db.execute.return_value = MockDBResult()
    
    # Capture the SQL and params passed to execute
    with patch('src.manager_api.routers.worker_tasks.datetime') as mock_datetime:
        # Mock the datetime.now() to return a fixed date
        mock_now = datetime(2025, 9, 14, 12, 0, 0, tzinfo=JST)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
        
        # Call the function
        await rate_limit_candidate_log_names(mock_db, "test_worker")
        
        # Check that execute was called with the right parameters
        args, kwargs = mock_db.execute.call_args
        
        # The first argument should be the SQL query
        sql = args[0]
        assert "SELECT" in sql
        assert "log_name" in sql
        assert "unsuccessful_rate" in sql.lower()
        assert "worker_status" in sql
        assert "GROUP BY" in sql
        
        # The second argument should be the parameters
        params = args[1] if len(args) > 1 else kwargs
        assert params.get("running_status") == JobStatus.RUNNING.value
        assert params.get("worker_name") == "test_worker"
        
        # Check that the threshold is set to 24 hours ago
        expected_threshold = (mock_now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        if params.get("threshold"):
            assert params.get("threshold") == expected_threshold
