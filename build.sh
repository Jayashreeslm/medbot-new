#!/usr/bin/env bash
set -o errexit

apt-get update
apt-get install -y cmake build-essential

pip install -r requirements.txt
