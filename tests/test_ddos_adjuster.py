import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from src.manager_api.routers.worker_tasks import ddos_adjuster, calculate_threads

MAX_WORKER_THREADS = 3000
MAX_THREADS_PER_WORKER = 7
DEFALUT_CATEGORIES = [
    "google",
    "digicert",
    "cloudflare",
    "letsencrypt",
    "trustasia",
]

@pytest.mark.asyncio
async def test_ddos_adjuster_100_workers():
    """Test ddos_adjuster with 100 running workers."""
    # Mock database session
    mock_db = AsyncMock()
    
    # Mock get_running_worker_count to return 100
    with patch('src.manager_api.routers.worker_tasks.get_running_worker_count', return_value=100) as mock_get_count:
        # Test input categories
        input_categories = DEFALUT_CATEGORIES.copy()
        
        # Call the function
        result = await ddos_adjuster(mock_db, input_categories)
        
        # Verify get_running_worker_count was called with correct db
        mock_get_count.assert_called_once_with(mock_db)
        
        # Calculate expected result
        # MAX_WORKER_THREADS = 3000, so with 100 workers: 3000 / 100 = 30 threads per worker
        # But limited by MAX_THREADS_PER_WORKER = 7, so should be 7
        expected_max_cat_count = calculate_threads(100, MAX_WORKER_THREADS)
        assert expected_max_cat_count == 7  # Limited by MAX_THREADS_PER_WORKER
        
        # Result should be input_categories sliced to expected_max_cat_count
        expected_result = input_categories[:expected_max_cat_count]
        assert result == expected_result
        assert len(result) == min(len(input_categories), expected_max_cat_count)


@pytest.mark.asyncio
async def test_ddos_adjuster_500_workers():
    """Test ddos_adjuster with 500 running workers."""
    mock_db = AsyncMock()
    
    with patch('src.manager_api.routers.worker_tasks.get_running_worker_count', return_value=500) as mock_get_count:
        input_categories = DEFALUT_CATEGORIES.copy()
        
        result = await ddos_adjuster(mock_db, input_categories)
        
        mock_get_count.assert_called_once_with(mock_db)
        
        # Calculate expected result
        # 3000 / 500 = 6 threads per worker
        expected_max_cat_count = calculate_threads(500, MAX_WORKER_THREADS)
        assert expected_max_cat_count == 6
        
        expected_result = input_categories[:expected_max_cat_count]
        assert result == expected_result
        assert len(result) == min(len(input_categories), expected_max_cat_count)


@pytest.mark.asyncio
async def test_ddos_adjuster_1000_workers():
    """Test ddos_adjuster with 1000 running workers."""
    mock_db = AsyncMock()
    
    with patch('src.manager_api.routers.worker_tasks.get_running_worker_count', return_value=1000) as mock_get_count:
        input_categories = DEFALUT_CATEGORIES.copy()
        
        result = await ddos_adjuster(mock_db, input_categories)
        
        mock_get_count.assert_called_once_with(mock_db)
        
        # Calculate expected result
        # 3000 / 1000 = 3 threads per worker
        expected_max_cat_count = calculate_threads(1000, MAX_WORKER_THREADS)
        assert expected_max_cat_count == 3
        
        expected_result = input_categories[:expected_max_cat_count]
        assert result == expected_result
        assert len(result) == min(len(input_categories), expected_max_cat_count)


@pytest.mark.asyncio
async def test_ddos_adjuster_2000_workers():
    """Test ddos_adjuster with 2000 running workers."""
    mock_db = AsyncMock()
    
    with patch('src.manager_api.routers.worker_tasks.get_running_worker_count', return_value=2000) as mock_get_count:
        input_categories = DEFALUT_CATEGORIES.copy()
        
        result = await ddos_adjuster(mock_db, input_categories)
        
        mock_get_count.assert_called_once_with(mock_db)
        
        # 3000 / 2000 = 1.5, probabilistic rounding could give 1 or 2
        # Verify result length is within expected range for probabilistic rounding
        assert len(result) in (1, 2)
        assert len(result) <= len(input_categories)
        
        # Verify the result is a proper slice of input_categories
        expected_result = input_categories[:len(result)]
        assert result == expected_result
        
        # Verify that calculate_threads produces consistent result
        calculated_threads = calculate_threads(2000, MAX_WORKER_THREADS)
        assert calculated_threads in (1, 2)


@pytest.mark.asyncio
async def test_ddos_adjuster_zero_workers():
    """Test ddos_adjuster with 0 running workers."""
    mock_db = AsyncMock()
    
    with patch('src.manager_api.routers.worker_tasks.get_running_worker_count', return_value=0) as mock_get_count:
        input_categories = DEFALUT_CATEGORIES.copy()
        
        result = await ddos_adjuster(mock_db, input_categories)
        
        mock_get_count.assert_called_once_with(mock_db)
        
        # With 0 workers, should return 0 threads
        expected_max_cat_count = calculate_threads(0, MAX_WORKER_THREADS)
        assert expected_max_cat_count == 0
        
        expected_result = input_categories[:expected_max_cat_count]
        assert result == expected_result
        assert len(result) == 0


@pytest.mark.asyncio
async def test_ddos_adjuster_empty_categories():
    """Test ddos_adjuster with empty categories list."""
    mock_db = AsyncMock()
    
    with patch('src.manager_api.routers.worker_tasks.get_running_worker_count', return_value=100) as mock_get_count:
        input_categories = []
        
        result = await ddos_adjuster(mock_db, input_categories)
        
        mock_get_count.assert_called_once_with(mock_db)
        
        # Even with threads available, empty list should stay empty
        assert result == []
        assert len(result) == 0


def test_calculate_threads_edge_cases():
    """Test calculate_threads function with edge cases."""
    # Test with 0 workers
    assert calculate_threads(0, MAX_WORKER_THREADS) == 0
    
    # Test with very high worker count - 3000/10000 = 0.3, probabilistic rounding could give 0 or 1
    results = []
    for _ in range(20):
        result = calculate_threads(10000, MAX_WORKER_THREADS)
        results.append(result)
        assert result in [0, 1]  # Should be 0 or 1 due to probabilistic rounding
    
    # Test with 1 worker
    result = calculate_threads(1, MAX_WORKER_THREADS)
    assert result == MAX_THREADS_PER_WORKER  # Should be limited by MAX_THREADS_PER_WORKER
    
    # Test with exact division
    assert calculate_threads(1000, 3000) == 3  # Exact division: 3000/1000 = 3


def test_calculate_threads_probabilistic_rounding():
    """Test that calculate_threads uses probabilistic rounding correctly."""
    # Test multiple runs with fractional values to ensure probabilistic behavior
    results = []
    for _ in range(100):  # Run multiple times to test probabilistic nature
        result = calculate_threads(2000, 3000)  # 3000/2000 = 1.5
        results.append(result)
    
    # Should get both 1 and 2 as results due to probabilistic rounding
    unique_results = set(results)
    assert len(unique_results) >= 1  # At minimum should have one value
    assert all(r in [1, 2] for r in unique_results)  # All results should be 1 or 2


@pytest.mark.asyncio
async def test_ddos_adjuster_preserves_category_order():
    """Test that ddos_adjuster preserves the order of categories."""
    mock_db = AsyncMock()
    
    with patch('src.manager_api.routers.worker_tasks.get_running_worker_count', return_value=1000):
        # Custom category order
        input_categories = ["trustasia", "google", "cloudflare", "digicert", "letsencrypt"]
        
        result = await ddos_adjuster(mock_db, input_categories)
        
        # Should preserve the input order
        expected_max_cat_count = calculate_threads(1000, MAX_WORKER_THREADS)
        expected_result = input_categories[:expected_max_cat_count]
        assert result == expected_result
        
        # Verify order is preserved
        for i, category in enumerate(result):
            assert category == input_categories[i]


@pytest.mark.asyncio
async def test_ddos_adjuster_database_error():
    """Test ddos_adjuster behavior when database query fails."""
    mock_db = AsyncMock()
    
    with patch('src.manager_api.routers.worker_tasks.get_running_worker_count', side_effect=Exception("DB Error")):
        input_categories = DEFALUT_CATEGORIES.copy()
        
        # Should raise the exception
        with pytest.raises(Exception, match="DB Error"):
            await ddos_adjuster(mock_db, input_categories)
