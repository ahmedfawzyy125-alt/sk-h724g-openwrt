#!/usr/bin/env python3
from pathlib import Path

luci = Path('/tmp/luci-012')
wifi = luci / 'modules/admin-full/luasrc/model/cbi/admin_network/wifi.lua'
overview = luci / 'modules/admin-full/luasrc/view/admin_network/wifi_overview.htm'
network = luci / 'modules/base/luasrc/model/network.lua'

s = wifi.read_text()

old = '''\tmode = s:taboption("advanced", ListValue, "hwmode", translate("Band"))\n\n\tif hw_modes.n then\n'''
new = '''\tmode = s:taboption("advanced", ListValue, "hwmode", translate("Band"))\n\n\tif hw_modes.ac then\n\t\tmode:value("11a", "5GHz (802.11n+ac)")\n\n\t\thtmode = s:taboption("advanced", ListValue, "htmode", translate("VHT mode (802.11ac)"))\n\t\thtmode:value("", translate("disabled"))\n\t\thtmode:value("VHT20", "20MHz")\n\t\thtmode:value("VHT40", "40MHz")\n\t\thtmode:value("VHT80", "80MHz")\n\n\telseif hw_modes.n then\n'''
if old in s:
    s = s.replace(old, new, 1)

needle = '''\tfor _, f in ipairs(iw and iw.freqlist or { }) do\n\t\tif not f.restricted then\n\t\t\tch:value(f.channel, "%i (%.3f GHz)" %{ f.channel, f.mhz / 1000 })\n\t\tend\n\tend\nend\n'''
insert = '''\tfor _, f in ipairs(iw and iw.freqlist or { }) do\n\t\tif not f.restricted then\n\t\t\tch:value(f.channel, "%i (%.3f GHz)" %{ f.channel, f.mhz / 1000 })\n\t\tend\n\tend\nend\n\n-- Show every frequency reported by the driver, including entries the current\n-- regulatory domain marks restricted. Restricted entries are informational\n-- only; the selectable Channel list above remains limited to usable channels.\nallfreq = s:taboption("general", DummyValue, "_driver_frequencies", translate("Driver Frequency List"))\nfunction allfreq.cfgvalue()\n\tlocal out = { }\n\tfor _, f in ipairs(iw and iw.freqlist or { }) do\n\t\tlocal state = f.restricted and " [restricted]" or ""\n\t\tout[#out+1] = "%i = %.3f GHz%s" %{ f.channel, f.mhz / 1000, state }\n\tend\n\treturn table.concat(out, " | ")\nend\n'''
if needle in s:
    s = s.replace(needle, insert, 1)
else:
    raise SystemExit('Could not find LuCI channel-list block')

wifi.write_text(s)

if overview.exists():
    t = overview.read_text()
    old = '''\t\t\t\tif bl.n then bands = bands .. "n" end\n'''
    if old in t and 'if bl.ac then bands = bands .. "ac" end' not in t:
        t = t.replace(old, old + '''\t\t\t\tif bl.ac then bands = bands .. "ac" end\n''', 1)
    overview.write_text(t)

if network.exists():
    t = network.read_text()
    old = '''\tif l.n then m = m .. "n" end\n'''
    if old in t and 'if l.ac then m = "ac" end' not in t:
        t = t.replace(old, old + '''\tif l.ac then m = "ac" end\n''', 1)
    network.write_text(t)

print('LuCI Realtek 11n/11ac + full driver frequency display patch applied')
