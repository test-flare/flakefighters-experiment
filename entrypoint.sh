#!/bin/bash
set -e

SOURCE_SHA=$1
TARGET_SHA=$2
TEST_PATH=$3
OUTPUT=$4
SAMPLE_SHAS=$5

source venv/bin/activate

if [ -z "$SOURCE_SHA" ] || [ -z "$TARGET_SHA" ] || [ -z "$TEST_PATH" ] || [ -z "$OUTPUT" ] || [ -z "$SAMPLE_SHAS" ]; then
    echo "Usage: docker run <image> <source_sha> <target_sha> <test_pat> <output> <sample_shas>"
    exit 1
fi

python ./reproduce_flakiness.py -s $SOURCE_SHA -t $TARGET_SHA -T $TEST_PATH -o $OUTPUT -S $SAMPLE_SHAS
