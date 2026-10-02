from pathlib import Path

root = Path('src/rtk_openwrt_sdk')
base = root / 'target/linux/rtkmips/base-files'
(base / 'etc/init.d').mkdir(parents=True, exist_ok=True)
(base / 'etc/uci-defaults').mkdir(parents=True, exist_ok=True)

# Late, persistent recovery service for SK-H724G. The known-working upgrade
# image uses the same cs6c/load/burn/rootfs layout as our build, so runtime
# connectivity is the critical path: bring LAN up even if netifd is late,
# explicitly load rtl8192cd, then rerun Realtek calibration after wlan exists.
init = base / 'etc/init.d/skh724g-connectivity'
init.write_text(r'''#!/bin/sh /etc/rc.common
START=98
STOP=10

boot() {
    start
}

start() {
    exec >>/tmp/skh724g-connectivity.log 2>&1
    echo "SK-H724G connectivity recovery start"
    date

    # LAN hard fallback: repair br-lan first so management stays reachable
    # even if legacy netifd/switch initialization is late.
    ifconfig eth0 up 2>/dev/null || true
    ifconfig eth1 up 2>/dev/null || true
    brctl addbr br-lan 2>/dev/null || true
    for p in eth0 eth1; do
        [ -d "/sys/class/net/$p" ] || continue
        brctl addif br-lan "$p" 2>/dev/null || true
    done
    ifconfig br-lan 192.168.1.1 netmask 255.255.255.0 up 2>/dev/null || true

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

    /etc/init.d/network restart 2>/dev/null || true
    sleep 2
    ifconfig br-lan 192.168.1.1 netmask 255.255.255.0 up 2>/dev/null || true
    /etc/init.d/dnsmasq enable 2>/dev/null || true
    /etc/init.d/dnsmasq restart 2>/dev/null || true
    /etc/init.d/uhttpd enable 2>/dev/null || true
    /etc/init.d/uhttpd restart 2>/dev/null || true

    # Explicitly retry the Realtek WLAN module. AutoProbe should normally do
    # this, but the failed image showed no broadcast at all.
    modprobe rtl8192cd 2>/dev/null || insmod rtl8192cd 2>/dev/null || true

    # Wait up to 60 seconds for vendor wlan/PHY registration. Once wlan is
    # present, rerun Realtek TX calibration at the correct time; stock rtk_app
    # can execute before the radio has finished registering.
    tries=0
    while [ "$tries" -lt 20 ]; do
        tries=$((tries + 1))
        echo "wifi discovery try $tries"
        [ -d /sys/class/ieee80211 ] && ls -la /sys/class/ieee80211 2>/dev/null || true
        ifconfig -a 2>/dev/null || true

        if [ -d /sys/class/net/wlan0 ] || [ -d /sys/class/net/wlan1 ]; then
            /usr/sbin/rtk_txcalr -w 2>/dev/null || true
        fi

        if [ -z "$(uci -q show wireless | sed -n "s/^wireless\.\([^.=]*\)=wifi-device.*/\1/p")" ]; then
            tmp=/tmp/wireless.detected
            : > "$tmp"
            wifi detect > "$tmp" 2>/dev/null || true
            if grep -q "=wifi-device" "$tmp" 2>/dev/null; then
                cp "$tmp" /etc/config/wireless
            fi
        fi

        devices="$(uci -q show wireless | sed -n "s/^wireless\.\([^.=]*\)=wifi-device.*/\1/p")"
        [ -n "$devices" ] && break
        sleep 3
    done

    devices="$(uci -q show wireless | sed -n "s/^wireless\.\([^.=]*\)=wifi-device.*/\1/p")"
    if [ -n "$devices" ]; then
        for dev in $devices; do
            uci -q set wireless.$dev.disabled='0'
        done

        vifs="$(uci -q show wireless | sed -n "s/^wireless\.\([^.=]*\)=wifi-iface.*/\1/p")"
        if [ -z "$vifs" ]; then
            n=0
            for dev in $devices; do
                sec="skh724g_ap$n"
                uci -q set wireless.$sec='wifi-iface'
                uci -q set wireless.$sec.device="$dev"
                uci -q set wireless.$sec.mode='ap'
                uci -q set wireless.$sec.network='lan'
                uci -q set wireless.$sec.encryption='none'
                if [ "$n" -eq 0 ]; then
                    uci -q set wireless.$sec.ssid='SK-H724G'
                else
                    uci -q set wireless.$sec.ssid="SK-H724G-$n"
                fi
                n=$((n + 1))
            done
        else
            n=0
            for vif in $vifs; do
                uci -q set wireless.$vif.mode='ap'
                uci -q set wireless.$vif.network='lan'
                uci -q set wireless.$vif.encryption='none'
                if [ "$n" -eq 0 ]; then
                    uci -q set wireless.$vif.ssid='SK-H724G'
                else
                    uci -q set wireless.$vif.ssid="SK-H724G-$n"
                fi
                n=$((n + 1))
            done
        fi
        uci -q commit wireless
        wifi down 2>/dev/null || true
        sleep 1
        wifi up 2>/dev/null || wifi 2>/dev/null || true
    else
        echo "WARN: no UCI wifi-device detected after 60s"
    fi

    sleep 3
    /usr/sbin/rtk_txcalr -w 2>/dev/null || true

    lan_ok=0
    wifi_ok=0
    ifconfig br-lan 2>/dev/null | grep -q '192\.168\.1\.1' && lan_ok=1
    if ifconfig -a 2>/dev/null | grep -Eq '^(wlan|ra)[0-9]'; then wifi_ok=1; fi

    echo "LAN_OK=$lan_ok WIFI_OK=$wifi_ok"
    if [ "$lan_ok" -eq 1 ] && [ "$wifi_ok" -eq 1 ]; then
        touch /etc/skh724g-connectivity-ready
        echo "SK-H724G connectivity recovery complete"
        return 0
    fi

    echo "ERROR: connectivity validation failed; will retry next boot"
    return 1
}
''')
init.chmod(0o755)

defaults = base / 'etc/uci-defaults/99-skh724g-connectivity-late'
defaults.write_text(r'''#!/bin/sh
/etc/init.d/skh724g-connectivity enable 2>/dev/null || true
(
    sleep 10
    /etc/init.d/skh724g-connectivity start
) >/tmp/skh724g-connectivity-bootstrap.log 2>&1 &
exit 0
''')
defaults.chmod(0o755)

early = base / 'etc/uci-defaults/99-skh724g-connectivity'
if early.exists():
    early.unlink()

print('SK-H724G hardened LAN/DHCP/Wi-Fi recovery patch applied')
