from pathlib import Path
import re

root = Path('src/rtk_openwrt_sdk/target/linux/rtkmips/files/drivers/net/wireless/rtl8192cd')

# Channel set taken from the requested LuCI screenshots / superchannel plan.
CHANNELS = [
    20,22,24,26,28,30,32,34,36,38,40,42,44,46,48,50,52,54,
    56,58,60,62,64,66,68,70,72,74,76,78,80,82,84,86,88,90,
    92,94,96,98,100,102,104,106,108,110,112,114,116,118,120,
    122,124,126,128,130,132,134,136,138,140,144,149,153,157,161
]


def read(path):
    return path.read_text(encoding='latin1')


def write(path, text):
    path.write_text(text, encoding='latin1')


# 1) Expand channel array capacity used by the vendor driver.
cfg = root / '8192cd_cfg.h'
s = read(cfg)
s2, n = re.subn(r'#define\s+MAX_CHANNEL_NUM\s+76', '#define MAX_CHANNEL_NUM\t\t192', s, count=1)
if n != 1 and 'MAX_CHANNEL_NUM\t\t192' not in s:
    raise RuntimeError('MAX_CHANNEL_NUM pattern not found')
write(cfg, s2)


# 2) Expand DOMAIN_5M10M available-channel list only. Normal country domains stay untouched.
util = root / '8192cd_util.c'
s = read(util)
s = s.replace('unsigned char channel[31];', 'unsigned char channel[192];')
row = '/* 5M10M */\t\t{{' + ','.join(str(x) for x in CHANNELS) + '},' + str(len(CHANNELS)) + '},'
pat = re.compile(r'/\*\s*5M10M\s*\*/\s*\{\{[^}]*\}\s*,\s*\d+\s*\}\s*,')
s2, n = pat.subn(row, s, count=1)
if n != 1:
    if row not in s:
        raise RuntimeError('DOMAIN_5M10M row not found')
    s2 = s
write(util, s2)


# 3) Add channel -> frequency mappings for non-standard entries so wl/iw/LuCI can display them.
comapi = root / '8192cd_comapi.c'
s = read(comapi)
marker = '/* SKH724G_SUPERCHANNEL_MAP */'
if marker not in s:
    existing = set()
    for ch, mhz in re.findall(r'\{\s*(\d+)\s*,\s*(\d+)\s*\}', s):
        existing.add(int(ch))
    additions = []
    for ch in CHANNELS:
        if ch not in existing:
            additions.append(f'\t{{{ch}, {5000 + ch * 5}}},')
    block = '\n\t' + marker + '\n' + '\n'.join(additions) + '\n\n\t'
    anchor = '/*\tUNII */'
    if anchor not in s:
        raise RuntimeError('CH_HZ_ID_MAP UNII anchor not found')
    s = s.replace(anchor, block + anchor, 1)
    write(comapi, s)

print('SK-H724G RTL8198C superchannel patch applied:', len(CHANNELS), 'channels')
print('Channels:', ','.join(str(x) for x in CHANNELS))
