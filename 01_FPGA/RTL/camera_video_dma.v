`timescale 1ns/1ps
// Only the DT-reserved 32MiB camera region can be addressed. Reset disables DMA.
module camera_video_dma(
 input wire bus_clk,bus_rst_n,bus_write,input wire[7:0]bus_address,input wire[31:0]bus_data,
 output wire[31:0]osd_read,
 input wire ui_clk,ui_rst_n,run_i,show_i,pixel_clk,display_clk,
 input wire [127:0] rgb_i,input wire valid_i,user_i,last_i,
 input wire display_de,display_vs,
 output wire [31:0] video_o,
 output wire [31:0] waddr,raddr,output wire wreq,rreq,
 output wire [15:0] wsize,rsize,output wire [63:0] wdata,
 input wire wbusy,wvalid,rbusy,rvalid,input wire [63:0] rdata,
 output wire wready,rready,output wire [191:0] stats_gray,output wire[15:0] duplicates_gray,output wire[31:0] debug_state,
 output wire[2:0] read_health
);
 localparam [31:0] BASE=32'h3c000000,END=32'h3d800000;
 // FDMA produces already-accepted beats (the consumer is always ready).
 // Register the response once before the distributed dual-clock FIFO RAM.
 reg response_valid;reg[63:0]response_data;
 always @(posedge ui_clk or negedge ui_rst_n)begin
  if(!ui_rst_n)begin response_valid<=0;response_data<=0;end
  else begin response_valid<=rvalid;if(rvalid)response_data<=rdata;end
 end
 reg run1,run2,show1,show2;reg sh1,sh2;
 always @(posedge ui_clk or negedge ui_rst_n)begin
  if(!ui_rst_n)begin run1<=0;run2<=0;show1<=0;show2<=0;end
  else begin run1<=run_i;run2<=run1;show1<=show_i;show2<=show1;end
 end
 // Stop issuing new requests, but drain accepted AXI bursts before resetting FIFOs.
 reg drain_active;
 always @(posedge ui_clk or negedge ui_rst_n)begin
  if(!ui_rst_n)drain_active<=0;
  else if(run2)drain_active<=1;
  else if(!wbusy&&!rbusy&&!response_valid&&!rvalid)drain_active<=0;
 end
 wire active_rst=ui_rst_n&&(run2||drain_active);
 wire [31:0] wa,ra;wire wr,rr;wire [15:0] ws,rs;
 wire [7:0] next_wbuf,completed_wbuf;
 wire wirq,rirq,read_valid,read_reset,input_full,read_full,read_user,read_last;wire[31:0] read_pixel;
 camera_dbuf #(.AXI_DATA_WIDTH(64),.AXI_ADDR_WIDTH(32),.ENABLE_VSYNC(1),
  .W_BUFDEPTH(1024),.W_DATAWIDTH(128),.W_BASEADDR(BASE),.W_DSIZEBITS(23),
  .W_XSIZE(480),.W_XSTRIDE(480),.W_YSIZE(1080),.W_XDIV(2),.W_BUFSIZE(3),
  .R_BUFDEPTH(4096),.R_DATAWIDTH(32),.R_BASEADDR(BASE),.R_DSIZEBITS(23),
  .R_XSIZE(1920),.R_XSTRIDE(1920),.R_YSIZE(1080),.R_XDIV(1),.R_BUFSIZE(3)) u_buffer(
  .O_input_full(input_full),.O_read_full(read_full),.O_debug_state(debug_state),.I_ui_clk(ui_clk),.I_ui_rstn(active_rst),
  .I_W_en(run2),.I_W_wclk(pixel_clk),.I_W_tuser(user_i),.I_W_tvalid(valid_i),
  .I_W_tdata(rgb_i),.I_W_tlast(last_i),.O_W_tready(),.O_W_sync_cnt(next_wbuf),.I_W_buf(next_wbuf),
  .I_R_en(display_vs&&sh2),.I_Rsync_en(1'b1),.I_R_rclk(display_clk),.I_R_tready(display_de),
  .O_R_tuser(read_user),.O_R_tvalid(read_valid),.O_R_tdata(read_pixel),.O_R_tlast(read_last),.O_R_sync_cnt(),
  .I_R_buf(completed_wbuf),.O_R_vrst(read_reset),
  .O_fdma_waddr(wa),.O_fdma_wareq(wr),.O_fdma_wsize(ws),.I_fdma_wbusy(wbusy),
  .O_fdma_wdata(wdata),.I_fdma_wvalid(wvalid),.O_fdma_wready(wready),.O_fdma_wbuf(completed_wbuf),.O_fdma_wirq(wirq),
  .O_fdma_raddr(ra),.O_fdma_rareq(rr),.O_fdma_rsize(rs),.I_fdma_rbusy(rbusy),
  .I_fdma_rdata(response_data),.I_fdma_rvalid(response_valid),.O_fdma_rready(rready),.O_fdma_rbuf(),.O_fdma_rirq(rirq));
 wire [32:0] write_end={1'b0,wa}+{14'd0,ws,3'd0};
 wire [32:0] read_end={1'b0,ra}+{14'd0,rs,3'd0};
 wire write_ok=wa>=BASE&&write_end<={1'b0,END}&&ws!=0&&wa[2:0]==0;
 wire read_ok=ra>=BASE&&read_end<={1'b0,END}&&rs!=0&&ra[2:0]==0;
 assign waddr=wa;assign raddr=ra;assign wsize=ws;assign rsize=rs;
 assign wreq=run2&&wr&&write_ok;assign rreq=run2&&rr&&read_ok;
 reg guard_event;
 reg [31:0] writes,reads,guard_errors;reg prev_wirq,prev_rirq;
 always @(posedge ui_clk or negedge ui_rst_n)begin
  if(!ui_rst_n)begin guard_event<=0;writes<=0;reads<=0;guard_errors<=0;prev_wirq<=0;prev_rirq<=0;end
  else begin
   guard_event<=run2&&((wr&&!write_ok)||(rr&&!read_ok));
   prev_wirq<=wirq;prev_rirq<=rirq;
   if(wirq&&!prev_wirq)writes<=writes+1;
   if(rirq&&!prev_rirq)reads<=reads+1;
   if(guard_event)guard_errors<=guard_errors+1;
  end
 end
 reg [31:0] underflows,overflows,display_frames;
 reg[15:0] duplicates;reg[7:0] previous_frame_id;reg waiting_first,have_previous,vs_previous;
 always @(posedge display_clk or negedge ui_rst_n)begin
  if(!ui_rst_n)begin
   sh1<=0;sh2<=0;underflows<=0;display_frames<=0;duplicates<=0;previous_frame_id<=0;waiting_first<=0;have_previous<=0;vs_previous<=0;
  end else begin
   sh1<=show_i;sh2<=sh1;vs_previous<=display_vs;
   if(sh2&&display_de&&!read_valid)underflows<=underflows+1;
   if(!sh2)begin waiting_first<=0;have_previous<=0;end
   else begin
    if(display_vs&&!vs_previous)waiting_first<=1;
    if(waiting_first&&display_de&&read_valid)begin
     waiting_first<=0;
     if(have_previous&&read_pixel[31:24]==previous_frame_id)duplicates<=duplicates+1;
     previous_frame_id<=read_pixel[31:24];have_previous<=1;
    end
   end
   if(display_vs&&!vs_previous)display_frames<=display_frames+1;
  end
 end
 always @(posedge pixel_clk or negedge ui_rst_n)begin
  if(!ui_rst_n)overflows<=0;
  else if(valid_i&&input_full)overflows<=overflows+1;
 end
 // A small visible back arrow matches the host application's touch target.
 reg [11:0] x,y;reg previous_de,previous_vs,frame_start;
 always @(posedge display_clk or negedge ui_rst_n)begin
  if(!ui_rst_n)begin x<=0;y<=0;previous_de<=0;previous_vs<=0;frame_start<=0;end
  else begin
   previous_de<=display_de;previous_vs<=display_vs;frame_start<=display_vs&&!previous_vs;
   if(frame_start)begin x<=0;y<=0;end
   else if(display_de)x<=x+1;
   else begin x<=0;if(previous_de)y<=y+1;end
  end
 end
 wire box_ink;wire[23:0]box_rgb;
 // Sticky diagnostics verify pixel boundaries, rather than inferring image
 // integrity from scanout FPS. Flags clear when capture/preview is stopped.
 reg read_overflow,raster_fault,frame_id_fault;
 reg [7:0] raster_frame_id;
 always @(posedge ui_clk or negedge active_rst)begin
  if(!active_rst)read_overflow<=0;
  else if(response_valid&&read_full)read_overflow<=1;
 end
 always @(posedge display_clk or negedge ui_rst_n)begin
  if(!ui_rst_n)begin raster_fault<=0;frame_id_fault<=0;raster_frame_id<=0;end
  else if(!sh2)begin raster_fault<=0;frame_id_fault<=0;raster_frame_id<=0;end
  else if(display_de&&read_valid)begin
   if(read_user!=(x==0&&y==0) || read_last!=(x==1919))raster_fault<=1;
   if(x==0&&y==0)raster_frame_id<=read_pixel[31:24];
   else if(read_pixel[31:24]!=raster_frame_id)frame_id_fault<=1;
  end
 end
 assign read_health={frame_id_fault,raster_fault,read_overflow};
 // Both mailbox domains use the same global reset assertion. Do not reset
 // the display handshake independently while a bus transaction is pending.
 vision_result_osd u_result_osd(
  .bus_clk(bus_clk),.bus_rst_n(bus_rst_n),.bus_write(bus_write),
  .bus_address(bus_address),.bus_data(bus_data),.bus_read(osd_read),
  .display_clk(display_clk),.display_rst_n(bus_rst_n),.enable(sh2),
  .vs(display_vs),.de(display_de&&read_valid),.x(x),.y(y),.ink(box_ink),.rgb(box_rgb));
 wire[6:0]arrow_sum={1'b0,x[5:0]}+{1'b0,y[5:0]};
 wire[6:0]arrow_slope={1'b0,x[5:0]}+7'd14;
 wire arrow=x>=16&&x<62&&y>=14&&y<42&&((x<32&&((y>=28&&arrow_sum<7'd61)||(y<28&&arrow_slope>{1'b0,y[5:0]})))||(y>=25&&y<31));
 wire osd_panel,osd_ink;
 wire new_unique_frame=sh2&&waiting_first&&display_de&&read_valid&&(!have_previous||read_pixel[31:24]!=previous_frame_id);
 camera_video_osd u_osd(.clk(display_clk),.rst_n(ui_rst_n),.enable(sh2),
  .new_frame(new_unique_frame),.x(x),.y(y),.panel(osd_panel),.ink(osd_ink));
 assign video_o=(x<80&&y<56)?(arrow?32'h00ffffff:32'h00132030):
  osd_panel?(osd_ink?32'h00ffffff:32'h00132030):(read_valid?(box_ink?{8'd0,box_rgb}:read_pixel):32'd0);
 reg[63:0] ui_gray;reg[95:0] display_gray;reg[31:0] overflow_gray;reg[15:0] duplicate_gray;
 always @(posedge ui_clk)ui_gray<={((guard_errors>>1)^guard_errors),((writes>>1)^writes)};
 always @(posedge display_clk)begin
  display_gray<={((display_frames>>1)^display_frames),((underflows>>1)^underflows),((duplicates>>1)^duplicates),16'd0};
  duplicate_gray<=(duplicates>>1)^duplicates;
 end
 always @(posedge pixel_clk)overflow_gray<=(overflows>>1)^overflows;
 reg[31:0] read_gray;always @(posedge ui_clk)read_gray<=(reads>>1)^reads;
 assign stats_gray={display_gray[95:64],overflow_gray,ui_gray[63:32],display_gray[63:32],read_gray,ui_gray[31:0]};
 assign duplicates_gray=duplicate_gray;
endmodule

// Real unique source frames per one second of the 148.5MHz display clock.
// Text is generated in PL; Linux scanout remains halted during full-screen video.
module camera_video_osd #(parameter PIXEL_HZ=148500000)(
 input wire clk,rst_n,enable,new_frame,input wire[11:0]x,y,
 output wire panel,ink
);
 reg[27:0] second_ticks;
 reg[7:0] frame_count,fps;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin second_ticks<=0;frame_count<=0;fps<=0;end
  else if(!enable)begin second_ticks<=0;frame_count<=0;fps<=0;end
  else if(second_ticks==PIXEL_HZ-1)begin
   second_ticks<=0;frame_count<=0;
   fps<=(frame_count+new_frame>99)?8'd99:frame_count+new_frame;
  end else begin
   second_ticks<=second_ticks+1;
   if(new_frame&&frame_count<99)frame_count<=frame_count+1;
  end
 end
 // 5x7 font, four display pixels per font pixel, 32-pixel character cells.
 function[34:0] font;
  input[4:0]glyph;
  begin case(glyph)
   0:font=35'b01110_10001_10011_10101_11001_10001_01110;
   1:font=35'b00100_01100_00100_00100_00100_00100_01110;
   2:font=35'b01110_10001_00001_00010_00100_01000_11111;
   3:font=35'b11110_00001_00001_01110_00001_00001_11110;
   4:font=35'b00010_00110_01010_10010_11111_00010_00010;
   5:font=35'b11111_10000_10000_11110_00001_00001_11110;
   6:font=35'b01110_10000_10000_11110_10001_10001_01110;
   7:font=35'b11111_00001_00010_00100_01000_01000_01000;
   8:font=35'b01110_10001_10001_01110_10001_10001_01110;
   9:font=35'b01110_10001_10001_01111_00001_00001_01110;
   10:font=35'b10001_10001_01010_00100_01010_10001_10001; // X
   11:font=35'b11111_10000_10000_11110_10000_10000_10000; // F
   12:font=35'b11110_10001_10001_11110_10000_10000_10000; // P
   13:font=35'b01111_10000_10000_01110_00001_00001_11110; // S
   default:font=0;
  endcase end
 endfunction
 wire[11:0]tx=x-96,ty=y-14;
 wire[4:0]character=tx[9:5];
 wire[2:0]column=tx[4:2],row=ty[4:2];
 reg[4:0]glyph;
 always @* begin
  case(character)
   0:glyph=1;1:glyph=9;2:glyph=2;3:glyph=0;4:glyph=10;
   5:glyph=1;6:glyph=0;7:glyph=8;8:glyph=0;
   10:glyph=fps/10;11:glyph=fps%10;
   13:glyph=11;14:glyph=12;15:glyph=13;
   default:glyph=31;
  endcase
 end
 wire[34:0]bits=font(glyph);
 assign panel=enable&&x>=80&&x<624&&y<56;
 // Select one fixed 5-bit row, then one of five columns. Avoid the wide
 // multiply/subtract/barrel-mux used by bits[34-row*5-column].
 reg[4:0]row_bits;
 always @*case(row)
  0:row_bits=bits[34:30];1:row_bits=bits[29:25];2:row_bits=bits[24:20];
  3:row_bits=bits[19:15];4:row_bits=bits[14:10];5:row_bits=bits[9:5];
  6:row_bits=bits[4:0];default:row_bits=0;
 endcase
 wire[2:0]column_bit=3'd4-column;
 assign ink=panel&&x>=96&&y>=14&&y<42&&column<5&&row<7&&row_bits[column_bit];
endmodule
