/************************************************************\
**	Copyright (c) 2012-2025 Anlogic Inc.
**	All Right Reserved.
\************************************************************/
/************************************************************\
**	Build time: Oct 08 2025 19:45:13
**	TD version	:	6.2.175876
************************************************************/
module system_uivbuf_0
(
  input                         I_ui_clk,
  input                         I_ui_rstn,
  input                         I_W_sync,
  input                         I_W_wclk,
  input                         I_W_tuser,
  input                         I_W_tvalid,
  input   [31:0]                I_W_tdata,
  input                         I_W_tlast,
  output                        O_W_tready,
  output                        O_W_tlocked,
  output                        O_s2mm_tuser,
  output                        O_s2mm_tvalid,
  output  [63:0]                O_s2mm_tdata,
  input                         I_s2mm_tready,
  output                        O_s2mm_tlast,
  input                         I_R_sync,
  input                         I_R_rclk,
  input                         I_R_tready,
  output                        O_R_tuser,
  output                        O_R_tvalid,
  output  [31:0]                O_R_tdata,
  output                        O_R_tlast,
  output                        O_R_tlocked,
  input                         I_mm2s_tuser,
  input                         I_mm2s_tvalid,
  input   [63:0]                I_mm2s_tdata,
  output                        O_mm2s_tready,
  input                         I_mm2s_tlast
);

  uivbuf_87cc5c5f324a
  #(
      .AXI_DATA_WIDTH(64),
      .W_BUFDEPTH(2048),
      .W_DATAWIDTH(32),
      .W_XSIZE(1920),
      .W_YSIZE(1080),
      .W_XDIV(1),
      .R_BUFDEPTH(2048),
      .R_DATAWIDTH(32),
      .R_XSIZE(1920),
      .R_YSIZE(1080),
      .R_XDIV(1)
  )uivbuf_87cc5c5f324a_Inst
  (
      .I_ui_clk(I_ui_clk),
      .I_ui_rstn(I_ui_rstn),
      .I_W_sync(I_W_sync),
      .I_W_wclk(I_W_wclk),
      .I_W_tuser(I_W_tuser),
      .I_W_tvalid(I_W_tvalid),
      .I_W_tdata(I_W_tdata),
      .I_W_tlast(I_W_tlast),
      .O_W_tready(O_W_tready),
      .O_W_tlocked(O_W_tlocked),
      .O_s2mm_tuser(O_s2mm_tuser),
      .O_s2mm_tvalid(O_s2mm_tvalid),
      .O_s2mm_tdata(O_s2mm_tdata),
      .I_s2mm_tready(I_s2mm_tready),
      .O_s2mm_tlast(O_s2mm_tlast),
      .I_R_sync(I_R_sync),
      .I_R_rclk(I_R_rclk),
      .I_R_tready(I_R_tready),
      .O_R_tuser(O_R_tuser),
      .O_R_tvalid(O_R_tvalid),
      .O_R_tdata(O_R_tdata),
      .O_R_tlast(O_R_tlast),
      .O_R_tlocked(O_R_tlocked),
      .I_mm2s_tuser(I_mm2s_tuser),
      .I_mm2s_tvalid(I_mm2s_tvalid),
      .I_mm2s_tdata(I_mm2s_tdata),
      .O_mm2s_tready(O_mm2s_tready),
      .I_mm2s_tlast(I_mm2s_tlast)
  );
endmodule
