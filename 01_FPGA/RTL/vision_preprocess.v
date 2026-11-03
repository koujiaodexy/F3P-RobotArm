`timescale 1ns/1ps
module vision_preprocess #(parameter WIDTH=480,HEIGHT=270)(
 input wire clk,rst_n,bus_clk,cfg_allow,cfg_we,input wire[7:0]cfg_address,input wire[3:0]cfg_data,
 input wire[7:0]saturation_min,value_min,input wire[9:0]roi_x0,roi_y0,roi_x1,roi_y1,
 input wire[23:0]data_i,input wire valid_i,user_i,last_i,
 output wire[63:0]data_o,output wire valid_o,user_o,last_o,error_o
);
 wire[47:0] gaussian;wire gv,gu,gl,gi,ge;
 vision_gaussian #(.WIDTH(WIDTH),.HEIGHT(HEIGHT)) g(.clk(clk),.rst_n(rst_n),.data_i(data_i),.valid_i(valid_i),.user_i(user_i),.last_i(last_i),
 .roi_x0(roi_x0),.roi_y0(roi_y0),.roi_x1(roi_x1),.roi_y1(roi_y1),.data_o(gaussian),.valid_o(gv),.user_o(gu),.last_o(gl),.in_roi_o(gi),.error_o(ge));
 wire[63:0]data[0:6];wire[6:0]v,u,l;wire[5:0]errors;
 vision_hsv hsv(.pixel_clk(clk),.rst_n(rst_n),.bus_clk(bus_clk),.cfg_allow(cfg_allow),.cfg_we(cfg_we),.cfg_address(cfg_address),.cfg_data(cfg_data),
 .saturation_min(saturation_min),.value_min(value_min),.data_i(gaussian),.valid_i(gv),.user_i(gu),.last_i(gl),.inside_i(gi),.data_o(data[0]),.valid_o(v[0]),.user_o(u[0]),.last_o(l[0]));
 genvar n;generate for(n=0;n<6;n=n+1)begin:FILTER
  localparam OP_ERODE=(n==0||n==4||n==5);
  vision_morph #(.WIDTH(WIDTH),.HEIGHT(HEIGHT),.ERODE(OP_ERODE)) m(.clk(clk),.rst_n(rst_n),.data_i(data[n]),.valid_i(v[n]),.user_i(u[n]),.last_i(l[n]),
   .roi_x0(roi_x0),.roi_y0(roi_y0),.roi_x1(roi_x1),.roi_y1(roi_y1),.data_o(data[n+1]),.valid_o(v[n+1]),.user_o(u[n+1]),.last_o(l[n+1]),.error_o(errors[n]));
 end endgenerate
 assign data_o=data[6];assign valid_o=v[6];assign user_o=u[6];assign last_o=l[6];assign error_o=ge||(|errors);
endmodule
