# Use system GNU m4 as the host build tool.
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
	/bin/cp -f /usr/bin/m4 $(STAGING_DIR_HOST)/bin/m4
endef

$(eval $(call HostBuild))
