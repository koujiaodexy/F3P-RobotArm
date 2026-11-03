`timescale 1ns/1ps
// Asynchronous recognition-result mailbox. No DDR master and no motion outputs.
// Word addresses 0x70..0x77 were unused in build05 (byte 0x1c0..0x1dc).
// The bus locks the entire staging payload until the display acknowledges it.
// A result becomes visible only at a rising VS edge; old results expire even
// when VS stops, provided the display clock keeps running.
module vision_result_osd #(
 parameter MAX_BOXES=16, parameter TTL_TICKS=37125000
)(
 input wire bus_clk,bus_rst_n,bus_write,
 input wire [7:0] bus_address,input wire [31:0] bus_data,
 output reg [31:0] bus_read,
 input wire display_clk,display_rst_n,enable,vs,de,
 input wire [11:0] x,y,
 output reg ink,output reg [23:0] rgb
);
 localparam DESC_BITS=73;
 reg [MAX_BOXES*DESC_BITS-1:0] stage;
 reg [31:0] stage_frame,sequence_number,ack_sequence,ack_frame,rejected;
 reg [4:0] index;
 reg [31:0] xy0,xy1;
 reg request;
 reg [1:0] ack_sync;
 reg acknowledge;
 wire busy=request!=ack_sync[1];
 wire valid_geometry=xy0[15:0]<xy1[15:0] && xy1[15:0]<=1920 &&
                     xy0[31:16]<xy1[31:16] && xy1[31:16]<=1080;
 integer i,j;
 always @(posedge bus_clk or negedge bus_rst_n)begin
  if(!bus_rst_n)begin
   stage<=0;stage_frame<=0;sequence_number<=0;ack_sequence<=0;ack_frame<=0;
   rejected<=0;index<=0;xy0<=0;xy1<=0;request<=0;ack_sync<=0;
  end else begin
   ack_sync<={ack_sync[0],acknowledge};
   if(busy && request==ack_sync[0])begin
    ack_sequence<=sequence_number;ack_frame<=stage_frame;
   end
   if(bus_write && bus_address>=8'h71 && bus_address<=8'h77)begin
    if(busy)rejected<=rejected+1'b1;
    else case(bus_address)
     8'h71:case(bus_data)
      32'h4f530000:stage<=0;
      32'h4f530001:begin sequence_number<=sequence_number+1'b1;request<=~request;end
      default:rejected<=rejected+1'b1;
     endcase
     8'h72:if(bus_data<MAX_BOXES)index<=bus_data[4:0];
            else begin index<=MAX_BOXES;rejected<=rejected+1'b1;end
     8'h73:xy0<=bus_data;
     8'h74:xy1<=bus_data;
     8'h75:if(index<MAX_BOXES)begin
      // Constant slices + decoded enables avoid a wide variable part-select
      // barrel shifter and the inferred DSP used for index*DESC_BITS.
      for(j=0;j<MAX_BOXES;j=j+1)begin
       if(index==j)begin
        if(!bus_data[31] || valid_geometry)
         stage[j*DESC_BITS+:DESC_BITS]<={bus_data[31],bus_data[23:0],
          xy1[27:16],xy1[11:0],xy0[27:16],xy0[11:0]};
        else stage[j*DESC_BITS+72]<=0;
       end
      end
      if(bus_data[31]&&!valid_geometry)rejected<=rejected+1'b1;
     end else rejected<=rejected+1'b1;
     8'h76:stage_frame<=bus_data;
     default:rejected<=rejected+1'b1;
    endcase
   end
  end
 end
 // Bundled-data CDC: request travels through 3 FFs. Payload sampling plus
 // the VS-gated active register form the two data stages.
 // Data cannot change before acknowledge returns through 2 bus FFs. The
 // request's third stage ensures the first payload stage has already settled.
 // The existing build05 asynchronous clock groups cover these clock domains.
 reg [2:0] req_sync;
 reg [MAX_BOXES*DESC_BITS-1:0] payload1,active;
 reg [1:0] enable_sync;
 reg prev_vs;
 reg [31:0] age;
 reg [1:0] expired_sync;
 wire expired=age>=TTL_TICKS;
 always @(posedge display_clk or negedge display_rst_n)begin
  if(!display_rst_n)begin
   req_sync<=0;payload1<=0;active<=0;acknowledge<=0;
   enable_sync<=0;prev_vs<=0;age<=TTL_TICKS;
  end else begin
   req_sync<={req_sync[1:0],request};payload1<=stage;
   enable_sync<={enable_sync[0],enable};prev_vs<=vs;
   if(!enable_sync[1])begin active<=0;age<=TTL_TICKS;end
   else if(!expired)age<=age+1'b1;
   if(vs&&!prev_vs && req_sync[2]!=acknowledge)begin
    active<=enable_sync[1]?payload1:0;
    age<=enable_sync[1]?0:TTL_TICKS;
    acknowledge<=req_sync[2];
   end
  end
 end
 always @(posedge bus_clk or negedge bus_rst_n)begin
  if(!bus_rst_n)expired_sync<=3;
  else expired_sync<={expired_sync[0],expired};
 end
 always @*begin
  bus_read=0;
  case(bus_address)
   8'h70:bus_read=32'h4f534431; // OSD1 capability; old build05 reads zero.
   8'h71:bus_read={30'd0,expired_sync[1],busy};
   8'h72:bus_read=ack_sequence;
   8'h73:bus_read=ack_frame;
   8'h74:bus_read=sequence_number;
   8'h75:bus_read=rejected;
   8'h76:bus_read=TTL_TICKS;
   8'h77:bus_read=MAX_BOXES;
  endcase
 end
 // Coordinates are in the native 1920x1080 image, half-open rectangles.
 // The lowest index has priority on overlap. Draw a 3-pixel inward border.
 reg [DESC_BITS-1:0] d;
 reg [11:0] dx0,dx1,dy0,dy1;
 always @*begin
  ink=0;rgb=0;d=0;dx0=0;dx1=0;dy0=0;dy1=0;
  for(i=MAX_BOXES-1;i>=0;i=i-1)begin
   d=active[i*DESC_BITS+:DESC_BITS];
   // Native-coordinate differences fit 12 bits inside a valid rectangle.
   // Explicit widths avoid unsized constants widening each subtract to 32.
   dx0=x-d[11:0];dx1=d[35:24]-x;dy0=y-d[23:12];dy1=d[47:36]-y;
   if(enable_sync[1]&&!expired&&de&&d[72] &&
      x>=d[11:0]&&x<d[35:24]&&y>=d[23:12]&&y<d[47:36] &&
      ((dx0<12'd3)||(dx1<=12'd3)||(dy0<12'd3)||(dy1<=12'd3)))begin
    ink=1;rgb=d[71:48];
   end
  end
 end
endmodule
