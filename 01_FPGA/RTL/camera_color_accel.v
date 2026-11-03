`timescale 1ns/1ps
// Camera-only capability/config aperture; arm/CAN/audio registers are separate.
module camera_color_accel(
 input wire bus_clk,bus_rst_n,bus_write,input wire[7:0]bus_address,input wire[31:0]bus_data,
 output reg[31:0]bus_read,input wire video_run,
 input wire pixel_clk,pixel_rst_n,input wire[127:0]rgb,input wire valid,user,last,input wire[31:0]source_id,
 input wire ui_clk,ui_rst_n,
 output wire[31:0]waddr,output wire[15:0]wsize,output wire wreq,
 output wire[31:0]diagnostic_state,output wire[63:0]wdata,output wire wready,input wire wbusy,wpop,output wire[2:0]preview_bank,output wire[31:0]preview_completed_fid,output wire[31:0]preview_count,output wire[23:0]preview_rgb,output wire preview_valid,preview_user,preview_last,output wire[31:0]preview_fid
);
 reg enabled,pattern;reg[9:0]x0,y0,x1,y1;reg[7:0]smin,vmin;reg[31:0]epoch;
 reg lut_we;reg[7:0]lut_index;reg[3:0]lut_data;
 wire run=enabled&&video_run;
 wire dma_active;reg active1,active2;
 wire allow_config=!enabled&&!active2;
 always @(posedge bus_clk or negedge bus_rst_n)begin
  if(!bus_rst_n)begin enabled<=0;pattern<=0;x0<=0;y0<=0;x1<=480;y1<=270;smin<=70;vmin<=45;epoch<=0;lut_we<=0;lut_index<=0;lut_data<=0;active1<=0;active2<=0;end
  else begin
   active1<=dma_active;active2<=active1;lut_we<=0;
   if(bus_write)case(bus_address)
    8'he1:if(bus_data[31:16]==16'h434c)begin
     enabled<=bus_data[0];if(!enabled&&!active2)pattern<=bus_data[1];
    end
    8'he7:if(allow_config&&bus_data[15:0]<bus_data[31:16]&&bus_data[31:16]<=480)begin x0<=bus_data[9:0];x1<=bus_data[25:16];end
    8'he8:if(allow_config&&bus_data[15:0]<bus_data[31:16]&&bus_data[31:16]<=270)begin y0<=bus_data[9:0];y1<=bus_data[25:16];end
    8'he9:if(allow_config)begin smin<=bus_data[7:0];vmin<=bus_data[15:8];end
    8'hea:if(allow_config&&bus_data[31:16]==16'h4c55&&bus_data[15:8]<180)begin lut_we<=1;lut_index<=bus_data[15:8];lut_data<=bus_data[3:0];end
    8'heb:if(allow_config)epoch<=bus_data;
   endcase
  end
 end
 reg run1,run2;
 always @(posedge pixel_clk or negedge pixel_rst_n)begin if(!pixel_rst_n)begin run1<=0;run2<=0;end else begin run1<=run;run2<=run1;end end
 wire prst=pixel_rst_n&&run2;
 wire[23:0]sample;wire sv,su,sl,se;wire[31:0]fid;
 vision_sampler sampler(.clk(pixel_clk),.rst_n(prst),.pattern(pattern),.data_i(rgb),.valid_i(valid),.user_i(user),.last_i(last),.source_id(source_id),.data_o(sample),.valid_o(sv),.user_o(su),.last_o(sl),.frame_id(fid),.error(se));
 assign preview_rgb=sample;assign preview_valid=sv;assign preview_user=su;assign preview_last=sl;assign preview_fid=fid;
 wire[63:0]feature;wire fv,fu,fl,fe;
 vision_preprocess processor(.clk(pixel_clk),.rst_n(prst),.bus_clk(bus_clk),.cfg_allow(allow_config),.cfg_we(lut_we),.cfg_address(lut_index),.cfg_data(lut_data),.saturation_min(smin),.value_min(vmin),.roi_x0(x0),.roi_y0(y0),.roi_x1(x1),.roi_y1(y1),.data_i(sample),.valid_i(sv),.user_i(su),.last_i(sl),.data_o(feature),.valid_o(fv),.user_o(fu),.last_o(fl),.error_o(fe));
 wire[63:0]packed_word;wire pv,pe;
 vision_pack packer(.clk(pixel_clk),.rst_n(prst),.data_i(feature),.valid_i(fv),.user_i(fu),.last_i(fl),.source_frame_id(fid),.config_epoch(epoch),.flags({31'd0,pattern}),.roi_x0(x0),.roi_y0(y0),.roi_x1(x1),.roi_y1(y1),.word_o(packed_word),.valid_o(pv),.error_o(pe));
 wire[31:0]completed,completed_id,dma_errors;wire[2:0]completed_bank;
 camera_compact_dma writer(.ui_clk(ui_clk),.ui_rst_n(ui_rst_n),.enable(run),.pixel_clk(pixel_clk),.pixel_rst_n(pixel_rst_n),.word_i(packed_word),.valid_i(pv),.waddr(waddr),.wsize(wsize),.wreq(wreq),.wdata(wdata),.wready(wready),.wbusy(wbusy),.wpop(wpop),.completed(completed),.completed_id(completed_id),.completed_bank(completed_bank),.errors(dma_errors),.active(dma_active),.diagnostic_state(diagnostic_state));
 assign preview_completed_fid=completed_id;assign preview_bank=completed_bank;assign preview_count=completed;
 reg[31:0]count_gray,id_gray;
 always @(posedge ui_clk or negedge ui_rst_n)begin
  if(!ui_rst_n)begin count_gray<=0;id_gray<=0;end else begin count_gray<=(completed>>1)^completed;id_gray<=(completed_id>>1)^completed_id;end
 end
 reg[31:0]cg1,cg2,ig1,ig2,er1,er2;reg[2:0]bk1,bk2;reg[2:0]pe1,pe2;
 function[31:0]binary;input[31:0]g;integer k;begin binary[31]=g[31];for(k=30;k>=0;k=k-1)binary[k]=binary[k+1]^g[k];end endfunction
 always @(posedge bus_clk or negedge bus_rst_n)begin
  if(!bus_rst_n)begin cg1<=0;cg2<=0;ig1<=0;ig2<=0;er1<=0;er2<=0;bk1<=0;bk2<=0;pe1<=0;pe2<=0;end
  else begin cg1<=count_gray;cg2<=cg1;ig1<=id_gray;ig2<=ig1;er1<=dma_errors;er2<=er1;bk1<=completed_bank;bk2<=bk1;pe1<={se,fe,pe};pe2<=pe1;end
 end
 always @*begin
  case(bus_address[3:0])
   0:bus_read=32'h434c5231;
   1:bus_read={30'd0,pattern,enabled};
   2:bus_read=binary(ig2);
   3:bus_read=binary(cg2);
   4:bus_read={23'd0,pe2,2'd0,active2,bk2};
   5:bus_read=er2|{26'd0,pe2,3'd0};
   6:bus_read=32'h3d800000;
   7:bus_read={{6'd0,x1},{6'd0,x0}};
   8:bus_read={{6'd0,y1},{6'd0,y0}};
   9:bus_read={16'd0,vmin,smin};
   10:bus_read=0;
   11:bus_read=epoch;
   12:bus_read=32'h00060001; // six slots, format version 1
   13:bus_read=32'h48533136;
   14:bus_read=32'd105306;
   15:bus_read={16'd270,16'd480};
  endcase
 end
endmodule
