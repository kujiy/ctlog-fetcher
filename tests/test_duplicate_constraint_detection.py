import pytest
from sqlalchemy.exc import IntegrityError
from src.manager_api.routers.worker_upload2 import is_duplicate_constraint_error


def test_is_duplicate_constraint_error():
    """Test the is_duplicate_constraint_error function with various error messages"""
    
    # Test MySQL duplicate entry error (the one we saw in the original error)
    mysql_duplicate_error = IntegrityError(
        "statement", "params", 
        "(pymysql.err.IntegrityError) (1062, \"Duplicate entry 'DigiCert Inc-13276748837403306648570091756620641900-3020c147dab7' for key 'cert2.idx_cert2_unique'\")"
    )
    assert is_duplicate_constraint_error(mysql_duplicate_error) == True
    
    # Test MySQL error code 1062 specifically
    mysql_1062_error = IntegrityError(
        "statement", "params", 
        "(pymysql.err.IntegrityError) (1062, 'Duplicate entry for key')"
    )
    assert is_duplicate_constraint_error(mysql_1062_error) == True
    
    # Test generic unique constraint error
    unique_constraint_error = IntegrityError(
        "statement", "params", 
        "UNIQUE constraint failed: cert2.idx_cert2_unique"
    )
    assert is_duplicate_constraint_error(unique_constraint_error) == True
    
    # Test duplicate key error
    duplicate_key_error = IntegrityError(
        "statement", "params", 
        "duplicate key value violates unique constraint"
    )
    assert is_duplicate_constraint_error(duplicate_key_error) == True
    
    # Test foreign key constraint error (should return False)
    foreign_key_error = IntegrityError(
        "statement", "params", 
        "FOREIGN KEY constraint failed"
    )
    assert is_duplicate_constraint_error(foreign_key_error) == False
    
    # Test check constraint error (should return False)
    check_constraint_error = IntegrityError(
        "statement", "params", 
        "CHECK constraint failed: some_check"
    )
    assert is_duplicate_constraint_error(check_constraint_error) == False
    
    # Test not null constraint error (should return False)
    not_null_error = IntegrityError(
        "statement", "params", 
        "NOT NULL constraint failed: table.column"
    )
    assert is_duplicate_constraint_error(not_null_error) == False


if __name__ == "__main__":
    test_is_duplicate_constraint_error()
    print("All tests passed!")
