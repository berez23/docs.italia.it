#!/usr/bin/env sh

set -e

BASE_DIR="/home/documents"
dirs="private_cname_project
private_cname_root
private_web_root
public_cname_project
public_cname_root
public_web_root
media
user_builds
logs"
cd
for dir in ${dirs}; do
  mkdir -p "${BASE_DIR}/${dir}"
done
