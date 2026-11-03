/************************************************************\
**	Copyright (c) 2012-2025 Anlogic Inc.
**	All Right Reserved.
\************************************************************/
/************************************************************\
**	Build time: Oct 04 2025 19:09:37
**	TD version	:	6.2.175876
************************************************************/
module pll
(
  input                         refclk,
  output                        clk0_out,
  output                        clk1_out,
  output                        lock,
  input                         reset
);

  dr1_phy_pll_c1cfd523020a
  #(
      .FBKCLK("VCO_PHASE0"),
      .FBKCLK_INT("VCO_PHASE0"),
      .REFCLK_DIV(2),
      .FBCLK_DIV(59),
      .CLKC0_FPHASE(0),
      .CLKC1_FPHASE(0),
      .CLKC0_CPHASE(9),
      .CLKC1_CPHASE(1),
      .CLKC0_DIV(10),
      .CLKC1_DIV(2),
      .CLKC0_DUTY_INT(5),
      .CLKC1_DUTY_INT(1),
      .CLKC0_ENABLE("ENABLE"),
      .CLKC1_ENABLE("ENABLE"),
      .FIN("50.0"),
      .FEEDBK_MODE("NOCOMP"),
      .PLL_USR_RST("ENABLE"),
      .PLL_FEED_TYPE("INTERNAL"),
      .LPF_RES(3),
      .LPF_CAP(2),
      .ICP_CUR(11),
      .GMC_GAIN(1),
      .FRAC_ENABLE("ENABLE"),
      .DITHER_ENABLE("DISABLE"),
      .SDM_FRAC(1638),
      .SSC_AMP(0.0000),
      .MPHASE_ENABLE("DISABLE"),
      .DYN_PHASE_PATH_SEL("DISABLE"),
      .DYN_FPHASE_EN("DISABLE"),
      .CLKC0_FPHASE_RSTSEL(0),
      .CLKC1_FPHASE_RSTSEL(0),
      .CLKC0_DUTY50("ENABLE"),
      .CLKC1_DUTY50("ENABLE"),
      .INTPI(1),
      .SSC_ENABLE("DISABLE"),
      .SSC_MODE("DOWN"),
      .SSC_FREQ_DIV(0),
      .SSC_RNGE(0),
      .HIGH_SPEED_EN("DISABLE")
  )dr1_phy_pll_c1cfd523020a_Inst
  (
      .refclk(refclk),
      .clk0_out(clk0_out),
      .clk1_out(clk1_out),
      .lock(lock),
      .reset(reset)
  );
endmodule
