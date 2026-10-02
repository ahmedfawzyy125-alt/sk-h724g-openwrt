from pathlib import Path

root = Path('src/rtk_openwrt_sdk')


def rep(rel, old, new, required=True):
    p = root / rel
    s = p.read_text()
    if old not in s:
        if required:
            print('WARN missing pattern', rel, repr(old[:100]))
        return
    p.write_text(s.replace(old, new))


# SK-H724G: RTL8198C + RTL8192EE + RTL8814AE
p = root / 'target/linux/rtkmips/rtl8198c/config-3.10'
s = p.read_text()
s = s.replace(
    '# CONFIG_SLOT_0_8192EE is not set\nCONFIG_SLOT_0_8194AE=y',
    'CONFIG_SLOT_0_8192EE=y\n# CONFIG_SLOT_0_8194AE is not set',
)
if 'CONFIG_WLAN_HAL_8192EE=y' not in s:
    s = s.replace('CONFIG_WLAN_HAL=y\n', 'CONFIG_WLAN_HAL=y\nCONFIG_WLAN_HAL_8192EE=y\n')
p.write_text(s)

# Stock SK-H724G kernel load address + serial speed.
p = root / 'target/linux/rtkmips/image/Makefile'
s = p.read_text().replace('ttyS0,38400', 'ttyS0,115200').replace('0x80500000', '0x81000000')
p.write_text(s)

# SK-H724G recovery networking + first-boot Wi-Fi defaults.
# Keep management reachable on both CPU Ethernet interfaces and explicitly
# generate/enable wireless configuration on first boot.
base = root / 'target/linux/rtkmips/base-files'
(base / 'etc/uci-defaults').mkdir(parents=True, exist_ok=True)
recovery = base / 'etc/uci-defaults/99-skh724g-connectivity'
recovery.write_text(r'''#!/bin/sh
uci -q batch <<'EOF'
set network.lan='interface'
set network.lan.type='bridge'
set network.lan.ifname='eth0 eth1'
set network.lan.proto='static'
set network.lan.ipaddr='192.168.1.1'
set network.lan.netmask='255.255.255.0'
set dhcp.lan='dhcp'
set dhcp.lan.interface='lan'
set dhcp.lan.start='100'
set dhcp.lan.limit='100'
set dhcp.lan.leasetime='12h'
set dhcp.lan.ignore='0'
EOF
uci -q commit network
uci -q commit dhcp

if [ ! -s /etc/config/wireless ]; then
    wifi detect > /etc/config/wireless 2>/dev/null || true
fi

for dev in $(uci -q show wireless | sed -n "s/^wireless\.\([^.=]*\)=wifi-device.*/\1/p"); do
    uci -q set wireless.$dev.disabled='0'
done

idx=0
for vif in $(uci -q show wireless | sed -n "s/^wireless\.\([^.=]*\)=wifi-iface.*/\1/p"); do
    uci -q set wireless.$vif.mode='ap'
    uci -q set wireless.$vif.network='lan'
    uci -q set wireless.$vif.encryption='none'
    if [ "$idx" -eq 0 ]; then
        uci -q set wireless.$vif.ssid='SK-H724G'
    else
        uci -q set wireless.$vif.ssid="SK-H724G-$idx"
    fi
    idx=$((idx + 1))
done
uci -q commit wireless

/etc/init.d/dnsmasq enable 2>/dev/null || true
/etc/init.d/uhttpd enable 2>/dev/null || true
/etc/init.d/network restart 2>/dev/null || true
/etc/init.d/dnsmasq restart 2>/dev/null || true
/etc/init.d/uhttpd restart 2>/dev/null || true
wifi 2>/dev/null || true
exit 0
''')
recovery.chmod(0o755)


# Do not inject legacy staging libraries into modern host /bin/sh.
p = root / 'include/toplevel.mk'
s = p.read_text()
s = s.replace(
    'export LD_LIBRARY_PATH:=$(subst ::,:,$(if $(LD_LIBRARY_PATH),$(LD_LIBRARY_PATH):)$(STAGING_DIR_HOST)/lib)',
    'export LD_LIBRARY_PATH:=',
)
s = s.replace(
    'export DYLD_LIBRARY_PATH:=$(subst ::,:,$(if $(DYLD_LIBRARY_PATH),$(DYLD_LIBRARY_PATH):)$(STAGING_DIR_HOST)/lib)',
    'export DYLD_LIBRARY_PATH:=',
)
p.write_text(s)

# findutils 4.4.2 contains old gnulib tests removed by glibc 2.28+.
p = root / 'tools/findutils/Makefile'
s = p.read_text()
marker = 'include $(INCLUDE_DIR)/host-build.mk\n'
compat = (
    marker
    + '\ndefine Host/Prepare\n'
    + '\t$(call Host/Prepare/Default)\n'
    + "\t$(SED) 's/_IO_ftrylockfile/_IO_EOF_SEEN/g' $(HOST_BUILD_DIR)/lib/*.c $(HOST_BUILD_DIR)/gnulib/lib/*.c\n"
    + "\tprintf '\\n#ifndef _IO_IN_BACKUP\\n#define _IO_IN_BACKUP 0x100\\n#endif\\n' >> $(HOST_BUILD_DIR)/lib/stdio-impl.h\n"
    + "\tprintf '\\n#ifndef _IO_IN_BACKUP\\n#define _IO_IN_BACKUP 0x100\\n#endif\\n#ifndef _IO_ferror_unlocked\\n#define _IO_ferror_unlocked(_fp) ferror_unlocked(_fp)\\n#endif\\n' >> $(HOST_BUILD_DIR)/gnulib/lib/stdio-impl.h\n"
    + "\tsed -i '/#include <unistd.h>/a #include <sys/sysmacros.h>' $(HOST_BUILD_DIR)/gnulib/lib/mountlist.c || true\n"
    + 'endef\n'
)
if 'define Host/Prepare' not in s:
    s = s.replace(marker, compat, 1)
p.write_text(s)

# Only build packages required by the known RTL8198C config.
p = root / 'package/Makefile'
s = p.read_text()
old = '$(curdir)/builddirs:=$(sort $(package-) $(package-y) $(package-m))'
new = '$(curdir)/builddirs:=luci base-files firmware/linux-firmware kernel/fastpath kernel/linux kernel/mac80211 kernel/rtl_fs kernel/rtl_nf kernel/rtl_sendfile libs/gettext libs/gmp libs/libiconv libs/libjson-c libs/libnl-tiny libs/libpcap libs/libtool libs/libubox libs/lzo libs/ncurses libs/nettle libs/ocf-crypto-headers libs/openssl libs/polarssl libs/toolchain libs/ustream-ssl libs/zlib network/config/firewall network/config/netifd network/ipv6/odhcp6c network/services/dnsmasq network/services/dropbear network/services/hostapd network/services/igmpproxy network/services/odhcpd network/services/ppp network/services/uhttpd network/utils/iptables network/utils/iw network/utils/iwinfo network/utils/linux-atm network/utils/resolveip network/utils/wireless-tools system/fstools system/mtd system/opkg system/procd system/ubox system/ubus system/uci utils/busybox utils/jsonfilter utils/lua utils/px5g utils/rtk_app utils/ubi-utils utils/util-linux'
s = s.replace(old, new)
p.write_text(s)

# Dead/legacy fetch URLs used by selected packages.
replacements = {
    'package/libs/librpc/Makefile': ('git://nbd.name/uclibc-rpc.git', 'https://github.com/openwrt/uclibc-rpc.git'),
    'package/libs/ustream-ssl/Makefile': ('git://nbd.name/ustream-ssl.git', 'https://github.com/openwrt/ustream-ssl.git'),
    'package/network/config/firewall/Makefile': ('git://nbd.name/firewall3.git', 'https://github.com/openwrt/firewall3.git'),
    'package/network/ipv6/odhcp6c/Makefile': ('git://github.com/sbyx/odhcp6c.git', 'https://github.com/sbyx/odhcp6c.git'),
    'package/network/services/hostapd/Makefile': ('git://w1.fi/srv/git/hostap.git', 'https://w1.fi/hostap.git'),
    'package/network/services/odhcpd/Makefile': ('git://github.com/sbyx/odhcpd.git', 'https://github.com/sbyx/odhcpd.git'),
    'package/network/services/relayd/Makefile': ('git://nbd.name/relayd.git', 'https://github.com/openwrt/relayd.git'),
    'package/network/services/uhttpd/Makefile': ('git://nbd.name/uhttpd2.git', 'https://git.openwrt.org/project/uhttpd.git'),
    'package/system/fstools/Makefile': ('git://nbd.name/fstools.git', 'https://github.com/openwrt/fstools.git'),
    'package/system/procd/Makefile': ('git://nbd.name/luci2/procd.git', 'https://github.com/openwrt/procd.git'),
    'package/system/ubox/Makefile': ('git://nbd.name/luci2/ubox.git', 'https://github.com/openwrt/ubox.git'),
    'package/system/ubus/Makefile': ('git://nbd.name/luci2/ubus.git', 'https://github.com/openwrt/ubus.git'),
    'package/system/uci/Makefile': ('git://nbd.name/uci.git', 'https://github.com/openwrt/uci.git'),
    'tools/mtd-utils/Makefile': ('git://git.infradead.org/mtd-utils.git', 'https://github.com/sigma-star/mtd-utils.git'),
}
for rel, (a, b) in replacements.items():
    rep(rel, a, b, False)

# Avoid unconditional ath10k firmware fetch when ath10k is not selected.
p = root / 'package/kernel/mac80211/Makefile'
s = p.read_text()
s = s.replace(
    '$(eval $(call Download,ath10k-firmware))',
    'ifneq ($(CONFIG_PACKAGE_kmod-ath10k),)\n$(eval $(call Download,ath10k-firmware))\nendif',
    1,
)
s = s.replace(
    '\t$(TAR) -C $(PKG_BUILD_DIR) -xjf $(DL_DIR)/$(PKG_ATH10K_LINUX_FIRMWARE_SOURCE)',
    'ifneq ($(CONFIG_PACKAGE_kmod-ath10k),)\n\t$(TAR) -C $(PKG_BUILD_DIR) -xjf $(DL_DIR)/$(PKG_ATH10K_LINUX_FIRMWARE_SOURCE)\nendif',
    1,
)
p.write_text(s)

# Old GCC host build: keep old C++ language mode on modern compilers.
p = root / 'toolchain/gcc/common.mk'
s = p.read_text()
needle = '\t\tCFLAGS="$(HOST_CFLAGS)" \\\n'
if 'CXXFLAGS="-O1 -std=gnu++98"' not in s and needle in s:
    s = s.replace(needle, needle + '\t\tCXXFLAGS="-O1 -std=gnu++98" \\\n', 1)
p.write_text(s)


# Escape literal opening braces in legacy Automake regexes for Perl 5.26+.
p = root / 'tools/automake/Makefile'
s = p.read_text()
marker = 'include $(INCLUDE_DIR)/host-build.mk\n'
command = '''\tpython3 -c 'from pathlib import Path; p = Path("$(HOST_BUILD_DIR)/automake.in"); s = p.read_text(); old = chr(92)+chr(36)+"{([^ "+chr(92)+"t=:+{}]+)}"; new = chr(92)+chr(36)+chr(92)+"{([^ "+chr(92)+"t=:+{}]+)}"; assert old in s or new in s, "Automake Perl pattern missing"; p.write_text(s.replace(old, new))'\n'''
# GNU make consumes dollars once before passing the command to the shell.
command = command.replace(chr(36) + '{', chr(36) * 2 + '{')
compat = marker + '\ndefine Host/Prepare\n\t$(call Host/Prepare/Default)\n' + command + 'endef\n'
if 'Automake Perl pattern missing' not in s:
    if marker not in s:
        raise RuntimeError('Automake host-build include missing')
    p.write_text(s.replace(marker, compat, 1))


# Replace retired kernel.org mirror domain; retain SDK archive checksums.
rep('scripts/download.pl', 'ftp://ftp.all.kernel.org/pub/$dir', 'https://cdn.kernel.org/pub/$dir')
rep('scripts/download.pl', 'http://ftp.all.kernel.org/pub/$dir', 'https://mirrors.edge.kernel.org/pub/$dir')


# Resolve newly introduced Wi-Fi Kconfig symbols before modules and vermagic.
rep(
    'include/kernel-defaults.mk',
    '\t$(call Kernel/SetNoInitramfs)\n\trm -rf $(KERNEL_BUILD_DIR)/modules',
    '\t$(call Kernel/SetNoInitramfs)\n\t+$(MAKE) $(KERNEL_MAKEOPTS) olddefconfig\n\trm -rf $(KERNEL_BUILD_DIR)/modules',
)


# Do not register the unused CyaSSL variant's dependency in this SDK build.
rep('package/libs/ustream-ssl/Makefile',
    '$(eval $(call BuildPackage,libustream-cyassl))',
    'ifneq ($(CONFIG_PACKAGE_libustream-cyassl),)\n$(eval $(call BuildPackage,libustream-cyassl))\nendif')

# Lua is now required by LuCI; use the official HTTPS archive endpoint.
rep('package/utils/lua/Makefile', 'http://www.lua.org/ftp/', 'https://www.lua.org/ftp/')
print('SK-H724G SDK patches applied')
