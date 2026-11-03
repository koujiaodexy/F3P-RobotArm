`timescale 1ns/1ps
module imx415_camera(
 input wire refclk,bus_clk,rst_n,enable_i,reinit_i,
 input wire [31:0] request_i,page_i,input wire [4:0] page_word_i,
 input wire clk_hs_p,input wire [3:0] data_hs_p,data_lp_p,data_lp_n,
 output wire cam_clk,cam_rst,cam_scl,inout wire cam_sda,
 output wire [31:0] status_o,done_o,words_o,frames_o,debug_o,config_debug_o,page_ack_o,page_data_o,
 output wire video_clk_o,video_valid_o,video_user_o,video_last_o,
 output wire[39:0] video_raw_o,
 output wire [255:0] link_debug_o
);
 wire lp_clk,cfg_clk,pll_locked;
 camera_pll u_pll(.refclk(refclk),.reset(!rst_n),.clk0_out(),.clk1_out(),.clk2_out(lp_clk),.clk3_out(cfg_clk),.lock(pll_locked));
 DR1_LOGIC_ODDR u_camera_clock(.q(cam_clk),.clk(cfg_clk),.d0(1'b1),.d1(1'b0),.rst(!pll_locked));
 reg [21:0] power_count;reg re1,re2,re_seen;
 always @(posedge cfg_clk or negedge rst_n)begin
  if(!rst_n)begin power_count<=0;re1<=0;re2<=0;re_seen<=0;end
  else begin
   re1<=reinit_i;re2<=re1;re_seen<=re2;
   if(!pll_locked||(re2&&!re_seen))power_count<=0;
   else if(power_count<2400000)power_count<=power_count+1;
  end
 end
 assign cam_rst=pll_locked&&(power_count>=2400000);
 wire configured,failed;
 imx415_init u_init(.clk(cfg_clk),.rst_n(cam_rst),.scl(cam_scl),.sda(cam_sda),.configured(configured),.failed(failed),.debug(config_debug_o));
 wire pixel_clk,hs_valid;wire [31:0] hs_data;wire[3:0] lane_error;
 mipi_dphy_rx_over_lvds_wrapper #(.DEVICE("DR1"),.LANE_NUM(4)) u_rx(
  .I_lp_clk(lp_clk),.I_rst(!cam_rst),.I_mipi_clk_p(clk_hs_p),.I_mipi_data_hs_p(data_hs_p),
  .I_mipi_data_lp_p(data_lp_p),.I_mipi_data_lp_n(data_lp_n),.I_lane_hs_invert(4'b0),.I_lane_lp_invert(4'b0),
  .O_hs_rx_clk(pixel_clk),.O_hs_rx_valid(hs_valid),.O_hs_rx_data(hs_data),.O_lp_rx_lane0_p(),.O_lp_rx_lane0_n(),.O_lane_error(lane_error));
 wire csi_start,csi_end,csi_valid;wire [31:0] csi_data;
 ui_csi_unpacket_4lane u_csi(.I_clk(pixel_clk),.I_rst_n(cam_rst),.I_hs_valid(hs_valid),.I_hs_data(hs_data),
  .O_csi_frame_start(csi_start),.O_csi_frame_end(csi_end),.O_csi_valid(csi_valid),.O_csi_data(csi_data));
 wire raw_start,raw_end,raw_valid;wire[39:0] raw_data;
 ui_raw10_unpacket_4lane u_raw(.I_clk(pixel_clk),.I_rst_n(cam_rst),.I_csi_frame_start(csi_start),.I_csi_frame_end(csi_end),
  .I_csi_valid(csi_valid),.I_csi_data(csi_data),.O_raw10_frame_start(raw_start),.O_raw10_frame_end(raw_end),.O_raw10_valid(raw_valid),.O_raw10_data(raw_data));
 wire crop_valid,crop_user,crop_last;wire[39:0] crop_data;
 assign video_clk_o=pixel_clk;assign video_raw_o=crop_data;
 assign video_valid_o=crop_valid;assign video_user_o=crop_user;assign video_last_o=crop_last;
 reg[31:0] pixel_cycles,hs_words,csi_frames,csi_words,raw_words,crop_words,last_hs;
 always @(posedge pixel_clk or negedge cam_rst)begin
  if(!cam_rst)begin pixel_cycles<=0;hs_words<=0;csi_frames<=0;csi_words<=0;raw_words<=0;crop_words<=0;last_hs<=0;end
  else begin
   pixel_cycles<=pixel_cycles+1;
   if(hs_valid)begin hs_words<=hs_words+1;last_hs<=hs_data;end
   if(csi_start)csi_frames<=csi_frames+1;
   if(csi_valid)csi_words<=csi_words+1;
   if(raw_valid)raw_words<=raw_words+1;
   if(crop_valid)crop_words<=crop_words+1;
  end
 end
 wire[191:0] gray_counts={(crop_words>>1)^crop_words,(raw_words>>1)^raw_words,(csi_words>>1)^csi_words,(csi_frames>>1)^csi_frames,(hs_words>>1)^hs_words,(pixel_cycles>>1)^pixel_cycles};
 reg[191:0] link1,link2;reg[31:0] last1,last2,pins1,pins2;
 always @(posedge bus_clk or negedge rst_n)begin
  if(!rst_n)begin link1<=0;link2<=0;last1<=0;last2<=0;pins1<=0;pins2<=0;end
  else begin
   link1<=gray_counts;link2<=link1;last1<=last_hs;last2<=last1;
   pins1<={17'd0,pll_locked,failed,configured,data_lp_n,data_lp_p,clk_hs_p,cam_rst,cam_scl,cam_sda};pins2<=pins1;
  end
 end
 // Export Gray values; decode in software to keep counters off the bridge read critical path.
 assign link_debug_o[191:0]=link2;
 assign link_debug_o[223:192]=last2;assign link_debug_o[255:224]=pins2;
 ui_image_correction u_crop(.I_clk(pixel_clk),.I_rst_n(cam_rst),.I_raw_data(raw_data),.I_raw_valid(raw_valid),
  .I_raw_frame_start(raw_start),.I_raw_frame_end(raw_end),.O_raw_tdata(crop_data),.O_raw_tlast(crop_last),
  .O_raw_tdest(),.O_raw_tvalid(crop_valid),.O_raw_tuser(crop_user),.O_raw_tready(1'b1));
 wire ready,busy,error,page_busy;
 camera_frame_store u_store(.pixel_clk(pixel_clk),.bus_clk(bus_clk),.rst_n(cam_rst),.enable_i(enable_i),
  .valid_i(crop_valid),.user_i(crop_user),.last_i(crop_last),.raw_i(crop_data),.request_i(request_i),.page_i(page_i),.page_word_i(page_word_i),
  .page_data_o(page_data_o),.page_ack_o(page_ack_o),.done_o(done_o),.words_o(words_o),.frames_o(frames_o),.debug_o(debug_o),
  .ready_o(ready),.busy_o(busy),.error_o(error),.page_busy_o(page_busy));
 reg cfg1,cfg2,fail1,fail2,lock1,lock2;reg[3:0] lane1,lane2;
 always @(posedge bus_clk or negedge rst_n)begin
  if(!rst_n)begin cfg1<=0;cfg2<=0;fail1<=0;fail2<=0;lock1<=0;lock2<=0;lane1<=0;lane2<=0;end
  else begin cfg1<=configured;cfg2<=cfg1;fail1<=failed;fail2<=fail1;lock1<=pll_locked;lock2<=lock1;lane1<=lane_error;lane2<=lane1;end
 end
 assign status_o={8'd0,lane2,12'd0,lock2,1'b0,page_busy,error,ready,busy,fail2,cfg2};
endmodule
