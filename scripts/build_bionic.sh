#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

dpkg --add-architecture i386
apt-get update
apt-get install -y \
  build-essential gawk git subversion wget curl ca-certificates \
  libncurses5-dev zlib1g-dev bison flex unzip xz-utils file patch sed m4 \
  autoconf automake libtool pkg-config python python-dev \
  libc6:i386 libstdc++6:i386 zlib1g:i386

rm -rf /work/src-bionic
git clone https://github.com/cgoder/openwrt_rtk.git /work/src-bionic
cd /work/src-bionic
git checkout d237e45ee480ee7e75c80a4c61e1a335a0a77755
cd /work

# Apply hardware, URL and package fixes, but keep original findutils on glibc 2.27.
python3 scripts/patch_sdk.py
# patch_sdk.py targets /work/src, so move bionic tree into that expected path first.
