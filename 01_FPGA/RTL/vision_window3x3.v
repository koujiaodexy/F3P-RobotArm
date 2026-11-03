`timescale 1ns/1ps
// Streaming 3x3 window with synchronous read-before-write row RAMs.
// Source rows need two idle clocks. The last virtual row is generated locally.
module vision_window3x3 #(parameter WIDTH=480,HEIGHT=270,DATA_WIDTH=24,FLUSH_GAP=320)(
 input wire clk,rst_n,input wire[DATA_WIDTH-1:0] data_i,input wire valid_i,user_i,last_i,
 output reg[DATA_WIDTH-1:0] p00,p01,p02,p10,p11,p12,p20,p21,p22,
 output reg valid_o,user_o,last_o,output reg[9:0] x_o,y_o,output reg error_o
);
 reg[DATA_WIDTH-1:0] row1[0:WIDTH-1],row2[0:WIDTH-1];
 reg[9:0] x,y,vx;reg active;reg[1:0] flush_state;reg[15:0] gap;
 reg[DATA_WIDTH-1:0] top,mid,bot,ta,tb,ma,mb,ba,bb;
 reg dv;reg[9:0] dx,dy;reg right_pending;reg[9:0] right_y;
 wire real_fire=valid_i&&flush_state==0&&(active||user_i);
 wire virtual_fire=flush_state==2;
 wire fire=real_fire||virtual_fire;
 wire[9:0] fx=virtual_fire?vx:(user_i?10'd0:x);
 wire[9:0] fy=virtual_fire?HEIGHT:(user_i?10'd0:y);
 wire[DATA_WIDTH-1:0] sample=virtual_fire?{DATA_WIDTH{1'b0}}:data_i;
 always @(posedge clk)if(fire)begin top<=row2[fx];mid<=row1[fx];bot<=sample;row2[fx]<=row1[fx];row1[fx]<=sample;end
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin x<=0;y<=0;vx<=0;active<=0;flush_state<=0;gap<=0;error_o<=0;end
  else begin
   if(valid_i&&user_i&&flush_state!=0)error_o<=1;
   if(real_fire)begin
    if(user_i)begin if(active)error_o<=1;active<=1;x<=1;y<=0;end
    else if(last_i)begin
     if(fx!=WIDTH-1)error_o<=1;
     x<=0;
     if(fy==HEIGHT-1)begin active<=0;y<=0;flush_state<=1;gap<=FLUSH_GAP;end
     else y<=fy+1;
    end else begin if(fx==WIDTH-1)error_o<=1;x<=fx+1;end
   end
   if(flush_state==1)begin if(gap==0)begin flush_state<=2;vx<=0;end else gap<=gap-1;end
   else if(flush_state==2)begin if(vx==WIDTH-1)flush_state<=3;else vx<=vx+1;end
   else if(flush_state==3&&right_pending&&right_y==HEIGHT)flush_state<=0;
  end
 end
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   dv<=0;dx<=0;dy<=0;right_pending<=0;right_y<=0;valid_o<=0;user_o<=0;last_o<=0;x_o<=0;y_o<=0;
   ta<=0;tb<=0;ma<=0;mb<=0;ba<=0;bb<=0;p00<=0;p01<=0;p02<=0;p10<=0;p11<=0;p12<=0;p20<=0;p21<=0;p22<=0;
  end else begin
   dv<=fire;if(fire)begin dx<=fx;dy<=fy;end
   valid_o<=0;user_o<=0;last_o<=0;right_pending<=0;
   if(right_pending)begin
    p00<=ta;p01<=tb;p02<=tb;p10<=ma;p11<=mb;p12<=mb;p20<=ba;p21<=bb;p22<=bb;
    valid_o<=1;last_o<=1;x_o<=WIDTH-1;y_o<=right_y-1;
   end
   if(dv)begin
    if(dx==0)begin ta<=top;tb<=top;ma<=mid;mb<=mid;ba<=bot;bb<=bot;end
    else begin
     if(dy>=1)begin
      p00<=ta;p01<=tb;p02<=top;p10<=ma;p11<=mb;p12<=mid;p20<=ba;p21<=bb;p22<=bot;
      valid_o<=1;user_o<=dx==1&&dy==1;last_o<=0;x_o<=dx-1;y_o<=dy-1;
     end
     ta<=tb;tb<=top;ma<=mb;mb<=mid;ba<=bb;bb<=bot;
    end
    if(dx==WIDTH-1&&dy>=1)begin right_pending<=1;right_y<=dy;end
   end
  end
 end
endmodule
