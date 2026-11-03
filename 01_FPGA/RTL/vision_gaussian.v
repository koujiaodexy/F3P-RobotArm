`timescale 1ns/1ps
module vision_gaussian #(parameter WIDTH=480,HEIGHT=270)(
 input wire clk,rst_n,input wire[23:0] data_i,input wire valid_i,user_i,last_i,
 input wire[9:0] roi_x0,roi_y0,roi_x1,roi_y1,
 output reg[47:0] data_o,output reg valid_o,user_o,last_o,in_roi_o,output wire error_o
);
 wire[23:0] w00,w01,w02,w10,w11,w12,w20,w21,w22;wire v,u,l;wire[9:0] x,y;
 vision_window3x3 #(.WIDTH(WIDTH),.HEIGHT(HEIGHT),.DATA_WIDTH(24)) win(
 .clk(clk),.rst_n(rst_n),.data_i(data_i),.valid_i(valid_i),.user_i(user_i),.last_i(last_i),
 .p00(w00),.p01(w01),.p02(w02),.p10(w10),.p11(w11),.p12(w12),.p20(w20),.p21(w21),.p22(w22),
 .valid_o(v),.user_o(u),.last_o(l),.x_o(x),.y_o(y),.error_o(error_o));
 reg[23:0] a00,a01,a02,a10,a11,a12,a20,a21,a22;
 always @*begin
  a00=w00;a01=w01;a02=w02;a10=w10;a11=w11;a12=w12;a20=w20;a21=w21;a22=w22;
  if(y==roi_y0)begin a00=w20;a01=w21;a02=w22;end
  if(y==roi_y1-1)begin a20=w00;a21=w01;a22=w02;end
  if(x==roi_x0)begin a00=a02;a10=a12;a20=a22;end
  if(x==roi_x1-1)begin a02=a00;a12=a10;a22=a20;end
 end
 function[7:0] gaussian;
  input integer c;reg[11:0] total;
  begin total={4'd0,a00[c+:8]}+({4'd0,a01[c+:8]}<<1)+{4'd0,a02[c+:8]}+
    ({4'd0,a10[c+:8]}<<1)+({4'd0,a11[c+:8]}<<2)+({4'd0,a12[c+:8]}<<1)+
    {4'd0,a20[c+:8]}+({4'd0,a21[c+:8]}<<1)+{4'd0,a22[c+:8]}+12'd8;
   gaussian=total[11:4];end
 endfunction
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin data_o<=0;valid_o<=0;user_o<=0;last_o<=0;in_roi_o<=0;end
  else begin valid_o<=v;user_o<=u;last_o<=l;
   if(v)begin data_o<={w11,gaussian(16),gaussian(8),gaussian(0)};in_roi_o<=x>=roi_x0&&x<roi_x1&&y>=roi_y0&&y<roi_y1;end
  end
 end
endmodule
