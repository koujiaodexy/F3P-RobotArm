`timescale 1ns/1ps
module vision_sampler #(parameter WIDTH=480,HEIGHT=270)(
 input wire clk,rst_n,pattern,
 input wire[127:0]data_i,input wire valid_i,user_i,last_i,input wire[31:0]source_id,
 output reg[23:0]data_o,output reg valid_o,user_o,last_o,output reg[31:0]frame_id,
 output reg error
);
 reg[10:0]y;reg[9:0]x;reg started;
 wire selected=user_i||y[1:0]==0;
 wire[9:0]sy=y>>2;
 reg[23:0]test_rgb;
 always @*begin
  test_rgb=24'hdcdcdc;
  if(x>=50&&x<190&&sy>=35&&sy<115)test_rgb=24'hff0000;
  if(x>=290&&x<430&&sy>=35&&sy<115)test_rgb=24'hffff00;
  if(x>=50&&x<190&&sy>=155&&sy<235)test_rgb=24'h0000ff;
  if(x>=290&&x<430&&sy>=155&&sy<235)test_rgb=24'h00ff00;
 end
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin y<=0;x<=0;started<=0;valid_o<=0;user_o<=0;last_o<=0;data_o<=0;frame_id<=0;error<=0;end
  else begin
   valid_o<=0;user_o<=0;last_o<=0;
   if(valid_i&&(started||user_i))begin
    if(user_i)begin y<=0;x<=0;started<=1;frame_id<=source_id;end
    if(selected)begin data_o<=pattern?test_rgb:data_i[23:0];valid_o<=1;user_o<=user_i;last_o<=last_i;end
    if(last_i)begin if(x!=WIDTH-1)error<=1;x<=0;y<=y==HEIGHT*4-1?0:y+1;end
    else x<=user_i?1:x+1;
   end
  end
 end
endmodule
