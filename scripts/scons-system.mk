# Use the SCons package already provided by the GitHub runner.
# This avoids legacy SCons 2.3.1 requiring Python 2 and does not change target firmware code.
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
	/bin/cp -f /usr/bin/scons $(STAGING_DIR_HOST)/bin/scons
endef

$(eval $(call HostBuild))
