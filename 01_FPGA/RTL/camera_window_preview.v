`timescale 1ns/1ps
// FPGA HDMI window: 480x270 RGB888 from six reserved compact-DDR slots.
// Eight tagged rows replace the low-resolution whole-frame BRAM buffers.
// The ARM never copies/renders RGB. Accepted FDMA requests always drain.
module camera_window_preview(
 input wire bus_clk,bus_rst_n,bus_write,input wire[7:0]bus_address,input wire[31:0]bus_data,
 output reg[31:0]bus_read,output wire[31:0]osd_read,input wire run,output reg raw_pause,
 input wire ui_clk,ui_rst_n,input wire[2:0]compact_bank,input wire[31:0]compact_count,compact_fid,
 input wire camera_clk,camera_rst_n,input wire[23:0]camera_rgb,
 input wire camera_valid,camera_user,camera_last,input wire[31:0]camera_fid,
 input wire pixel_clk,vs,de,output reg[31:0]pixel,output reg ink,
 output reg[31:0]raddr,output reg[15:0]rsize,output wire rreq,rready,
 input wire rbusy,rvalid,input wire[63:0]rdata
);
 wire reset_n=bus_rst_n&&ui_rst_n;
 // Accepted HP read beats enter local registers before header checks and RAM.
 // This preserves one beat per clock and cuts the hard-PS -> ERAM data path.
 reg response_valid;reg[63:0]response_data;
 always @(posedge ui_clk or negedge reset_n)begin
  if(!reset_n)begin response_valid<=0;response_data<=0;end
  else begin response_valid<=rvalid;if(rvalid)response_data<=rdata;end
 end
 reg enabled;reg[11:0]left,top;reg[3:0]zoom;
 wire[11:0]configured_width=zoom*12'd192,configured_height=zoom*12'd108;
 always @(posedge bus_clk or negedge bus_rst_n)begin
  if(!bus_rst_n)begin enabled<=0;raw_pause<=0;left<=1504;top<=800;zoom<=2;end
  else begin
   if(!run)begin enabled<=0;raw_pause<=0;end
   if(bus_write)case(bus_address)
    8'h79:if(bus_data[31:16]==16'h574e)begin enabled<=bus_data[0]&&run;raw_pause<=bus_data[1]&&run;end
    8'h7a:if(!enabled&&bus_data[15:0]>=4&&bus_data[15:0]+{4'd0,configured_width}<=1920&&bus_data[31:16]+{4'd0,configured_height}<=1080)begin left<=bus_data[11:0];top<=bus_data[27:16];end
    8'h7b:if(!enabled)case(bus_data)
     32'h00d80180:zoom<=4'd2;32'h01440240:zoom<=4'd3;
     32'h01b00300:zoom<=4'd4;32'h021c03c0:zoom<=4'd5;
     32'h02880480:zoom<=4'd6;32'h02f40540:zoom<=4'd7;
     32'h03600600:zoom<=4'd8;default:begin end
    endcase
   endcase
  end
 end
 reg[2:0]enable_sync,capture_sync;
 reg[27:0]position1,position2;
 reg active,prev_vs,prev_de,request;reg[7:0]generation;
 reg[11:0]x,y,l,t,width,height;reg[3:0]display_zoom;
 reg[8:0]sx,sy,consumed_gray;reg[4:0]phase_x,phase_y;
 wire[5:0]denominator={1'b0,display_zoom,1'b0};
 wire[5:0]next_phase_x={1'b0,phase_x}+6'd5,next_phase_y={1'b0,phase_y}+6'd5;
 wire inside=active&&de&&x>=l&&x<l+width&&y>=t&&y<t+height;
 wire[11:0]wx=x-l,wy=y-t;
 always @(posedge pixel_clk or negedge reset_n)begin
  if(!reset_n)begin
   enable_sync<=0;capture_sync<=0;position1<=0;position2<=0;
   active<=0;prev_vs<=0;prev_de<=0;request<=0;generation<=0;
   x<=0;y<=0;l<=0;t<=0;width<=384;height<=216;display_zoom<=2;
   sx<=0;sy<=0;phase_x<=0;phase_y<=0;consumed_gray<=0;
  end else begin
   enable_sync<={enable_sync[1:0],enabled&&run};capture_sync<={capture_sync[1:0],raw_pause&&run};
   position1<={zoom,top,left};position2<=position1;prev_vs<=vs;prev_de<=de;
   if(!enable_sync[2])active<=0;
   if(vs&&!prev_vs)begin
    active<=enable_sync[2];l<=position2[11:0]-12'd4;t<=position2[23:12];
    display_zoom<=position2[27:24];width<=position2[27:24]*12'd192;height<=position2[27:24]*12'd108;
    x<=0;y<=0;sx<=0;sy<=0;phase_x<=0;phase_y<=0;consumed_gray<=0;
    if(enable_sync[2]&&capture_sync[2])begin generation<=generation+1'b1;request<=~request;end
   end else if(de)x<=x+1'b1;
   else begin x<=0;if(prev_de)y<=y+1'b1;end
   // Rational nearest-neighbour mapping, floor(output * 480 / width).
   // Both axes preserve the complete field of view; no divider in the pixel path.
   if(inside)begin
    if(wx==0)begin
     sx<=0;phase_x<=0;
     if(wy==0)begin sy<=0;phase_y<=0;end
     else if(next_phase_y>=2*denominator)begin sy<=sy+2;phase_y<=next_phase_y-2*denominator;end
     else if(next_phase_y>=denominator)begin sy<=sy+1'b1;phase_y<=next_phase_y-denominator;end
     else phase_y<=next_phase_y;
    end else if(next_phase_x>=2*denominator)begin sx<=sx+2;phase_x<=next_phase_x-2*denominator;end
    else if(next_phase_x>=denominator)begin sx<=sx+1'b1;phase_x<=next_phase_x-denominator;end
    else phase_x<=next_phase_x;
   end
   consumed_gray<=(sy>>1)^sy;
  end
 end
 // The request toggle is slower than its held generation payload. Completion
 // bank/FID are already in ui_clk. A new VS never cancels an accepted burst.
 reg[2:0]req_sync;reg[7:0]gen1,gen2;reg[8:0]row_gray1,row_gray2;
 reg[1:0]capture_ui;reg request_seen;
 function[8:0]row_binary;input[8:0]g;integer k;begin row_binary[8]=g[8];for(k=7;k>=0;k=k-1)row_binary[k]=row_binary[k+1]^g[k];end endfunction
 wire[8:0]consumed=row_binary(row_gray2);
 always @(posedge ui_clk or negedge reset_n)begin
  if(!reset_n)begin req_sync<=0;gen1<=0;gen2<=0;row_gray1<=0;row_gray2<=0;capture_ui<=0;end
  else begin
   req_sync<={req_sync[1:0],request};gen1<=generation;gen2<=gen1;
   row_gray1<=consumed_gray;row_gray2<=row_gray1;capture_ui<={capture_ui[0],raw_pause&&run};
  end
 end
 localparam IDLE=0,HREQ=1,HDRAIN=2,HCHECK=3,RWAIT=4,RREQ=5,RDRAIN=6,RCOMMIT=7,FREQ=8,FDRAIN=9,FCHECK=10;
 reg[3:0]state;reg[31:0]slot_base,selected_fid,rgb_hash,footer_hash,footer_fid;
 reg[7:0]selected_gen;reg[8:0]load_row,beats;
 reg row_error,header_error,frame_error,address_error;
 reg[7:0]ready_gen;reg header_ready;reg[31:0]loaded_frames;
 reg[17:0]tags[0:7]; // good, generation, source row; published after final RAM write
 integer i,j;
 assign rreq=state==HREQ||state==RREQ||state==FREQ;
 assign rready=1'b1;
 wire[31:0]row_offset=({23'd0,load_row}<<11)+({23'd0,load_row}<<10)+({23'd0,load_row}<<5)+({23'd0,load_row}<<4);
 function[31:0]hash_pixel;input[31:0]h;input[23:0]c;begin hash_pixel={h[26:0],h[31:27]}^{8'd0,c};end endfunction
 wire[31:0]hash_pair=hash_pixel(hash_pixel(rgb_hash,response_data[23:0]),response_data[55:32]);
 wire writing_row=state==RDRAIN&&response_valid&&beats<240;
 always @(posedge ui_clk or negedge reset_n)begin
  if(!reset_n)begin
   state<=IDLE;raddr<=0;rsize<=0;request_seen<=0;slot_base<=0;selected_fid<=0;selected_gen<=0;
   load_row<=0;beats<=0;row_error<=0;header_error<=0;frame_error<=0;address_error<=0;
   rgb_hash<=0;footer_hash<=0;footer_fid<=0;header_ready<=0;ready_gen<=0;loaded_frames<=0;
   for(i=0;i<8;i=i+1)tags[i]<=0;
  end else begin
   if(!capture_ui[1]&&!rbusy&&!rreq&&!response_valid&&!rvalid)begin
    state<=IDLE;header_ready<=0;frame_error<=0;address_error<=0;
   end else if(req_sync[2]!=request_seen&&!rbusy&&!rreq&&!response_valid&&!rvalid)begin
    request_seen<=req_sync[2];header_ready<=0;selected_gen<=gen2;rgb_hash<=0;load_row<=0;beats<=0;header_error<=0;
    if(compact_count!=0&&compact_bank<6&&capture_ui[1])begin
     slot_base<=32'h3d800000+{9'd0,compact_bank,20'd0};
     raddr<=32'h3d800000+{9'd0,compact_bank,20'd0};rsize<=4;
     selected_fid<=compact_fid;state<=HREQ;
    end else state<=IDLE;
   end else begin
    if(response_valid)begin
     beats<=beats+1'b1;
     if(state==HDRAIN)begin
      if(beats==0&&(response_data[31:0]!=32'h43564d31||response_data[63:32]!=selected_fid))header_error<=1;
      if(beats==1&&response_data[31:0]!={16'd270,16'd480})header_error<=1;
     end
     if(state==RDRAIN)begin
      rgb_hash<=hash_pair;
      if(beats>=240||response_data[31:24]!=selected_fid[7:0]||response_data[63:56]!=selected_fid[7:0])row_error<=1;
     end
     if(state==FDRAIN&&beats==1)begin footer_hash<=response_data[31:0];footer_fid<=response_data[63:32];end
     if(state!=HDRAIN&&state!=RDRAIN&&state!=FDRAIN)frame_error<=1;
    end
    case(state)
     HREQ:if(rbusy)state<=HDRAIN;
     HDRAIN:if(!rbusy&&!response_valid&&!rvalid)state<=HCHECK;
     HCHECK:begin
      if(beats!=4||header_error)begin frame_error<=1;state<=IDLE;end
      else begin header_ready<=1;ready_gen<=selected_gen;state<=RWAIT;end
     end
     RWAIT:if(load_row<270&&{1'b0,load_row}<={1'b0,consumed}+10'd6)begin
      raddr<=slot_base+32'd992+row_offset;rsize<=240;beats<=0;row_error<=0;tags[load_row[2:0]]<=0;state<=RREQ;
     end
     RREQ:if(rbusy)state<=RDRAIN;
     RDRAIN:if(!rbusy&&!response_valid&&!rvalid)state<=RCOMMIT;
     RCOMMIT:begin
      if(beats!=240||row_error)frame_error<=1;
      tags[load_row[2:0]]<={beats==240&&!row_error,selected_gen,load_row};
      if(load_row==269)begin raddr<=slot_base+32'd842432;rsize<=2;beats<=0;state<=FREQ;end
      else begin load_row<=load_row+1'b1;state<=RWAIT;end
     end
     FREQ:if(rbusy)state<=FDRAIN;
     FDRAIN:if(!rbusy&&!response_valid&&!rvalid)state<=FCHECK;
     FCHECK:begin
      if(beats!=2||footer_hash!=rgb_hash||footer_fid!=selected_fid)frame_error<=1;
      else loaded_frames<=loaded_frames+1'b1;
      state<=IDLE;
     end
    endcase
   end
   if(rreq&&(raddr<32'h3d800000||raddr+{13'd0,rsize,3'd0}>32'h3de00000||raddr[2:0]!=0||rsize==0||rsize>240))address_error<=1;
  end
 end
 // Eight independent dual-clock line memories. A row can be replaced only once
 // the display has advanced at least two source rows beyond its former owner.
 wire[63:0]ram_q[0:7];genvar b;
 generate for(b=0;b<8;b=b+1)begin:line_cache
  reg[63:0]mem[0:255];reg[7:0]read_address;reg[63:0]q;
  always @(posedge ui_clk)if(writing_row&&load_row[2:0]==b)mem[beats[7:0]]<=response_data;
  always @(posedge pixel_clk)if(sy[2:0]==b)read_address<=sx[8:1];
  always @(posedge pixel_clk)q<=mem[read_address];
  assign ram_q[b]=q;
 end endgenerate
 reg[17:0]tag1[0:7],tag2[0:7];reg[7:0]ready_gen1,ready_gen2;reg[1:0]header_sync;
 reg[31:0]fid1,frame_fid;reg[1:0]error_sync,address_sync;
 always @(posedge pixel_clk or negedge reset_n)begin
  if(!reset_n)begin
   for(j=0;j<8;j=j+1)begin tag1[j]<=0;tag2[j]<=0;end
   ready_gen1<=0;ready_gen2<=0;header_sync<=0;fid1<=0;frame_fid<=0;error_sync<=0;address_sync<=0;
  end else begin
   for(j=0;j<8;j=j+1)begin tag1[j]<=tags[j];tag2[j]<=tag1[j];end
   ready_gen1<=ready_gen;ready_gen2<=ready_gen1;header_sync<={header_sync[0],header_ready};
   fid1<=selected_fid;frame_fid<=fid1;error_sync<={error_sync[0],frame_error};address_sync<={address_sync[0],address_error};
  end
 end
 wire have_frame=header_sync[1]&&ready_gen2==generation;
 reg consume1,consume2,consume3,good2,good3,half2,half3,first2,first3;
 reg[2:0]line2,line3;reg[11:0]native_x,native_y;reg box_ink3;reg[23:0]box_rgb3;
 wire box_ink;wire[23:0]box_rgb;
 wire[63:0]display_pair=ram_q[line3];
 wire[31:0]display_rgb=half3?display_pair[63:32]:display_pair[31:0];
 vision_window_osd boxes(.bus_clk(bus_clk),.bus_rst_n(bus_rst_n),.bus_write(bus_write),.bus_address(bus_address),.bus_data(bus_data),.bus_read(osd_read),
  .display_clk(pixel_clk),.display_rst_n(reset_n),.enable(active),.vs(vs),.de(consume2&&good2),.x(native_x),.y(native_y),.ink(box_ink),.rgb(box_rgb));
 reg[31:0]frames,unique_frames,underflows,previous_fid;reg have_previous;
 always @(posedge pixel_clk or negedge reset_n)begin
  if(!reset_n)begin
   consume1<=0;consume2<=0;consume3<=0;good2<=0;good3<=0;half2<=0;half3<=0;first2<=0;first3<=0;
   line2<=0;line3<=0;native_x<=0;native_y<=0;box_ink3<=0;box_rgb3<=0;pixel<=0;ink<=0;
   frames<=0;unique_frames<=0;underflows<=0;previous_fid<=0;have_previous<=0;
  end else begin
   consume1<=inside;consume2<=consume1;consume3<=consume2;
   good2<=have_frame&&tag2[sy[2:0]]=={1'b1,generation,sy}&&sx<480&&sy<270;
   good3<=good2;half2<=sx[0];half3<=half2;line2<=sy[2:0];line3<=line2;
   native_x<={1'b0,sx,2'b00};native_y<={1'b0,sy,2'b00};
   first2<=sx==0&&sy==0&&phase_x==0&&phase_y==0;first3<=first2;box_ink3<=box_ink;box_rgb3<=box_rgb;
   ink<=consume3&&active;
   pixel<=good3&&display_rgb[31:24]==frame_fid[7:0]?(box_ink3?{8'd0,box_rgb3}:{8'd0,display_rgb[23:0]}):32'h00132030;
   if(!active)have_previous<=0;
   if(consume3&&active)begin
    if(!good3||display_rgb[31:24]!=frame_fid[7:0])underflows<=underflows+1'b1;
    if(first3)begin
     frames<=frames+1'b1;
     if(!have_previous||previous_fid!=frame_fid)unique_frames<=unique_frames+1'b1;
     previous_fid<=frame_fid;have_previous<=1;
    end
   end
  end
 end
 reg[31:0]fg,ug,eg,fg1,fg2,ug1,ug2,eg1,eg2;reg[4:0]health1,health2;
 always @(posedge pixel_clk)begin fg<=(frames>>1)^frames;ug<=(unique_frames>>1)^unique_frames;eg<=(underflows>>1)^underflows;end
 always @(posedge bus_clk)begin
  fg1<=fg;fg2<=fg1;ug1<=ug;ug2<=ug1;eg1<=eg;eg2<=eg1;
  health1<={active,1'b0,1'b0,error_sync[1],address_sync[1]};health2<=health1;
 end
 function[31:0]binary;input[31:0]g;integer k;begin binary[31]=g[31];for(k=30;k>=0;k=k-1)binary[k]=binary[k+1]^g[k];end endfunction
 always @*begin
  case(bus_address)
   8'h78:bus_read=32'h574e5034;
   8'h79:bus_read={30'd0,raw_pause,enabled};
   8'h7a:bus_read={4'd0,top,4'd0,left};8'h7b:bus_read={4'd0,configured_height,4'd0,configured_width};
   8'h7c:bus_read=binary(fg2);8'h7d:bus_read=binary(ug2);8'h7e:bus_read=binary(eg2);
   8'h7f:bus_read={27'd0,health2};default:bus_read=0;
  endcase
 end
endmodule
