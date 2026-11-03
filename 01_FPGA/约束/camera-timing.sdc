create_clock -name {CAM_REF} -period 10.000 [get_ports {I_cam_ref_clk}]
create_clock -name {CAM_HS} -period 2.200 [get_ports {I_cam_clk_hs_p}]
derive_clocks


rename_clock -name {P2F_CLK0} [get_clocks {I_system/system_ARM_Processor_System_0_Inst/ARM_Processor_System_59fb6a0bf2ca_Inst/DR1_PHY_PROCESSOR_SYSTEM_Inst.p2f_clk0}]
rename_clock -name {P2F_CLK1} [get_clocks {I_system/system_ARM_Processor_System_0_Inst/ARM_Processor_System_59fb6a0bf2ca_Inst/DR1_PHY_PROCESSOR_SYSTEM_Inst.p2f_clk1}]
rename_clock -name {P2F_CLK2} [get_clocks {I_system/system_ARM_Processor_System_0_Inst/ARM_Processor_System_59fb6a0bf2ca_Inst/DR1_PHY_PROCESSOR_SYSTEM_Inst.p2f_clk2}]
rename_clock -name {VTC_CLK} [get_clocks {I_system/system_video_timing_generator_v01_0_Inst/video_timing_generator_v01_727902e0178c_Inst/dr1_pll_vtc_Inst/u_DR1_PHY_PLL.clkc[0]}]
rename_clock -name {PCLKX1} [get_clocks {U_pll/dr1_phy_pll_c1cfd523020a_Inst/u_DR1_PHY_PLL.clkc[0]}]
rename_clock -name {PCLKX2} [get_clocks {U_pll/dr1_phy_pll_c1cfd523020a_Inst/u_DR1_PHY_PLL.clkc[1]}]
set_clock_groups -name ASYNC -exclusive -group [get_clocks {P2F_CLK0}] -group [get_clocks {P2F_CLK1}] -group [get_clocks {P2F_CLK2}] -group [get_clocks {PCLKX1}] -group [get_clocks {PCLKX2}] -group [get_clocks {VTC_CLK}]
# Camera PLL domains and the sensor-derived DPHY clock are independent of PS.
# MIPI x1/x2/x4 stay in one group because their transfers are synchronous.
rename_clock -name CAM_PIXEL [get_clocks {u_camera/u_rx/u_rx_clk_gen/U_io_clk_div_1.clkdivout}]
rename_clock -name CAM_X2 [get_clocks {u_camera/u_rx/u_rx_clk_gen/U_io_clk_div_0.clkdivout}]
rename_clock -name CAM_X4 [get_clocks {u_camera/u_rx/u_rx_clk_gen/U_io_clk_div_0.clkout}]
rename_clock -name CAM_LP [get_clocks {u_camera/u_pll/dr1_phy_pll_Inst/u_DR1_PHY_PLL.clkc[2]}]
rename_clock -name CAM_CFG [get_clocks {u_camera/u_pll/dr1_phy_pll_Inst/u_DR1_PHY_PLL.clkc[3]}]
set_clock_groups -name CAMERA_CDC -asynchronous -group [get_clocks {CAM_HS CAM_PIXEL CAM_X2 CAM_X4}] -group [get_clocks {CAM_LP}] -group [get_clocks {CAM_CFG}] -group [get_clocks {P2F_CLK0 P2F_CLK1 P2F_CLK2 PCLKX1 PCLKX2 VTC_CLK}]

# PS reset crosses into the vendor's four-stage external-reset synchronizer.
# system.v connects p2f_rst0_n only to this synchronizer's external_reset.
# This exception excludes only the launch from that asynchronous reset output;
# all four synchronizer stages and all normal data/control paths remain timed.
set_false_path -from [get_pins {I_system/system_ARM_Processor_System_0_Inst/ARM_Processor_System_59fb6a0bf2ca_Inst/DR1_PHY_PROCESSOR_SYSTEM_Inst.p2f_clk0_rst_n}]
