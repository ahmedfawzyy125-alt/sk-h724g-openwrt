# SK-H724G OpenWrt Cloud Builder

Cloud build workspace for the RTL8198C-based SK-H724G firmware experiment.

Hardware overrides targeted by this builder:
- RTL8198C
- kernel load address 0x81000000
- UART 115200
- Slot0 RTL8192EE with CONFIG_WLAN_HAL_8192EE=y
- Slot1 RTL8814AE

The workflow builds from cgoder/openwrt_rtk and uploads all generated firmware files plus the build log as a GitHub Actions artifact.
