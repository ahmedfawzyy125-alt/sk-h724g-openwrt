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
  libc6:i386 libstdc++6:i386 zlib1g:i386 squashfs-tools

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

# Pin a LuCI revision compatible with the Barrier Breaker SDK.
# Current LuCI needs newer OpenWrt APIs and cannot be mixed into this SDK.
rm -rf /work/luci
git clone --branch luci-0.12 --single-branch https://github.com/openwrt/luci.git /work/luci
git -C /work/luci checkout 0d510b28203d33c6969ae5549f37f8b39811dd2e
mkdir -p package/luci
sed 's|^LUCI_TOPDIR=.*|LUCI_TOPDIR=/work/luci|' /work/luci/contrib/package/luci/Makefile > package/luci/Makefile
# SDK package dependency generation includes every registered variant.
# Register only this image's LuCI components, so unused apps cannot add
# qos/comgt/relayd/SSL dependencies to the aggregate package build rule.
python3 - <<'LUCIPY'
from pathlib import Path
p = Path("package/luci/Makefile")
s = p.read_text()
old = "$(foreach b,$(LUCI_BUILD_PACKAGES),$(eval $(call BuildPackage,$(b))))"
selected = "luci luci-base luci-lib-nixio luci-mod-admin-full luci-theme-bootstrap luci-app-firewall luci-proto-ppp"
new = "$(foreach b,$(filter " + selected + ",$(LUCI_BUILD_PACKAGES)),$(eval $(call BuildPackage,$(b))))"
assert old in s, "Pinned LuCI package registration changed"
p.write_text(s.replace(old, new))
LUCIPY

cp rtk_deconfig/defconfig_rtl8198c .config
cat >> .config <<'CONFIG'
CONFIG_PACKAGE_luci=y
CONFIG_PACKAGE_luci-base=y
CONFIG_PACKAGE_luci-base_source=y
CONFIG_PACKAGE_luci-mod-admin-full=y
CONFIG_PACKAGE_luci-theme-bootstrap=y
CONFIG_PACKAGE_luci-app-firewall=y
CONFIG_PACKAGE_luci-proto-ppp=y
CONFIG_PACKAGE_luci-lib-nixio=y
CONFIG_PACKAGE_luci-lib-nixio_notls=y
CONFIG_PACKAGE_lua=y
CONFIG_PACKAGE_libuci-lua=y
CONFIG_PACKAGE_libubus-lua=y
CONFIG_PACKAGE_libiwinfo-lua=y
CONFIG_PACKAGE_uhttpd=y
CONFIG_PACKAGE_uhttpd-mod-ubus=y
CONFIG

# The legacy OpenWrt/Realtek SDK explicitly refuses to compile as root.
# Prepare the tree as root, then run configuration and compilation as a normal user.
id -u builder >/dev/null 2>&1 || useradd -m -s /bin/bash builder
chown -R builder:builder /work/src

su -s /bin/bash builder -c '
  set -euo pipefail
  cd /work/src/rtk_openwrt_sdk
  make defconfig
  grep -qx "CONFIG_PACKAGE_luci=y" .config
  grep -qx "CONFIG_PACKAGE_luci-mod-admin-full=y" .config

  echo "=== SK-H724G target verification ==="
  grep -E "CONFIG_TARGET_rtkmips_rtl8198c|CONFIG_PACKAGE_kmod-rtl8192cd" .config | head -20 || true
  grep -E "CONFIG_SLOT_0_8192EE|CONFIG_SLOT_0_8194AE|CONFIG_SLOT_1_8814AE|CONFIG_WLAN_HAL_8192EE" target/linux/rtkmips/rtl8198c/config-3.10
  grep -n "0x81000000" target/linux/rtkmips/image/Makefile

  mkdir -p build_dir/host/firmware-utils/bin
  set -o pipefail
  make -j2 V=s 2>&1 | tee build-skh724g.log
'

# Validate the actual BIN, not just intermediate package output.
python3 - <<'PY'
from pathlib import Path
import hashlib, json, struct, subprocess

root = Path("/work/src/rtk_openwrt_sdk")
image = root / "bin/rtkmips/openwrt-rtkmips-rtl8198c-AP-fw.bin"
data = image.read_bytes()
signature, load, burn, length = struct.unpack(">4sIII", data[:16])
assert signature == b"cs6c", "Unexpected firmware signature"
assert load == 0x81000000 and burn == 0x60000, "Stock header address mismatch"
assert length == len(data) - 20, "Firmware header length mismatch"
assert data[-4:] == bytes.fromhex("deadc0de"), "Missing JFFS2 end marker"
payload = data[16:-4]
assert len(payload) % 2 == 0
assert sum(struct.unpack(">%dH" % (len(payload) // 2), payload)) & 0xffff == 0, "Bad checksum"
# Conservative engineering limit; this is NOT confirmation of a device bank size.
assert burn + len(data) <= 0x800000, "Image exceeds conservative 8 MiB test limit"
offset = next((i for i in range(0, len(data), 4096) if data[i:i+4] == b"hsqs"), None)
assert offset is not None, "No aligned SquashFS rootfs"
dest = Path("/tmp/skh724g-verified-rootfs")
subprocess.run(["unsquashfs", "-no-progress", "-d", str(dest), "-o", str(offset), str(image)], check=True)
for name in ("www/cgi-bin/luci", "usr/lib/lua/luci/dispatcher.lua",
             "usr/lib/lua/luci/controller/admin/index.lua", "etc/config/uhttpd"):
    assert (dest / name).is_file(), "Missing management file: " + name
assert "/www" in (dest / "etc/config/uhttpd").read_text()
kernel_configs = list((root / "build_dir").glob("target-*/linux-rtkmips_rtl8198c/linux-3.10.*/.config"))
assert len(kernel_configs) == 1, "Cannot identify final kernel config"
kernel = kernel_configs[0].read_text()
assert "CONFIG_SLOT_0_8192EE=y" in kernel
assert "CONFIG_SLOT_1_8814AE=y" in kernel
out = root / "bin/rtkmips"
(out / "build-config.txt").write_text((root / ".config").read_text())
(out / "kernel-config.txt").write_text(kernel)
report = {
    "status": "STATIC_CHECKS_PASSED_HARDWARE_BOOT_UNTESTED",
    "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
    "load_address": hex(load), "burn_address": hex(burn),
    "rootfs_image_offset": hex(offset), "rootfs_flash_offset": hex(burn + offset),
    "management": "LuCI 0.12", "default_lan_ip": "192.168.1.1",
    "source": "Realtek Barrier Breaker SDK; not current official OpenWrt",
    "web_upgrade_bank_selection": "UNVERIFIED",
    "hardware_boot": "UNTESTED"
}
(out / "firmware-validation.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
PY
