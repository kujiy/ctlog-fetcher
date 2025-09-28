#!/bin/bash

# HTTP Performance Test Runner
# Runs all 16 test patterns separately and combines results

SCRIPT_NAME="test_http_performance.py"

# Activate virtual environment
if [ -d "venv" ]; then
    echo "🔧 Activating virtual environment (venv)..."
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo "🔧 Activating virtual environment (.venv)..."
    source .venv/bin/activate
else
    echo "⚠️  No virtual environment found (venv or .venv). Using system Python."
fi
RESULTS_FILE="results_$(date +%Y%m%d_%H%M%S).txt"
TEMP_DIR="./temp_results"

# Test IDs to run
TEST_IDS=("1.1" "1.2" "1.3" "1.4" "2.1" "2.2" "2.3" "2.4" "3.1" "3.2" "3.3" "3.4" "4.1" "4.2" "4.3" "4.4")

echo "🚀 HTTP Connection Performance Test Runner"
echo "=========================================="
echo "Running 16 separate test processes..."
echo "Results will be saved to: $RESULTS_FILE"
echo ""

# Create temp directory for individual results
mkdir -p "$TEMP_DIR"

# Function to run a single test
run_test() {
    local test_id=$1
    local output_file="$TEMP_DIR/result_${test_id}.txt"
    
    echo "🔄 Running test $test_id..."
    
    # Run the test and capture both stdout and stderr
    python "$SCRIPT_NAME" --test "$test_id" > "$output_file" 2> "$TEMP_DIR/stderr_${test_id}.txt"
    
    if [ $? -eq 0 ]; then
        echo "✅ Test $test_id completed"
    else
        echo "❌ Test $test_id failed"
        cat "$TEMP_DIR/stderr_${test_id}.txt"
    fi
}

# Run tests serially (one after another)
echo "Starting serial test execution..."
for test_id in "${TEST_IDS[@]}"; do
    run_test "$test_id"
done

echo ""
echo "🎯 All tests completed. Combining results..."

# Create final results table
{
    echo "=========================================="
    echo "【明示的No Keep-Alive テスト結果】"
    echo "=========================================="
    echo ""
    printf "%-35s %-10s %-10s %-10s %-12s %s\\n" "Pattern" "Req1 (s)" "Req2 (s)" "Req3 (s)" "Average (s)" "Analysis"
    echo "----------------------------------------------------------------------------------------------------"
    
    # Process results in order
    for test_id in "${TEST_IDS[@]}"; do
        result_file="$TEMP_DIR/result_${test_id}.txt"
        if [ -f "$result_file" ] && [ -s "$result_file" ]; then
            cat "$result_file"
        else
            printf "%-35s %-10s %-10s %-10s %-12s %s\\n" "${test_id} (FAILED)" "N/A" "N/A" "N/A" "N/A" "❌ Test failed"
        fi
    done
    
    echo ""
    echo "=========================================="
    echo "📊 Test Summary"
    echo "=========================================="
    
    # Count successful and failed tests
    successful=0
    failed=0
    for test_id in "${TEST_IDS[@]}"; do
        result_file="$TEMP_DIR/result_${test_id}.txt"
        if [ -f "$result_file" ] && [ -s "$result_file" ]; then
            ((successful++))
        else
            ((failed++))
        fi
    done
    
    echo "Total tests: ${#TEST_IDS[@]}"
    echo "Successful: $successful"
    echo "Failed: $failed"
    echo ""
    echo "Execution completed at: $(date)"
    
} > "$RESULTS_FILE"

# Display the results
cat "$RESULTS_FILE"

echo ""
echo "📁 Results saved to: $RESULTS_FILE"

# Clean up temp directory option
read -p "🗑️  Delete temporary files? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf "$TEMP_DIR"
    echo "✅ Temporary files cleaned up"
else
    echo "📁 Temporary files kept in: $TEMP_DIR"
fi

echo "🎉 All done!"