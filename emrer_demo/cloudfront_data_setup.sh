#!/bin/sh
# This script copies the sample "cloudfront" directory to our own bucket.
# The purpose is just to have a bootstrap action do something.
# The role of the instance executing it must have access to both buckets.

our_bucket="$1"
touch /tmp/bucket_access_test
echo "Uploading test file"
aws s3 cp /tmp/bucket_access_test s3://${our_bucket}
if [ $? -neq 0 ]; then
    echo "Access test failed. Abandoning"
    exit 1
fi
aws s3 cp s3://eu-west-1.elasticmapreduce.samples/cloudfront/ s3://${our_bucket}/cloudfront/ --recursive
