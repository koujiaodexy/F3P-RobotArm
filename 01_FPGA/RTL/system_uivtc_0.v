/************************************************************\
**	Copyright (c) 2012-2025 Anlogic Inc.
**	All Right Reserved.
\************************************************************/
/************************************************************\
**	Build time: Sep 30 2025 15:58:13
**	TD version	:	6.2.175876
************************************************************/
`timescale 1ns / 1ns  
module system_uivtc_0
(
  input                         I_vtc_rstn,
  input                         I_vtc_clk,
  output                        O_vtc_vs,
  output                        O_vtc_hs,
  output                        O_vtc_de_valid,
  output                        O_vtc_user,
  output                        O_vtc_last
);

  uivtc_717760ec1b25
  #(
      .H_ActiveSize(1920),
      .H_FrameSize(2200),
      .H_SyncStart(2008),
      .H_SyncEnd(2052),
      .V_ActiveSize(1080),
      .V_FrameSize(1125),
      .V_SyncStart(1084),
      .V_SyncEnd(1089)
  )uivtc_717760ec1b25_Inst
  (
      .I_vtc_rstn(I_vtc_rstn),
      .I_vtc_clk(I_vtc_clk),
      .O_vtc_vs(O_vtc_vs),
      .O_vtc_hs(O_vtc_hs),
      .O_vtc_de_valid(O_vtc_de_valid),
      .O_vtc_user(O_vtc_user),
      .O_vtc_last(O_vtc_last)
  );
endmodule
