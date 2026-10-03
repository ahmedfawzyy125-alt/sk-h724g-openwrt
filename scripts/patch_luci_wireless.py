#!/usr/bin/env python3
from pathlib import Path

luci = Path('/tmp/luci-012')
wifi = luci / 'modules/admin-full/luasrc/model/cbi/admin_network/wifi.lua'
overview = luci / 'modules/admin-full/luasrc/view/admin_network/wifi_overview.htm'
network = luci / 'modules/base/luasrc/model/network.lua'

s = wifi.read_text()

# 5 GHz mode / width controls. Only expose capabilities the driver reports.
old = '''\tmode = s:taboption("advanced", ListValue, "hwmode", translate("Band"))\n\n\tif hw_modes.n then\n'''
new = '''\tmode = s:taboption("advanced", ListValue, "hwmode", translate("Mode"))\n\n\tif hw_modes.ac then\n\t\tmode:value("11a", "AC")\n\t\tif hw_modes.n then mode:value("11na", "NA") end\n\n\t\thtmode = s:taboption("advanced", ListValue, "htmode", translate("Width"))\n\t\thtmode:value("VHT20", "20 MHz")\n\t\thtmode:value("VHT40", "40 MHz")\n\t\thtmode:value("VHT80", "80 MHz")\n\n\telseif hw_modes.n then\n'''
if old in s:
    s = s.replace(old, new, 1)

# Make the channel selector read like the requested layout and keep selection
# limited to frequencies the current driver/regulatory domain marks usable.
old_label = 'ch = s:taboption("general", Value, "channel", translate("Channel"))'
if old_label in s:
    s = s.replace(old_label, 'ch = s:taboption("general", Value, "channel", translate("Operating frequency"))', 1)

needle = '''\tfor _, f in ipairs(iw and iw.freqlist or { }) do\n\t\tif not f.restricted then\n\t\t\tch:value(f.channel, "%i (%.3f GHz)" %{ f.channel, f.mhz / 1000 })\n\t\tend\n\tend\nend\n'''
insert = '''\tfor _, f in ipairs(iw and iw.freqlist or { }) do\n\t\tif not f.restricted then\n\t\t\tch:value(f.channel, "%i (%i MHz)" %{ f.channel, f.mhz })\n\t\tend\n\tend\nend\n\n-- Show the complete frequency table reported by the Realtek driver. Entries\n-- marked restricted remain informational and are not made selectable here.\nallfreq = s:taboption("general", DummyValue, "_driver_frequencies", translate("Driver Frequency List"))\nallfreq.rawhtml = true\nfunction allfreq.cfgvalue()\n\tlocal out = { }\n\tfor _, f in ipairs(iw and iw.freqlist or { }) do\n\t\tlocal state = f.restricted and " <strong>[restricted]</strong>" or ""\n\t\tout[#out+1] = "%i (%i MHz)%s" %{ f.channel, f.mhz, state }\n\tend\n\treturn table.concat(out, "<br />")\nend\n'''
if needle in s:
    s = s.replace(needle, insert, 1)
elif 'Driver Frequency List' not in s:
    raise SystemExit('Could not find LuCI channel-list block')

# Rename the power label to match the requested UI while retaining driver values.
s = s.replace('"txpower", translate("Transmit Power"), "dBm")', '"txpower", translate("Maximum transmit power"), "dBm")')

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

print('LuCI 5GHz mode/width/channel/power + full driver frequency display patch applied')
