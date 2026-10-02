#!/usr/bin/env python3
from pathlib import Path
import hashlib
import shutil
import struct
import subprocess
import sys

root = Path('src/rtk_openwrt_sdk')
image = root / 'bin/rtkmips/openwrt-rtkmips-rtl8198c-AP-fw.bin'
if not image.is_file():
    raise SystemExit(f'Missing firmware image: {image}')

data = image.read_bytes()
if len(data) < 32:
    raise SystemExit('Firmware image is too small')

signature, load, burn, length = struct.unpack('>4sIII', data[:16])
assert signature == b'cs6c', f'bad signature: {signature!r}'
assert load == 0x81000000, f'bad load address: {load:#x}'
assert burn == 0x00060000, f'bad burn address: {burn:#x}'
assert length == len(data) - 20, f'bad header length: {length} != {len(data)-20}'
assert data[-4:] == bytes.fromhex('deadc0de'), 'missing deadc0de end marker'

payload = data[16:-4]
assert len(payload) % 2 == 0, 'payload word alignment is invalid'
words = struct.unpack('>%dH' % (len(payload) // 2), payload)
assert (sum(words) & 0xffff) == 0, 'firmware checksum is invalid'

# This offset is taken from the user-confirmed working web-upgrade image.
rootfs_offset = data.find(b'hsqs')
assert rootfs_offset == 0x1D1000, f'rootfs moved: {rootfs_offset:#x}'

# The known-working reference is 6,103,044 bytes. Smaller images are allowed;
# larger images require an explicit review before relaxing this guard.
assert len(data) <= 6103044, f'image grew beyond working reference size: {len(data)}'

sq = Path('/tmp/skh724g-rootfs.squashfs')
out = Path('/tmp/skh724g-rootfs-verify')
if out.exists():
    shutil.rmtree(out)
sq.write_bytes(data[rootfs_offset:-4])
subprocess.run(['unsquashfs', '-no-progress', '-d', str(out), str(sq)], check=True)

required = [
    'etc/init.d/skh724g-connectivity',
    'etc/uci-defaults/99-skh724g-connectivity-late',
    'etc/init.d/dnsmasq',
    'etc/init.d/uhttpd',
    'usr/sbin/rtk_txcalr',
]
for rel in required:
    p = out / rel
    assert p.exists(), f'missing runtime file: {rel}'

wifi_modules = list(out.glob('lib/modules/*/rtl8192cd.ko'))
assert wifi_modules, 'rtl8192cd.ko is missing from rootfs'

script = (out / 'etc/init.d/skh724g-connectivity').read_text(errors='replace')
for needle in ('192.168.1.1', 'modprobe rtl8192cd', 'rtk_txcalr -w', 'wifi detect', 'SK-H724G'):
    assert needle in script, f'connectivity recovery missing: {needle}'

print('SK-H724G firmware validation PASSED')
print('size=', len(data))
print('sha256=', hashlib.sha256(data).hexdigest())
print('signature=', signature.decode())
print('load=', hex(load), 'burn=', hex(burn))
print('rootfs_offset=', hex(rootfs_offset))
print('wifi_module=', wifi_modules[0])
