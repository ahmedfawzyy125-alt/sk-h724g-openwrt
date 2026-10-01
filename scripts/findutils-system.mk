# Use the GNU findutils already provided by the GitHub runner.
# This is a host-build compatibility shim only; it does not change target firmware code.
include $(TOPDIR)/rules.mk

HOST_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/host-build.mk

define Host/Prepare
endef

define Host/Configure
endef

define Host/Compile
endef

define Host/Install
	mkdir -p $(STAGING_DIR_HOST)/bin
	/bin/cp -f /usr/bin/find $(STAGING_DIR_HOST)/bin/find
	/bin/cp -f /usr/bin/xargs $(STAGING_DIR_HOST)/bin/xargs
endef

$(eval $(call HostBuild))
