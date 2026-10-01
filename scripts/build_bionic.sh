#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# Ubuntu 18.04 is old enough for this SDK. Fall back to old-releases if needed.
dpkg --add-architecture i386
if ! apt-get update; then
  sed -i \
    -e 's|http://archive.ubuntu.com/ubuntu|http://old-releases.ubuntu.com/ubuntu|g' \
    -e 's|http://security.ubuntu.com/ubuntu|http://old-releases.ubuntu.com/ubuntu|g' \
    /etc/apt/sources.list
  apt-get update
fi
apt-get install -y \
  build-essential gawk git subversion wget curl ca-certificates \
  libncurses5-dev zlib1g-dev bison flex unzip xz-utils file patch sed m4 \
  autoconf automake libtool pkg-config python python-dev python3 \
  libc6:i386 libstdc++6:i386 zlib1g:i386

rm -rf /work/src
git clone https://github.com/cgoder/openwrt_rtk.git /work/src
cd /work/src
git checkout d237e45ee480ee7e75c80a4c61e1a335a0a77755
cd /work

# Apply SK-H724G hardware and package/download fixes.
python3 /work/scripts/patch_sdk.py

# On glibc 2.27, let the SDK build its original findutils/m4 instead of modern-host shims.
git -C /work/src checkout -- rtk_openwrt_sdk/tools/findutils/Makefile rtk_openwrt_sdk/tools/m4/Makefile

cd /work/src/rtk_openwrt_sdk
mkdir -p staging_dir
curl -fL --retry 5 --retry-delay 3 \
  https://github.com/bol-van/build/raw/refs/heads/master/rsdk-4.6.4-5281-EB-3.10-0.9.33-m32ub-20141001.txz \
  -o /tmp/rsdk.txz
tar -xJf /tmp/rsdk.txz -C staging_dir

cp rtk_deconfig/defconfig_rtl8198c .config

# The legacy OpenWrt/Realtek SDK explicitly refuses to compile as root.
# Prepare the tree as root, then run configuration and compilation as a normal user.
id -u builder >/dev/null 2>&1 || useradd -m -s /bin/bash builder
chown -R builder:builder /work/src

su -s /bin/bash builder -c '
  set -euo pipefail
  cd /work/src/rtk_openwrt_sdk
  yes "" | make oldconfig || true

  echo "=== SK-H724G target verification ==="
  grep -E "CONFIG_TARGET_rtkmips_rtl8198c|CONFIG_PACKAGE_kmod-rtl8192cd" .config | head -20 || true
  grep -E "CONFIG_SLOT_0_8192EE|CONFIG_SLOT_0_8194AE|CONFIG_SLOT_1_8814AE|CONFIG_WLAN_HAL_8192EE" target/linux/rtkmips/rtl8198c/config-3.10
  grep -n "0x81000000" target/linux/rtkmips/image/Makefile

  mkdir -p build_dir/host/firmware-utils/bin
  set -o pipefail
  make -j2 V=s 2>&1 | tee build-skh724g.log
'
