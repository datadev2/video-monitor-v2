#!/bin/bash

image="citadelbv/pb-accessibility-analysis"

echo "Enter the version of the build:"
read -r version

echo "Should this build be tagged as 'latest'? (y/n)"
read -r is_latest


# If the user answered 'yes', also tag the build as latest
if [ "$is_latest" = "y" ] || [ "$is_latest" = "yes" ]; then
  docker buildx build --platform linux/amd64 -t "$image":"$version" -t "$image":latest . --push
  sleep 15
else
  docker buildx build --platform linux/amd64 -t "$image":"$version" . --push
  sleep 15
fi