`timescale 1ns/1ps

// Linux HDMI framebuffer + ZDT X42S runtime control top.
// The vendor system block supplies the PS, VDMA and HDMI pipeline used by the
// Ubuntu vdmafb device tree.  The original TPG writer is not instantiated, so
// it cannot overwrite Linux-owned DDR.  The PS control window is 0xA0000000.
module system_top (
    input  wire       I_can_rx,
    output wire       O_can_tx,
    output wire       O_hdmi_clk_p,
    output wire [2:0] O_hdmi_tx_p,
    output wire O_aud_mclk, O_aud_sclk, O_aud_lrck, O_aud_dsdin, O_aud_cclk,
    input wire I_aud_asdout,
    inout wire IO_aud_cdata,
    input wire I_cam_ref_clk,I_cam_clk_hs_p,
    input wire [3:0] I_cam_data_hs_p,I_cam_data_lp_p,I_cam_data_lp_n,
    output wire O_cam_clk,O_cam_rst,O_cam_scl,inout wire IO_cam_sda,
    input wire [3:0] I_car_encoder,I_car_keys_n,
    output wire O_car_pwma,O_car_pwmb,O_car_ain1,O_car_ain2,O_car_bin1,O_car_bin2,
    inout wire IO_oled_scl,IO_oled_sda,
    input wire I_jy61p_rx,output wire O_jy61p_tx,
    output wire O_gripper_pwm
);
    wire camera_pixel_clk,camera_raw_valid,camera_raw_user,camera_raw_last;
    wire[39:0] camera_raw;
    reg[1:0] video_mode_m;reg[27:0] video_watchdog;
    reg[2:0] tone_we;reg[7:0] tone_address,tone_value;
    wire[31:0] camera_hdmi_pixel,fullscreen_pixel,window_pixel,osd_read,fullscreen_osd_read,window_osd_read,window_read;wire window_ink,window_raw_pause;
    wire[23:0]preview_rgb;wire preview_valid,preview_user,preview_last;wire[31:0]preview_fid;wire[2:0] compact_bank;wire[31:0] compact_count,compact_fid;
    wire[31:0] full_raddr,win_raddr;wire[15:0] full_rsize,win_rsize;
    wire full_rreq,win_rreq,full_rbusy,win_rbusy,full_rvalid,win_rvalid,full_rready,win_rready,read_arb_error;wire camera_display_de,camera_display_vs;
    wire[31:0] dma_waddr,dma_raddr;wire[15:0] dma_wsize,dma_rsize;
    wire[31:0]compact_diagnostic;wire[15:0]hp0_diagnostic;wire[159:0]dma_diagnostic;reg[159:0]dma_diagnostic1,dma_diagnostic2;
    wire dma_wreq,dma_rreq,dma_wbusy,dma_wvalid,dma_rbusy,dma_rvalid,dma_wready,dma_rready;
    wire[63:0] dma_wdata,dma_rdata;
    wire[191:0] video_stats;reg[191:0] video_stats1,video_stats2;
    wire[2:0] video_read_health;reg[2:0] video_read_health1,video_read_health2;
    always @(posedge S_mclk or negedge S_mrstn)begin
     if(!S_mrstn)begin video_read_health1<=0;video_read_health2<=0;end
     else begin video_read_health1<=video_read_health;video_read_health2<=video_read_health1;end
    end
    wire[15:0] video_duplicates;reg[15:0] video_duplicates1,video_duplicates2;
    wire[16:0]linux_line_gray;reg[16:0]linux_line_gray1,linux_line_gray2;
    always @(posedge S_mclk or negedge S_mrstn)begin
     if(!S_mrstn)begin linux_line_gray1<=0;linux_line_gray2<=0;end
     else begin linux_line_gray1<=linux_line_gray;linux_line_gray2<=linux_line_gray1;end
    end
    wire[31:0] video_debug;reg[31:0] video_debug1,video_debug2;
    reg[31:0] isp_frame_count,isp_word_count,isp_line_count;
    reg[95:0] isp_gray,isp_gray1,isp_gray2;
    reg[31:0] dma_write_beats,dma_read_beats,dma_cycles,display_pixels;
    reg[159:0] dma_probe,dma_probe1,dma_probe2;
    reg[31:0] display_pixel_gray,display_pixel_gray1,display_pixel_gray2;
    always @(posedge S_ui_clk or negedge S_ui_rstn)begin
     if(!S_ui_rstn)begin dma_write_beats<=0;dma_read_beats<=0;dma_cycles<=0;dma_probe<=0;end
     else begin
      dma_cycles<=dma_cycles+1;
      if(raw_wvalid)dma_write_beats<=dma_write_beats+1;
      if(dma_rvalid)dma_read_beats<=dma_read_beats+1;
      dma_probe<={dma_raddr,raw_waddr,((dma_cycles>>1)^dma_cycles),((dma_read_beats>>1)^dma_read_beats),((dma_write_beats>>1)^dma_write_beats)};
     end
    end
    always @(posedge S_pclkx1 or negedge S_ui_rstn)begin
     if(!S_ui_rstn)begin display_pixels<=0;display_pixel_gray<=0;end
     else begin
      if(camera_display_de)display_pixels<=display_pixels+1;
      display_pixel_gray<=(display_pixels>>1)^display_pixels;
     end
    end
    always @(posedge S_mclk or negedge S_mrstn)begin
     if(!S_mrstn)begin dma_probe1<=0;dma_probe2<=0;display_pixel_gray1<=0;display_pixel_gray2<=0;end
     else begin dma_probe1<=dma_probe;dma_probe2<=dma_probe1;display_pixel_gray1<=display_pixel_gray;display_pixel_gray2<=display_pixel_gray1;end
    end
    always @(posedge camera_pixel_clk or negedge O_cam_rst)begin
     if(!O_cam_rst)begin isp_frame_count<=0;isp_word_count<=0;isp_line_count<=0;isp_gray<=0;end
     else begin
      if(isp_user)isp_frame_count<=isp_frame_count+1;
      if(isp_valid)isp_word_count<=isp_word_count+1;
      if(isp_last)isp_line_count<=isp_line_count+1;
      isp_gray<={((isp_line_count>>1)^isp_line_count),((isp_word_count>>1)^isp_word_count),((isp_frame_count>>1)^isp_frame_count)};
     end
    end
    wire[127:0] isp_rgb,tone_rgb;wire isp_valid,isp_user,isp_last,tone_valid,tone_user,tone_last;
    ui_top_demosaic #(.IMG_HEIGHT(1080),.IMG_WIDTH(1920),.data_complete_delay(50),.BAYER_MODE("RGGB")) u_isp(
     .I_clk(camera_pixel_clk),.I_rst_n(O_cam_rst),.I_axi4s_tdata(camera_raw),.I_axi4s_tdest(10'd0),
     .I_axi4s_tlast(camera_raw_last),.I_axi4s_tvalid(camera_raw_valid),.I_axi4s_tuser(camera_raw_user),.I_axi4s_tready(),
     .O_tlast(isp_last),.O_tuser(isp_user),.O_tvalid(isp_valid),.O_tdata(isp_rgb),.O_tready(1'b1));
    camera_video_tone u_tone(.pixel_clk(camera_pixel_clk),.rst_n(O_cam_rst),.bus_clk(S_mclk),.allow_write(!video_mode_m[0]),
     .table_we(tone_we),.table_address(tone_address),.table_data(tone_value),
     .data_i(isp_rgb),.valid_i(isp_valid),.user_i(isp_user),.last_i(isp_last),
     .data_o(tone_rgb),.valid_o(tone_valid),.user_o(tone_user),.last_o(tone_last));
    wire[31:0] raw_waddr,color_waddr;wire[15:0]raw_wsize,color_wsize;
    wire raw_wreq,raw_wbusy,raw_wvalid,raw_wready,color_wreq,color_wbusy,color_wpop,color_wready;
    wire[63:0]raw_wdata,color_wdata;wire[31:0]color_read;wire color_arb_error;
    reg[1:0]color_reset_sync;
    always @(posedge S_ui_clk or negedge S_ui_rstn)begin
     if(!S_ui_rstn)color_reset_sync<=0;else color_reset_sync<={color_reset_sync[0],1'b1};
    end
    wire color_ui_rstn=color_reset_sync[1];
    camera_color_accel u_color(.diagnostic_state(compact_diagnostic),.bus_clk(S_mclk),.bus_rst_n(S_mrstn),.bus_write(!S_mcsb&&S_mweb==4'h0),.bus_address(S_maddr),.bus_data(S_mrdata),.bus_read(color_read),.video_run(video_mode_m[0]),
      .pixel_clk(camera_pixel_clk),.pixel_rst_n(O_cam_rst),.rgb(tone_rgb),.valid(tone_valid),.user(tone_user),.last(tone_last),.source_id(isp_frame_count),
      .ui_clk(S_ui_clk),.ui_rst_n(color_ui_rstn),.waddr(color_waddr),.wsize(color_wsize),.wreq(color_wreq),.wdata(color_wdata),.wready(color_wready),.wbusy(color_wbusy),.wpop(color_wpop),.preview_completed_fid(compact_fid),.preview_bank(compact_bank),.preview_count(compact_count),.preview_rgb(preview_rgb),.preview_valid(preview_valid),.preview_user(preview_user),.preview_last(preview_last),.preview_fid(preview_fid));
    vision_write_arbiter u_camera_writer(.clk(S_ui_clk),.rst_n(color_ui_rstn),
      .a_addr(raw_waddr),.a_size(raw_wsize),.a_req(raw_wreq),.a_data(raw_wdata),.a_ready(raw_wready),.a_busy(raw_wbusy),.a_pop(raw_wvalid),
      .b_addr(color_waddr),.b_size(color_wsize),.b_req(color_wreq),.b_data(color_wdata),.b_ready(color_wready),.b_busy(color_wbusy),.b_pop(color_wpop),
      .m_addr(dma_waddr),.m_size(dma_wsize),.m_req(dma_wreq),.m_data(dma_wdata),.m_ready(dma_wready),.m_busy(dma_wbusy),.m_pop(dma_wvalid),.error(color_arb_error));
    camera_video_dma u_video(
     .bus_clk(S_mclk),.bus_rst_n(S_mrstn),.bus_write(!S_mcsb&&S_mweb==4'h0),
     .bus_address(S_maddr),.bus_data(S_mrdata),.osd_read(fullscreen_osd_read),.ui_clk(S_ui_clk),.ui_rst_n(S_ui_rstn),.run_i(video_mode_m[0]&&!window_raw_pause),.show_i(video_mode_m[1]),
     .pixel_clk(camera_pixel_clk),.display_clk(S_pclkx1),.rgb_i(tone_rgb),.valid_i(tone_valid),.user_i(tone_user),.last_i(tone_last),
     .display_de(camera_display_de),.display_vs(camera_display_vs),.video_o(fullscreen_pixel),
     .waddr(raw_waddr),.raddr(full_raddr),.wreq(raw_wreq),.rreq(full_rreq),.wsize(raw_wsize),.rsize(full_rsize),
     .wdata(raw_wdata),.wbusy(raw_wbusy),.wvalid(raw_wvalid),.rbusy(full_rbusy),.rvalid(full_rvalid),.rdata(dma_rdata),
     .wready(raw_wready),.rready(full_rready),.stats_gray(video_stats),.duplicates_gray(video_duplicates),.debug_state(video_debug),.read_health(video_read_health));
    camera_window_preview u_window(
     .bus_clk(S_mclk),.bus_rst_n(S_mrstn),.bus_write(!S_mcsb&&S_mweb==4'h0),.bus_address(S_maddr),.bus_data(S_mrdata),
     .bus_read(window_read),.osd_read(window_osd_read),.run(video_mode_m[0]&&!video_mode_m[1]),.raw_pause(window_raw_pause),
     .ui_clk(S_ui_clk),.ui_rst_n(color_ui_rstn),.compact_bank(compact_bank),.compact_count(compact_count),.compact_fid(compact_fid),
     .camera_clk(camera_pixel_clk),.camera_rst_n(O_cam_rst),.camera_rgb(preview_rgb),.camera_valid(preview_valid),.camera_user(preview_user),.camera_last(preview_last),.camera_fid(preview_fid),
     .pixel_clk(S_pclkx1),.vs(camera_display_vs),.de(camera_display_de),.pixel(window_pixel),.ink(window_ink),
     .raddr(win_raddr),.rsize(win_rsize),.rreq(win_rreq),.rbusy(win_rbusy),.rvalid(win_rvalid),.rdata(dma_rdata),.rready(win_rready));
    camera_read_arbiter u_camera_reader(.clk(S_ui_clk),.rst_n(S_ui_rstn),
     .a_addr(full_raddr),.a_size(full_rsize),.a_req(full_rreq),.a_busy(full_rbusy),.a_valid(full_rvalid),.a_ready(full_rready),
     .b_addr(win_raddr),.b_size(win_rsize),.b_req(win_rreq),.b_busy(win_rbusy),.b_valid(win_rvalid),.b_ready(win_rready),
     .m_addr(dma_raddr),.m_size(dma_rsize),.m_req(dma_rreq),.m_busy(dma_rbusy),.m_valid(dma_rvalid),.m_ready(dma_rready),.error(read_arb_error));
    camera_dma_diagnostics u_dma_diagnostics(.clk(S_ui_clk),.rst_n(color_ui_rstn),
     .compact_state(compact_diagnostic),.compact_address(color_waddr),.ps_signals(hp0_diagnostic),
     .flags({1'b0,window_raw_pause,color_arb_error,read_arb_error,dma_wbusy,dma_rbusy,dma_wreq,dma_rreq,
       color_wbusy,color_wreq,color_wready,color_wpop,win_rreq,win_rbusy,raw_wreq,raw_wbusy}),
     .compact_pop(color_wpop),.write_busy(dma_wbusy),.read_busy(dma_rbusy),.snapshot(dma_diagnostic));
    always @(posedge S_mclk or negedge S_mrstn)begin
     if(!S_mrstn)begin dma_diagnostic1<=0;dma_diagnostic2<=0;end
     else begin dma_diagnostic1<=dma_diagnostic;dma_diagnostic2<=dma_diagnostic1;end
    end
    assign camera_hdmi_pixel=window_ink?window_pixel:fullscreen_pixel;
    assign osd_read=video_mode_m[1]?fullscreen_osd_read:window_osd_read;
    always @(posedge S_mclk or negedge S_mrstn)begin
     if(!S_mrstn)begin video_stats1<=0;video_stats2<=0;video_duplicates1<=0;video_duplicates2<=0;video_debug1<=0;video_debug2<=0;isp_gray1<=0;isp_gray2<=0;end
     else begin video_stats1<=video_stats;video_stats2<=video_stats1;video_duplicates1<=video_duplicates;video_duplicates2<=video_duplicates1;video_debug1<=video_debug;video_debug2<=video_debug1;isp_gray1<=isp_gray;isp_gray2<=isp_gray1;end
    end
    wire [255:0] camera_link_debug;
    reg camera_enable_m,camera_reinit_m;reg [31:0] camera_request_m,camera_page_m;
    wire [31:0] camera_status,camera_done,camera_words,camera_frames,camera_debug,camera_config_debug,camera_page_ack,camera_page_data;
    imx415_camera u_camera(.refclk(I_cam_ref_clk),.bus_clk(S_mclk),.rst_n(S_mrstn),.enable_i(camera_enable_m),.reinit_i(camera_reinit_m),
      .request_i(camera_request_m),.page_i(camera_page_m),.page_word_i(S_maddr[4:0]),.clk_hs_p(I_cam_clk_hs_p),
      .data_hs_p(I_cam_data_hs_p),.data_lp_p(I_cam_data_lp_p),.data_lp_n(I_cam_data_lp_n),
      .cam_clk(O_cam_clk),.cam_rst(O_cam_rst),.cam_scl(O_cam_scl),.cam_sda(IO_cam_sda),
      .status_o(camera_status),.done_o(camera_done),.words_o(camera_words),.frames_o(camera_frames),.debug_o(camera_debug),
      .video_clk_o(camera_pixel_clk),.video_raw_o(camera_raw),.video_valid_o(camera_raw_valid),.video_user_o(camera_raw_user),.video_last_o(camera_raw_last),
      .link_debug_o(camera_link_debug),.config_debug_o(camera_config_debug),.page_ack_o(camera_page_ack),.page_data_o(camera_page_data));

    wire [31:0] audio_status, audio_head, audio_ack, audio_total, audio_overflows;
    reg audio_enable_m, audio_reinit_m;
    reg [3:0] audio_gain_m;
    reg [31:0] audio_pop_m;
    es8388_capture u_audio(.clk_i(S_refclk),.rst_ni(S_mrstn),.bus_clk_i(S_mclk),
      .enable_i(audio_enable_m),.reinit_i(audio_reinit_m),.gain_i(audio_gain_m),.pop_i(audio_pop_m),
      .status_o(audio_status),.head_o(audio_head),.ack_o(audio_ack),.total_o(audio_total),.overflows_o(audio_overflows),
      .mclk_o(O_aud_mclk),.bclk_o(O_aud_sclk),.lrck_o(O_aud_lrck),.dac_o(O_aud_dsdin),
      .adc_i(I_aud_asdout),.scl_o(O_aud_cclk),.sda_io(IO_aud_cdata));

    // V9 control/commit snapshots use toggle mailboxes with held payloads.
    reg [2:0] trajectory_ctl_m;
    reg trajectory_ctl_toggle_m,trajectory_commit_toggle_m,trajectory_hb_toggle_m;
    reg [31:0] trajectory_seq_m; reg trajectory_final_m;
    reg [383:0] trajectory_axes_m; reg [416:0] trajectory_commit_m;
    reg [2:0] trajectory_ctl_c1,trajectory_ctl_c2;
    reg [2:0] trajectory_ctl_sync,trajectory_commit_sync,trajectory_hb_sync;
    reg trajectory_ctl_seen,trajectory_commit_seen,trajectory_hb_seen;
    reg [416:0] trajectory_frame_c1,trajectory_frame_c2;
    wire tr_ctl_pulse=trajectory_ctl_sync[2]^trajectory_ctl_seen;
    wire tr_commit_pulse=trajectory_commit_sync[2]^trajectory_commit_seen;
    wire tr_hb_pulse=trajectory_hb_sync[2]^trajectory_hb_seen;
    wire tr_owned,tr_running,tr_draining,tr_stop_done,tr_final,tr_fault;
    wire [31:0] tr_error,tr_accepted,tr_fired,tr_now_ms;
    wire [5:0] tr_count,tr_stop_mask;
    wire tr_tx_valid,tr_tx_abort; wire [28:0] tr_tx_id;wire [3:0] tr_tx_dlc;wire [63:0] tr_tx_data;
    wire [1535:0] tr_feedback;wire tr_feedback_toggle;
    reg [1535:0] tr_feedback_m1,tr_feedback_m2,tr_feedback_m;
    reg [2:0] tr_feedback_sync;reg tr_feedback_seen;
    wire [31:0] tr_status={2'd0,((tr_running||tr_draining||tr_stop_active)?(~tr_stop_mask):6'd0),2'd0,tr_stop_mask,2'd0,tr_count,tr_stop_active,tr_final,(tr_count==32),tr_fault,tr_stop_done,tr_draining,tr_running,tr_owned};
    reg [31:0] tr_status_m1,tr_status_m2,tr_error_m1,tr_error_m2;
    reg [31:0] tr_accepted_m1,tr_accepted_m2,tr_fired_m1,tr_fired_m2;
    reg [1:0] tr_ctl_ack_m,tr_commit_ack_m;
    wire [31:0] tr_accepted_gray=tr_accepted^(tr_accepted>>1);
    wire [31:0] tr_fired_gray=tr_fired^(tr_fired>>1);
    wire [31:0] tr_now_gray=tr_now_ms^(tr_now_ms>>1);
    reg [31:0] tr_now_gray_m1,tr_now_gray_m2;
    wire tr_stop_active;
    function [31:0] gray_to_binary;
      input [31:0] value;integer k;begin gray_to_binary[31]=value[31];for(k=30;k>=0;k=k-1)gray_to_binary[k]=gray_to_binary[k+1]^value[k];end
    endfunction
    wire legacy_tx_valid,legacy_tx_extended;wire [28:0] legacy_tx_id;
    wire [3:0] legacy_tx_dlc;wire [63:0] legacy_tx_data;

    wire S_refclk;
    wire S_ui_rstn;
    wire S_ui_clk;
    wire S_mclk;
    wire S_mrstn;
    wire [7:0] S_maddr;
    wire [31:0] S_mrdata;
    reg  [31:0] S_mwdata;
    wire S_mcsb;
    wire [3:0] S_mweb;
    wire S_pclkx1;
    wire S_pclkx5;
    wire S_locked;

    reg [3:0] cmd_opcode_m;
    reg direction_m;
    reg [15:0] speed_m;
    reg [7:0] acceleration_m;
    reg [7:0] node_m, cmd_node_m;
    reg [15:0] cmd_speed_m;
    reg [7:0] cmd_acceleration_m;
    reg cmd_toggle_m;
    reg cmd_ack_m1, cmd_ack_m2;
    reg heartbeat_toggle_m;

    reg cmd_toggle_c1, cmd_toggle_c2, cmd_toggle_c3, cmd_toggle_seen;
    reg heartbeat_c1, heartbeat_c2, heartbeat_seen;
    reg [3:0] cmd_opcode_c1, cmd_opcode_c2;
    reg direction_c1, direction_c2;
    reg [15:0] speed_c1, speed_c2;
    reg [31:0] target_pulses_m, cmd_target_pulses_m;
    reg [31:0] target_pulses_c1, target_pulses_c2;
    reg [7:0] acceleration_c1, acceleration_c2;
    reg [7:0] node_c1, node_c2;
    wire cmd_pulse_c = cmd_toggle_c3 ^ cmd_toggle_seen;
    wire heartbeat_pulse_c = heartbeat_c2 ^ heartbeat_seen;

    wire frame_tx_valid;
    wire frame_tx_ready;
    wire frame_tx_extended;
    wire [28:0] frame_tx_id;
    wire [3:0] frame_tx_dlc;
    wire [63:0] frame_tx_data;
    wire frame_tx_done;
    wire frame_tx_error;
    wire frame_tx_no_ack;
    wire frame_rx_valid;
    wire frame_rx_extended;
    wire [28:0] frame_rx_id;
    wire [3:0] frame_rx_dlc;
    wire [63:0] frame_rx_data;
    wire frame_rx_crc_error;
    wire frame_rx_stuff_error;
    wire can_bus_active;

    wire [7:0] control_node;
    wire control_reply_valid;
    reg [7:0] control_node_m1, control_node_m2;
    wire control_busy;
    wire control_enabled;
    wire control_moving;
    wire control_error;
    wire control_watchdog_stop;
    wire [31:0] control_error_code;
    wire [3:0] control_state;

    reg [31:0] tx_count_c;
    reg [31:0] rx_count_c;
    reg [28:0] last_rx_id_c;
    reg last_rx_extended_c;
    reg [3:0] last_rx_dlc_c;
    reg [63:0] last_rx_data_c;
    reg [31:0] f3_rx_c;
    reg [31:0] f6_rx_c;

    reg [8:0] status_m1, status_m2;
    reg [31:0] error_code_m1, error_code_m2;
    reg [31:0] tx_count_m1, tx_count_m2;
    reg [31:0] rx_count_m1, rx_count_m2;
    reg [28:0] last_rx_id_m1, last_rx_id_m2;
    reg [4:0] last_rx_meta_m1, last_rx_meta_m2;
    reg [63:0] last_rx_data_m1, last_rx_data_m2;
    reg [31:0] f3_rx_m1, f3_rx_m2;
    reg [31:0] f6_rx_m1, f6_rx_m2;

    assign frame_tx_valid=tr_owned?tr_tx_valid:legacy_tx_valid;
    assign frame_tx_extended=tr_owned?1'b1:legacy_tx_extended;
    assign frame_tx_id=tr_owned?tr_tx_id:legacy_tx_id;
    assign frame_tx_dlc=tr_owned?tr_tx_dlc:legacy_tx_dlc;
    assign frame_tx_data=tr_owned?tr_tx_data:legacy_tx_data;
    pll U_pll (
        .refclk(S_refclk), .reset(~S_mrstn), .lock(S_locked),
        .clk0_out(S_pclkx1), .clk1_out(S_pclkx5)
    );

    always @(posedge S_refclk or negedge S_mrstn) begin
        if (!S_mrstn) begin
            cmd_toggle_c1 <= 0; cmd_toggle_c2 <= 0; cmd_toggle_c3 <= 0; cmd_toggle_seen <= 0;
            heartbeat_c1 <= 0; heartbeat_c2 <= 0; heartbeat_seen <= 0;
            cmd_opcode_c1 <= 0; cmd_opcode_c2 <= 0;
            direction_c1 <= 0; direction_c2 <= 0;
            speed_c1 <= 16'd30; speed_c2 <= 16'd30;
            acceleration_c1 <= 8'd50; acceleration_c2 <= 8'd50;
            node_c1 <= 1; node_c2 <= 1;
            target_pulses_c1 <= 0; target_pulses_c2 <= 0;
        end else begin
            cmd_toggle_c1 <= cmd_toggle_m;
            cmd_toggle_c2 <= cmd_toggle_c1;
            cmd_toggle_c3 <= cmd_toggle_c2;
            heartbeat_c1 <= heartbeat_toggle_m;
            heartbeat_c2 <= heartbeat_c1;
            cmd_opcode_c1 <= cmd_opcode_m;
            cmd_opcode_c2 <= cmd_opcode_c1;
            direction_c1 <= direction_m;
            direction_c2 <= direction_c1;
            speed_c1 <= cmd_speed_m;
            speed_c2 <= speed_c1;
            target_pulses_c1 <= cmd_target_pulses_m;
            target_pulses_c2 <= target_pulses_c1;
            acceleration_c1 <= cmd_acceleration_m;
            node_c1 <= cmd_node_m; node_c2 <= node_c1;
            acceleration_c2 <= acceleration_c1;
            if (cmd_pulse_c) cmd_toggle_seen <= cmd_toggle_c3;
            if (heartbeat_pulse_c) heartbeat_seen <= heartbeat_c2;
        end
    end

    always @(posedge S_refclk or negedge S_mrstn) begin
        if (!S_mrstn) begin
            tx_count_c <= 0; rx_count_c <= 0;
            last_rx_id_c <= 0; last_rx_extended_c <= 0;
            last_rx_dlc_c <= 0; last_rx_data_c <= 0;
            f3_rx_c <= 0; f6_rx_c <= 0;
        end else begin
            if (frame_tx_valid && frame_tx_ready)
                tx_count_c <= tx_count_c + 1'b1;
            if (control_reply_valid) begin
                rx_count_c <= rx_count_c + 1'b1;
                last_rx_id_c <= frame_rx_id;
                last_rx_extended_c <= frame_rx_extended;
                last_rx_dlc_c <= frame_rx_dlc;
                last_rx_data_c <= frame_rx_data;
                if (frame_rx_data[7:0] == 8'hF3)
                    f3_rx_c <= {frame_rx_dlc, 4'd0, frame_rx_data[23:0]};
                if (frame_rx_data[7:0] == 8'hF6)
                    f6_rx_c <= {frame_rx_dlc, 4'd0, frame_rx_data[23:0]};
            end
        end
    end

    can_classic_core #(
        .CLK_HZ(50_000_000), .CAN_BITRATE(500_000),
        .SAMPLE_NUM(3), .SAMPLE_DEN(4), .MAX_RETRIES(3)
    ) u_can (
        .clk_i(S_refclk), .rst_ni(S_mrstn),
        .can_rx_i(I_can_rx), .can_tx_o(O_can_tx),
        .tx_valid_i(frame_tx_valid), .tx_abort_i(tr_owned&&tr_tx_abort), .tx_ready_o(frame_tx_ready),
        .tx_extended_i(frame_tx_extended), .tx_id_i(frame_tx_id),
        .tx_dlc_i(frame_tx_dlc), .tx_data_i(frame_tx_data),
        .tx_done_o(frame_tx_done), .tx_error_o(frame_tx_error),
        .tx_no_ack_o(frame_tx_no_ack),
        .rx_valid_o(frame_rx_valid), .rx_extended_o(frame_rx_extended),
        .rx_id_o(frame_rx_id), .rx_dlc_o(frame_rx_dlc),
        .rx_data_o(frame_rx_data), .rx_crc_error_o(frame_rx_crc_error),
        .rx_stuff_error_o(frame_rx_stuff_error), .bus_active_o(can_bus_active)
    );

    zdt_x42s_runtime #(.CLK_HZ(50_000_000), .NODE_ID(8'd1)) u_runtime (
        .clk_i(S_refclk), .rst_ni(S_mrstn),
        .cmd_pulse_i(cmd_pulse_c && !tr_owned), .cmd_opcode_i(cmd_opcode_c2),
        .node_i(node_c2), .active_node_o(control_node), .reply_valid_o(control_reply_valid),
        .speed_rpm_i(speed_c2), .acceleration_i(acceleration_c2),
        .direction_ccw_i(direction_c2), .target_pulses_i(target_pulses_c2),
        .heartbeat_pulse_i(heartbeat_pulse_c),
        .busy_o(control_busy), .enabled_o(control_enabled),
        .moving_o(control_moving), .error_o(control_error),
        .watchdog_stop_o(control_watchdog_stop),
        .error_code_o(control_error_code), .state_o(control_state),
        .tx_valid_o(legacy_tx_valid), .tx_ready_i(frame_tx_ready && !tr_owned),
        .tx_done_i(frame_tx_done && !tr_owned), .tx_error_i(frame_tx_error && !tr_owned), .tx_extended_o(legacy_tx_extended),
        .tx_id_o(legacy_tx_id), .tx_dlc_o(legacy_tx_dlc),
        .tx_data_o(legacy_tx_data),
        .rx_valid_i(frame_rx_valid), .rx_extended_i(frame_rx_extended),
        .rx_id_i(frame_rx_id), .rx_dlc_i(frame_rx_dlc),
        .rx_data_i(frame_rx_data)
    );

    always @(posedge S_refclk or negedge S_mrstn) begin
      if(!S_mrstn)begin
        trajectory_ctl_sync<=0;trajectory_commit_sync<=0;trajectory_hb_sync<=0;
        trajectory_ctl_seen<=0;trajectory_commit_seen<=0;trajectory_hb_seen<=0;
        trajectory_ctl_c1<=0;trajectory_ctl_c2<=0;trajectory_frame_c1<=0;trajectory_frame_c2<=0;
      end else begin
        trajectory_ctl_sync<={trajectory_ctl_sync[1:0],trajectory_ctl_toggle_m};
        trajectory_commit_sync<={trajectory_commit_sync[1:0],trajectory_commit_toggle_m};
        trajectory_hb_sync<={trajectory_hb_sync[1:0],trajectory_hb_toggle_m};
        trajectory_ctl_c1<=trajectory_ctl_m;trajectory_ctl_c2<=trajectory_ctl_c1;
        trajectory_frame_c1<=trajectory_commit_m;trajectory_frame_c2<=trajectory_frame_c1;
        if(tr_ctl_pulse)trajectory_ctl_seen<=trajectory_ctl_sync[2];
        if(tr_commit_pulse)trajectory_commit_seen<=trajectory_commit_sync[2];
        if(tr_hb_pulse)trajectory_hb_seen<=trajectory_hb_sync[2];
      end
    end
    trajectory_stream u_trajectory(
      .clk_i(S_refclk),.rst_ni(S_mrstn),.legacy_idle_i(!control_busy&&!control_moving),
      .ctl_pulse_i(tr_ctl_pulse||(cmd_pulse_c&&tr_owned&&cmd_opcode_c2==4)),
      .ctl_i((cmd_pulse_c&&tr_owned&&cmd_opcode_c2==4)?3'd3:trajectory_ctl_c2),
      .commit_pulse_i(tr_commit_pulse),.frame_i(trajectory_frame_c2),.heartbeat_i(tr_hb_pulse),
      .owned_o(tr_owned),.running_o(tr_running),.draining_o(tr_draining),.stop_done_o(tr_stop_done),
      .final_sent_o(tr_final),.fault_o(tr_fault),.error_o(tr_error),.count_o(tr_count),
      .accepted_seq_o(tr_accepted),.fired_seq_o(tr_fired),.stop_mask_o(tr_stop_mask),.stopping_o(tr_stop_active),
      .tx_abort_o(tr_tx_abort),.tx_valid_o(tr_tx_valid),.tx_ready_i(frame_tx_ready&&tr_owned),
      .tx_done_i(frame_tx_done&&tr_owned),.tx_error_i(frame_tx_error&&tr_owned),
      .tx_id_o(tr_tx_id),.tx_dlc_o(tr_tx_dlc),.tx_data_o(tr_tx_data),
      .rx_valid_i(frame_rx_valid),.rx_extended_i(frame_rx_extended),.rx_id_i(frame_rx_id),
      .rx_dlc_i(frame_rx_dlc),.rx_data_i(frame_rx_data),
      .feedback_o(tr_feedback),.feedback_toggle_o(tr_feedback_toggle),.now_ms_o(tr_now_ms));
    always @(posedge S_mclk or negedge S_mrstn) begin
      if(!S_mrstn)begin
        tr_status_m1<=0;tr_status_m2<=0;tr_error_m1<=0;tr_error_m2<=0;
        tr_accepted_m1<=0;tr_accepted_m2<=0;tr_fired_m1<=0;tr_fired_m2<=0;
        tr_ctl_ack_m<=0;tr_commit_ack_m<=0;tr_now_gray_m1<=0;tr_now_gray_m2<=0;
        tr_feedback_m1<=0;tr_feedback_m2<=0;tr_feedback_m<=0;tr_feedback_sync<=0;tr_feedback_seen<=0;
      end else begin
        tr_status_m1<=tr_status;tr_status_m2<=tr_status_m1;tr_error_m1<=tr_error;tr_error_m2<=tr_error_m1;
        tr_accepted_m1<=tr_accepted_gray;tr_accepted_m2<=tr_accepted_m1;tr_fired_m1<=tr_fired_gray;tr_fired_m2<=tr_fired_m1;
        tr_ctl_ack_m<={tr_ctl_ack_m[0],trajectory_ctl_seen};tr_commit_ack_m<={tr_commit_ack_m[0],trajectory_commit_seen};
        tr_now_gray_m1<=tr_now_gray;tr_now_gray_m2<=tr_now_gray_m1;
        tr_feedback_m1<=tr_feedback;tr_feedback_m2<=tr_feedback_m1;
        tr_feedback_sync<={tr_feedback_sync[1:0],tr_feedback_toggle};
        if(tr_feedback_sync[2]!=tr_feedback_seen)begin tr_feedback_m<=tr_feedback_m2;tr_feedback_seen<=tr_feedback_sync[2];end
      end
    end
    always @(posedge S_mclk or negedge S_mrstn) begin
        if (!S_mrstn) begin
            status_m1 <= 0; status_m2 <= 0;
            control_node_m1 <= 1; control_node_m2 <= 1;
            cmd_ack_m1 <= 0; cmd_ack_m2 <= 0;
            error_code_m1 <= 0; error_code_m2 <= 0;
            tx_count_m1 <= 0; tx_count_m2 <= 0;
            rx_count_m1 <= 0; rx_count_m2 <= 0;
            last_rx_id_m1 <= 0; last_rx_id_m2 <= 0;
            last_rx_meta_m1 <= 0; last_rx_meta_m2 <= 0;
            last_rx_data_m1 <= 0; last_rx_data_m2 <= 0;
            f3_rx_m1 <= 0; f3_rx_m2 <= 0;
            f6_rx_m1 <= 0; f6_rx_m2 <= 0;
        end else begin
            control_node_m1 <= control_node; control_node_m2 <= control_node_m1;
            cmd_ack_m1 <= cmd_toggle_seen; cmd_ack_m2 <= cmd_ack_m1;
            status_m1 <= {control_state, control_watchdog_stop, control_error,
                          control_moving, control_enabled, control_busy};
            status_m2 <= status_m1;
            error_code_m1 <= control_error_code; error_code_m2 <= error_code_m1;
            tx_count_m1 <= tx_count_c; tx_count_m2 <= tx_count_m1;
            rx_count_m1 <= rx_count_c; rx_count_m2 <= rx_count_m1;
            last_rx_id_m1 <= last_rx_id_c; last_rx_id_m2 <= last_rx_id_m1;
            last_rx_meta_m1 <= {last_rx_extended_c, last_rx_dlc_c};
            last_rx_meta_m2 <= last_rx_meta_m1;
            last_rx_data_m1 <= last_rx_data_c;
            last_rx_data_m2 <= last_rx_data_m1;
            f3_rx_m1 <= f3_rx_c; f3_rx_m2 <= f3_rx_m1;
            f6_rx_m1 <= f6_rx_c; f6_rx_m2 <= f6_rx_m1;
        end
    end

    reg [31:0] read_bank0,read_bank1,read_bank2,read_bank3;
    always @* begin
      read_bank0=0;
      case(S_maddr[5:0])
        6'h00: read_bank0=32'h5241_4331;
        6'h01: read_bank0=32'h0003_000A;
        6'h02: read_bank0={16'd0, speed_m};
        6'h03: read_bank0={23'd0, direction_m, 4'd0, cmd_opcode_m};
        6'h04: read_bank0=32'd0;
        6'h05: read_bank0=tr_status_m2[0]?{23'd0,4'd0,1'b0,tr_status_m2[4],(|tr_status_m2[29:24]),status_m2[1],1'b1}:{23'd0,status_m2};
        6'h06: read_bank0=tr_status_m2[0]?tr_error_m2:error_code_m2;
        6'h07: read_bank0=tx_count_m2;
        6'h08: read_bank0=rx_count_m2;
        6'h09: read_bank0={3'd0, last_rx_id_m2};
        6'h0a: read_bank0={27'd0, last_rx_meta_m2};
        6'h0b: read_bank0=last_rx_data_m2[31:0];
        6'h0c: read_bank0=last_rx_data_m2[63:32];
        6'h0d: read_bank0=f3_rx_m2;
        6'h0e: read_bank0=f6_rx_m2;
        6'h0f: read_bank0={27'd0, frame_rx_stuff_error,
                                       frame_rx_crc_error, frame_tx_no_ack,
                                       frame_tx_done, can_bus_active};
        6'h10: read_bank0={24'd0, acceleration_m};
        6'h11: read_bank0={24'd0, node_m};
        6'h12: read_bank0={24'd0, control_node_m2};
        6'h13: read_bank0={31'd0, cmd_ack_m2};
        6'h14: read_bank0=target_pulses_m;
        6'h18: read_bank0=trajectory_ctl_m;
        6'h19: read_bank0={30'd0,trajectory_ctl_toggle_m,tr_ctl_ack_m[1]};
        6'h1a: read_bank0=tr_status_m2;
        6'h1b: read_bank0=tr_error_m2;
        6'h1c: read_bank0={30'd0,trajectory_commit_toggle_m,tr_commit_ack_m[1]};
        6'h1d: read_bank0=gray_to_binary(tr_accepted_m2);
        6'h1e: read_bank0=gray_to_binary(tr_fired_m2);
        6'h1f: read_bank0=32;
        6'h23: read_bank0=gray_to_binary(tr_now_gray_m2);
      endcase
    end
    always @* begin
      read_bank1=0;
      case(S_maddr[5:0])
        6'h00: read_bank1=tr_feedback_m[0 +:32];
        6'h01: read_bank1=tr_feedback_m[32 +:32];
        6'h02: read_bank1=tr_feedback_m[64 +:32];
        6'h03: read_bank1=tr_feedback_m[96 +:32];
        6'h04: read_bank1=tr_feedback_m[128 +:32];
        6'h05: read_bank1=tr_feedback_m[160 +:32];
        6'h06: read_bank1=tr_feedback_m[192 +:32];
        6'h07: read_bank1=tr_feedback_m[224 +:32];
        6'h08: read_bank1=tr_feedback_m[256 +:32];
        6'h09: read_bank1=tr_feedback_m[288 +:32];
        6'h0a: read_bank1=tr_feedback_m[320 +:32];
        6'h0b: read_bank1=tr_feedback_m[352 +:32];
        6'h0c: read_bank1=tr_feedback_m[384 +:32];
        6'h0d: read_bank1=tr_feedback_m[416 +:32];
        6'h0e: read_bank1=tr_feedback_m[448 +:32];
        6'h0f: read_bank1=tr_feedback_m[480 +:32];
        6'h10: read_bank1=tr_feedback_m[512 +:32];
        6'h11: read_bank1=tr_feedback_m[544 +:32];
        6'h12: read_bank1=tr_feedback_m[576 +:32];
        6'h13: read_bank1=tr_feedback_m[608 +:32];
        6'h14: read_bank1=tr_feedback_m[640 +:32];
        6'h15: read_bank1=tr_feedback_m[672 +:32];
        6'h16: read_bank1=tr_feedback_m[704 +:32];
        6'h17: read_bank1=tr_feedback_m[736 +:32];
        6'h18: read_bank1=tr_feedback_m[768 +:32];
        6'h19: read_bank1=tr_feedback_m[800 +:32];
        6'h1a: read_bank1=tr_feedback_m[832 +:32];
        6'h1b: read_bank1=tr_feedback_m[864 +:32];
        6'h1c: read_bank1=tr_feedback_m[896 +:32];
        6'h1d: read_bank1=tr_feedback_m[928 +:32];
        6'h1e: read_bank1=tr_feedback_m[960 +:32];
        6'h1f: read_bank1=tr_feedback_m[992 +:32];
        6'h20: read_bank1=tr_feedback_m[1024 +:32];
        6'h21: read_bank1=tr_feedback_m[1056 +:32];
        6'h22: read_bank1=tr_feedback_m[1088 +:32];
        6'h23: read_bank1=tr_feedback_m[1120 +:32];
        6'h24: read_bank1=tr_feedback_m[1152 +:32];
        6'h25: read_bank1=tr_feedback_m[1184 +:32];
        6'h26: read_bank1=tr_feedback_m[1216 +:32];
        6'h27: read_bank1=tr_feedback_m[1248 +:32];
        6'h28: read_bank1=tr_feedback_m[1280 +:32];
        6'h29: read_bank1=tr_feedback_m[1312 +:32];
        6'h2a: read_bank1=tr_feedback_m[1344 +:32];
        6'h2b: read_bank1=tr_feedback_m[1376 +:32];
        6'h2c: read_bank1=tr_feedback_m[1408 +:32];
        6'h2d: read_bank1=tr_feedback_m[1440 +:32];
        6'h2e: read_bank1=tr_feedback_m[1472 +:32];
        6'h2f: read_bank1=tr_feedback_m[1504 +:32];
        6'h30: read_bank1=osd_read;
        6'h31: read_bank1=osd_read;
        6'h32: read_bank1=osd_read;
        6'h33: read_bank1=osd_read;
        6'h34: read_bank1=osd_read;
        6'h35: read_bank1=osd_read;
        6'h36: read_bank1=osd_read;
        6'h37: read_bank1=osd_read;
        6'h3f: read_bank1=window_read;
        6'h3e: read_bank1=window_read;
        6'h3d: read_bank1=window_read;
        6'h3c: read_bank1=window_read;
        6'h3b: read_bank1=window_read;
        6'h3a: read_bank1=window_read;
        6'h39: read_bank1=window_read;
        6'h38: read_bank1=window_read;
      endcase
    end
    always @* begin
      read_bank2=0;
      case(S_maddr[5:0])
        6'h00: read_bank2=32'h4155_4431;
        6'h01: read_bank2={31'd0,audio_enable_m};
        6'h02: read_bank2=audio_status;
        6'h03: read_bank2={28'd0,audio_gain_m};
        6'h04: read_bank2=audio_head;
        6'h06: read_bank2=audio_ack;
        6'h07: read_bank2=32'd50000000;
        6'h08: read_bank2=32'd3072;
        6'h09: read_bank2=audio_total;
        6'h0a: read_bank2=audio_overflows;
        6'h0b: read_bank2=32'h00010000;
      endcase
    end
    always @* begin
      read_bank3=0;
      case(S_maddr[5:0])
        6'h00: read_bank3=32'h43414d31;
        6'h01: read_bank3={30'd0,camera_reinit_m,camera_enable_m};
        6'h02: read_bank3=camera_request_m;
        6'h03: read_bank3=camera_status;
        6'h04: read_bank3=camera_done;
        6'h05: read_bank3=camera_words;
        6'h06: read_bank3=camera_frames;
        6'h07: read_bank3=camera_debug;
        6'h08: read_bank3=camera_page_m;
        6'h09: read_bank3=camera_page_ack;
        6'h0a: read_bank3=camera_config_debug;
        6'h0b: read_bank3=32'h00010000;
        6'h0c: read_bank3=640;
        6'h0d: read_bank3=360;
        6'h0e: read_bank3=32'h52474742;
        6'h0f: read_bank3={video_duplicates2,14'd0,video_mode_m};
        6'h10: read_bank3=video_mode_m[0]?video_debug2:camera_page_data;
        6'h11: read_bank3=video_mode_m[0]?isp_gray2[0+:32]:camera_page_data;
        6'h12: read_bank3=video_mode_m[0]?isp_gray2[32+:32]:camera_page_data;
        6'h13: read_bank3=video_mode_m[0]?isp_gray2[64+:32]:camera_page_data;
        6'h14: read_bank3=video_mode_m[0]?dma_probe2[0+:32]:camera_page_data;
        6'h15: read_bank3=video_mode_m[0]?dma_probe2[32+:32]:camera_page_data;
        6'h16: read_bank3=video_mode_m[0]?dma_probe2[64+:32]:camera_page_data;
        6'h17: read_bank3=video_mode_m[0]?dma_probe2[96+:32]:camera_page_data;
        6'h18: read_bank3=video_mode_m[0]?dma_probe2[128+:32]:camera_page_data;
        6'h19: read_bank3=video_mode_m[0]?display_pixel_gray2:camera_page_data;
        6'h1b: read_bank3=dma_diagnostic2[0+:32];
        6'h1c: read_bank3=dma_diagnostic2[32+:32];
        6'h1d: read_bank3=dma_diagnostic2[64+:32];
        6'h1e: read_bank3=dma_diagnostic2[96+:32];
        6'h1f: read_bank3=dma_diagnostic2[128+:32];
        6'h1a: read_bank3=video_mode_m[0]?{16'h5253,13'd0,video_read_health2}:camera_page_data;
        6'h30: read_bank3=camera_link_debug[0+:32];
        6'h31: read_bank3=camera_link_debug[32+:32];
        6'h32: read_bank3=camera_link_debug[64+:32];
        6'h33: read_bank3=camera_link_debug[96+:32];
        6'h34: read_bank3=camera_link_debug[128+:32];
        6'h35: read_bank3=camera_link_debug[160+:32];
        6'h36: read_bank3=camera_link_debug[192+:32];
        6'h37: read_bank3={linux_line_gray2,camera_link_debug[238:224]};
        6'h38: read_bank3=32'h56494431;
        6'h39: read_bank3=video_stats2[0+:32];
        6'h3a: read_bank3=video_stats2[32+:32];
        6'h3b: read_bank3=video_stats2[64+:32];
        6'h3c: read_bank3=video_stats2[96+:32];
        6'h3d: read_bank3=video_stats2[128+:32];
        6'h3e: read_bank3=video_stats2[160+:32];
        6'h3f: read_bank3=32'h4c4e4b31;
        default: if(S_maddr[5:0]>=6'h10&&S_maddr[5:0]<=6'h2f)read_bank3=(video_mode_m[0]&&S_maddr[5])?(color_read|((S_maddr[3:0]==5)?{color_arb_error,31'd0}:32'd0)):camera_page_data;
      endcase
    end

    // The AXI ERAM bridge emits word addresses (byte offset 0x04 -> address 1).
    always @(posedge S_mclk or negedge S_mrstn) begin
        if (!S_mrstn) begin
            cmd_opcode_m <= 0; direction_m <= 0; speed_m <= 16'd30;
            acceleration_m <= 8'd50;
            node_m <= 1; cmd_node_m <= 1;
            cmd_speed_m <= 30; cmd_acceleration_m <= 50;
            target_pulses_m <= 0; cmd_target_pulses_m <= 0;
            cmd_toggle_m <= 0; heartbeat_toggle_m <= 0; S_mwdata <= 0;
            camera_enable_m<=0;camera_reinit_m<=0;camera_request_m<=0;camera_page_m<=0;
            video_mode_m<=0;video_watchdog<=0;tone_we<=0;tone_address<=0;tone_value<=0;
            audio_enable_m<=0;audio_reinit_m<=0;audio_gain_m<=6;audio_pop_m<=0;
            trajectory_ctl_m<=0;trajectory_ctl_toggle_m<=0;trajectory_commit_toggle_m<=0;trajectory_hb_toggle_m<=0;
            trajectory_seq_m<=0;trajectory_final_m<=0;trajectory_axes_m<=0;trajectory_commit_m<=0;
        end else begin
            tone_we<=0;
            if(video_mode_m[0])begin
             if(video_watchdog>=200000000)video_mode_m<=0;
             else video_watchdog<=video_watchdog+1;
            end else video_watchdog<=0;
            if (!S_mcsb && (S_mweb == 4'h0)) begin
                case (S_maddr)
                    8'hcf: if(S_mrdata[31:16]==16'h5644)begin video_mode_m<=S_mrdata[1:0];video_watchdog<=0;end
                    8'hf8: if(!video_mode_m[0]&&S_mrdata[17:16]<3)begin
                     tone_we<=3'b001<<S_mrdata[17:16];tone_address<=S_mrdata[15:8];tone_value<=S_mrdata[7:0];end
                    8'hc1: begin camera_enable_m<=S_mrdata[0];camera_reinit_m<=S_mrdata[1];end
                    8'hc2: camera_request_m<=S_mrdata;
                    8'hc8: camera_page_m<=S_mrdata;
                    8'h81: begin audio_enable_m<=S_mrdata[0];audio_reinit_m<=S_mrdata[1];end
                    8'h83: if(S_mrdata<=8)audio_gain_m<=S_mrdata[3:0];
                    8'h85: audio_pop_m<=S_mrdata;
                    8'h02: speed_m <= S_mrdata[15:0];
                    8'h03: if (cmd_ack_m2 == cmd_toggle_m) begin
                        cmd_node_m <= node_m;
                        cmd_speed_m <= speed_m;
                        cmd_target_pulses_m <= target_pulses_m;
                        cmd_acceleration_m <= acceleration_m;
                        cmd_opcode_m <= S_mrdata[3:0];
                        direction_m <= S_mrdata[8];
                        cmd_toggle_m <= ~cmd_toggle_m;
                    end
                    8'h04: heartbeat_toggle_m <= ~heartbeat_toggle_m;
                    8'h10: acceleration_m <= S_mrdata[7:0];
                    8'h11: node_m <= S_mrdata[7:0];
                    8'h14: target_pulses_m <= S_mrdata;
                    8'h18: if(tr_ctl_ack_m[1]==trajectory_ctl_toggle_m)begin trajectory_ctl_m<=S_mrdata[2:0];trajectory_ctl_toggle_m<=~trajectory_ctl_toggle_m;end
                    8'h20: trajectory_seq_m<=S_mrdata;
                    8'h21: trajectory_final_m<=S_mrdata[0];
                    8'h22: if(tr_commit_ack_m[1]==trajectory_commit_toggle_m)begin
                        trajectory_commit_m<={trajectory_final_m,trajectory_seq_m,trajectory_axes_m};trajectory_commit_toggle_m<=~trajectory_commit_toggle_m;end
                    8'h24: trajectory_hb_toggle_m<=~trajectory_hb_toggle_m;
                    default: if(S_maddr>=8'h28&&S_maddr<=8'h33)trajectory_axes_m[(S_maddr-8'h28)*32 +:32]<=S_mrdata;
                endcase
            end
            if (!S_mcsb && (S_mweb == 4'hF)) begin
                if(S_maddr==8'hb9) S_mwdata<=32'h5054503c; // PTP 60 deg/s capability.
                else if(S_maddr>=8'hb0 && S_maddr<=8'hb7) S_mwdata<=gripper_read;
                else if(S_maddr>=8'ha8 && S_maddr<=8'haf) S_mwdata<=jy61p_read;
                else if(S_maddr>=8'ha2 && S_maddr<=8'ha7) S_mwdata<=oled_read;
                else if((S_maddr>=8'h90 && S_maddr<=8'haf)||S_maddr==8'hb8) S_mwdata<=car_read;
                else case (S_maddr[7:6])
                  0:S_mwdata<=read_bank0;
                  1:S_mwdata<=read_bank1;
                  2:S_mwdata<=read_bank2;
                  3:S_mwdata<=read_bank3;
                endcase
            end
        end
    end

    // Added peripheral blocks: original register reads preserved outside 0x90..b7.
    wire [31:0] car_read,oled_read,jy61p_read,gripper_read;
    car_io I_car_io (
      .clk(S_mclk),.rst_n(S_mrstn),.wr(!S_mcsb && S_mweb==4'h0),
      .addr(S_maddr),.wdata(S_mrdata),.rdata(car_read),
      .encoder(I_car_encoder),.keys_n(I_car_keys_n),
      .pwma(O_car_pwma),.pwmb(O_car_pwmb),
      .ain1(O_car_ain1),.ain2(O_car_ain2),.bin1(O_car_bin1),.bin2(O_car_bin2)
    );
    oled_i2c I_oled_i2c (
      .clk(S_mclk),.rst_n(S_mrstn),.wr(!S_mcsb && S_mweb==4'h0),
      .addr(S_maddr),.wdata(S_mrdata),.rdata(oled_read),
      .scl(IO_oled_scl),.sda(IO_oled_sda)
    );
    jy61p_uart I_jy61p_uart (
      .clk(S_mclk),.rst_n(S_mrstn),.wr(!S_mcsb && S_mweb==4'h0),
      .addr(S_maddr),.wdata(S_mrdata),.rdata(jy61p_read),
      .rx(I_jy61p_rx),.tx(O_jy61p_tx)
    );
    gripper_pwm I_gripper_pwm (
      .clk(S_mclk),.rst_n(S_mrstn),.wr(!S_mcsb && S_mweb==4'h0),
      .addr(S_maddr),.wdata(S_mrdata),.rdata(gripper_read),.pwm(O_gripper_pwm)
    );

    system I_system (
        .O_dma_debug(hp0_diagnostic),
        .O_ui_clk(S_ui_clk), .O_ui_rstn(S_ui_rstn), .O_refclk(S_refclk),
        .I_pixel_clk(S_pclkx1), .I_serial_clk(S_pclkx5),
        .O_hdmi_clk_p(O_hdmi_clk_p), .O_hdmi_tx_p(O_hdmi_tx_p),
        .O_mclk(S_mclk), .O_mrstn(S_mrstn), .O_maddr(S_maddr),
        .O_mweb(S_mweb), .O_mcsb(S_mcsb), .O_mrdata(S_mrdata),
        .I_mwdata(S_mwdata), .I_irq2(1'b0),
        .I_cam_window_ink(window_ink),.I_cam_display(video_mode_m[1]),.I_cam_pixel(camera_hdmi_pixel),.O_camera_de(camera_display_de),.O_camera_vs(camera_display_vs),.O_linux_line_gray(linux_line_gray),
        .I_fdma_waddr(dma_waddr),.I_fdma_wareq(dma_wreq),.I_fdma_wsize(dma_wsize),
        .O_fdma_wbusy(dma_wbusy),.I_fdma_wdata(dma_wdata),.O_fdma_wvalid(dma_wvalid),.I_fdma_wready(dma_wready),
        .I_fdma_raddr(dma_raddr),.I_fdma_rareq(dma_rreq),.I_fdma_rsize(dma_rsize),.O_fdma_rbusy(dma_rbusy),
        .O_fdma_rdata(dma_rdata),.O_fdma_rvalid(dma_rvalid),.I_fdma_rready(dma_rready)
    );
endmodule
