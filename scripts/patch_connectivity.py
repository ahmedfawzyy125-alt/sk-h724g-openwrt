from pathlib import Path

root = Path('src/rtk_openwrt_sdk')
base = root / 'target/linux/rtkmips/base-files'
(base / 'etc/init.d').mkdir(parents=True, exist_ok=True)
(base / 'etc/uci-defaults').mkdir(parents=True, exist_ok=True)

# Run late in boot, after kernel modules and netifd are available.  The old
# one-shot uci-defaults stage can be too early for rtl8192cd PHY discovery.
init = base / 'etc/init.d/skh724g-connectivity'
init.write_text(r'''#!/bin/sh /etc/rc.common
START=98
STOP=10

boot() {
    start
}

start() {
    [ -e /etc/skh724g-connectivity-ready ] && return 0

    exec >>/tmp/skh724g-connectivity.log 2>&1
    echo "SK-H724G connectivity recovery start"
    date

    # The stock SK-H724G bridge contains eth0 + eth1. Bring both CPU-side
    # Ethernet interfaces up before asking netifd to create br-lan.
    ifconfig eth0 up 2>/dev/null || true
    ifconfig eth1 up 2>/dev/null || true

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
    /etc/init.d/dnsmasq enable 2>/dev/null || true
    /etc/init.d/dnsmasq restart 2>/dev/null || true
    /etc/init.d/uhttpd enable 2>/dev/null || true
    /etc/init.d/uhttpd restart 2>/dev/null || true

    # rtl8192cd is packaged with AutoProbe, but on this legacy SDK PHY
    # registration may finish after uci-defaults. Retry discovery for up to
    # ~30 seconds instead of permanently writing an empty wireless config.
    tries=0
    while [ "$tries" -lt 10 ]; do
        tries=$((tries + 1))
        echo "wifi discovery try $tries"
        [ -d /sys/class/ieee80211 ] && ls -la /sys/class/ieee80211 || true
        ifconfig -a 2>/dev/null || true

        if [ -z "$(uci -q show wireless | sed -n "s/^wireless\.\([^.=]*\)=wifi-device.*/\1/p")" ]; then
            tmp=/tmp/wireless.detected
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
    [ -n "$devices" ] || {
        echo "ERROR: no wifi-device detected; leaving marker absent so next boot retries"
        return 1
    }

    for dev in $devices; do
        uci -q set wireless.$dev.disabled='0'
    done

    # If detection produced devices but no VIF, create an AP VIF per radio.
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
    sleep 3

    # Success requires both management bridge/IP and at least one Wi-Fi
    # interface. Do not mark complete if either side is missing.
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

    echo "ERROR: connectivity validation failed; next boot will retry"
    return 1
}
''')
init.chmod(0o755)

# Keep uci-defaults tiny: only enable the late service and launch one delayed
# attempt on the first boot. The late service does the actual hardware-aware
# work and only writes its persistent success marker after validation.
defaults = base / 'etc/uci-defaults/99-skh724g-connectivity-late'
defaults.write_text(r'''#!/bin/sh
/etc/init.d/skh724g-connectivity enable 2>/dev/null || true
(
    sleep 8
    /etc/init.d/skh724g-connectivity start
) >/tmp/skh724g-connectivity-bootstrap.log 2>&1 &
exit 0
''')
defaults.chmod(0o755)

# Remove the earlier one-shot script if patch_sdk.py created it. It can run
# before rtl8192cd has registered PHYs and therefore create an empty config.
early = base / 'etc/uci-defaults/99-skh724g-connectivity'
if early.exists():
    early.unlink()

print('SK-H724G late LAN/DHCP/Wi-Fi recovery patch applied')
