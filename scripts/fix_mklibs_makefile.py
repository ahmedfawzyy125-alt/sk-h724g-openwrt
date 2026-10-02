#!/usr/bin/env python3
from pathlib import Path

p = Path('src/rtk_openwrt_sdk/tools/mklibs/Makefile')
s = p.read_text()
marker = 'HOST_LDFLAGS += $(HOST_STATIC_LINKING)\n'
needle = 'mklibs modern-GCC source fix applied'

block = r'''

# mklibs 0.1.35 uses dynamic exception specifications such as
# throw(std::bad_alloc). Modern GCC rejects them in its default C++ mode.
# Run this after every host-source unpack so OpenWrt cannot restore the
# incompatible source during a later prepare/rebuild.
define Host/Prepare
	$(call Host/Prepare/Default)
	find $(HOST_BUILD_DIR) -type f \( -name '*.cpp' -o -name '*.cc' -o -name '*.h' -o -name '*.hpp' \) -exec sed -i -E 's/[[:space:]]+throw[[:space:]]*\([^)]*\)//g' {} +
	@if grep -RInE 'throw[[:space:]]*\([^)]*\)' $(HOST_BUILD_DIR) --include='*.cpp' --include='*.cc' --include='*.h' --include='*.hpp'; then echo 'ERROR: dynamic exception specifications remain in mklibs'; exit 1; else echo 'mklibs modern-GCC source fix applied'; fi
endef
'''

if needle not in s:
    if marker not in s:
        raise RuntimeError('mklibs Makefile insertion marker missing')
    s = s.replace(marker, marker + block, 1)
    p.write_text(s)

print('Persistent mklibs Host/Prepare compatibility fix installed')
