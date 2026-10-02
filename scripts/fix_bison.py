from pathlib import Path

p = Path('src/rtk_openwrt_sdk/tools/bison/Makefile')
s = p.read_text()
marker = 'include $(INCLUDE_DIR)/host-build.mk\n'
compat = marker + '''\ndefine Host/Prepare
\t$(call Host/Prepare/Default)
\t$(SED) 's/defined _IO_ftrylockfile/defined _IO_EOF_SEEN/g' $(HOST_BUILD_DIR)/lib/fseterr.c
endef
'''

if "defined _IO_EOF_SEEN/g" not in s:
    if marker not in s:
        raise RuntimeError('bison host-build include missing')
    s = s.replace(marker, compat, 1)
    p.write_text(s)

print('Bison 3.0.2 glibc compatibility fix applied')
