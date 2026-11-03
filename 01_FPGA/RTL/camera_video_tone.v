`timescale 1ns/1ps
// Four pixels/clock; tables may only be programmed while video DMA is disabled.
module camera_video_tone(
 input wire pixel_clk,rst_n,bus_clk,allow_write,
 input wire [2:0] table_we,input wire [7:0] table_address,table_data,
 input wire [127:0] data_i,input wire valid_i,user_i,last_i,
 output wire [127:0] data_o,output reg valid_o,user_o,last_o
);
 reg[7:0] frame_id;
 always @(posedge pixel_clk or negedge rst_n)begin
  if(!rst_n)frame_id<=0;else if(valid_i&&user_i)frame_id<=frame_id+1;
 end
 genvar p,c;
 generate for(p=0;p<4;p=p+1)begin:PIXEL
  for(c=0;c<3;c=c+1)begin:CHANNEL
   reg [7:0] lut[0:255];reg[7:0] value;
   if(c==0)initial $readmemh("camera-tone-b.hex",lut);
   if(c==1)initial $readmemh("camera-tone-g.hex",lut);
   if(c==2)initial $readmemh("camera-tone-r.hex",lut);
   always @(posedge bus_clk)if(allow_write&&table_we[c])lut[table_address]<=table_data;
   always @(posedge pixel_clk)if(valid_i)value<=lut[data_i[p*32+c*8+:8]];
   assign data_o[p*32+c*8+:8]=value;
  end
  assign data_o[p*32+24+:8]=frame_id;
 end endgenerate
 always @(posedge pixel_clk or negedge rst_n)begin
  if(!rst_n)begin valid_o<=0;user_o<=0;last_o<=0;end
  else begin valid_o<=valid_i;user_o<=user_i;last_o<=last_i;end
 end
endmodule
