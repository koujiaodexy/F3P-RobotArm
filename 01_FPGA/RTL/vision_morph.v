`timescale 1ns/1ps
module vision_morph #(parameter WIDTH=480,HEIGHT=270,ERODE=1)(
 input wire clk,rst_n,input wire[63:0] data_i,input wire valid_i,user_i,last_i,
 input wire[9:0] roi_x0,roi_y0,roi_x1,roi_y1,
 output reg[63:0] data_o,output reg valid_o,user_o,last_o,output wire error_o
);
 wire[63:0] w00,w01,w02,w10,w11,w12,w20,w21,w22;wire v,u,l;wire[9:0]x,y;
 vision_window3x3 #(.WIDTH(WIDTH),.HEIGHT(HEIGHT),.DATA_WIDTH(64)) win(
 .clk(clk),.rst_n(rst_n),.data_i(data_i),.valid_i(valid_i),.user_i(user_i),.last_i(last_i),
 .p00(w00),.p01(w01),.p02(w02),.p10(w10),.p11(w11),.p12(w12),.p20(w20),.p21(w21),.p22(w22),
 .valid_o(v),.user_o(u),.last_o(l),.x_o(x),.y_o(y),.error_o(error_o));
 localparam[3:0] BORDER=ERODE?4'hf:4'h0;
 wire[3:0] top=y==roi_y0?BORDER:w01[51:48],bottom=y==roi_y1-1?BORDER:w21[51:48];
 wire[3:0] left=x==roi_x0?BORDER:w10[51:48],right=x==roi_x1-1?BORDER:w12[51:48];
 wire[3:0] value=ERODE?(w11[51:48]&top&bottom&left&right):(w11[51:48]|top|bottom|left|right);
 wire[3:0] result=(x>=roi_x0&&x<roi_x1&&y>=roi_y0&&y<roi_y1)?value:4'd0;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin data_o<=0;valid_o<=0;user_o<=0;last_o<=0;end
  else begin valid_o<=v;user_o<=u;last_o<=l;if(v)data_o<={w11[63:52],result,w11[47:0]};end
 end
endmodule
