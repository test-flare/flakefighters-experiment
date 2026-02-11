#!/bin/bash
set -e

SOURCE_SHA=$1
TARGET_SHA=$2
TEST_PATH=$3
OUTPUT=$4

source venv/bin/activate

if [ -z "$SOURCE_SHA" ] || [ -z "$TARGET_SHA" ] || [ -z "$TEST_PATH" ] || [ -z "$OUTPUT" ]; then
    echo "Usage: docker run <image> <source_sha> <target_sha> <test_pat> <output>"
    exit 1
fi

python ./reproduce_flakiness.py -s $SOURCE_SHA -t $TARGET_SHA -T $TEST_PATH -o $OUTPUT
