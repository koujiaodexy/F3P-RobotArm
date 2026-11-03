`timescale 1ns/1ps
// Header + per-line packed HS16, raw RGB32, mask4 + quality/hash trailer.
module vision_pack #(parameter WIDTH=480,HEIGHT=270)(
 input wire clk,rst_n,input wire[63:0] data_i,input wire valid_i,user_i,last_i,
 input wire[31:0] source_frame_id,config_epoch,flags,
 input wire[9:0] roi_x0,roi_y0,roi_x1,roi_y1,
 output reg[63:0] word_o,output reg valid_o,output reg error_o
);
 localparam[15:0] W16=WIDTH,H16=HEIGHT;
 localparam COLLECT=0,RGB=1,MASK=2,FOOT0=3,FOOT1=4;
 reg[2:0] state;reg[2:0] header;
 reg[9:0] x,y;reg line_final;
 reg[31:0] frame_id,epoch,cfg_flags,area,sum_v,pixel_hash;
 reg[9:0] rx0,ry0,rx1,ry1;
 reg[31:0] rgb_hold;reg[63:0] hs_acc,mask_acc,hs_word;reg hs_pending,hs_last;
 reg[63:0] rgb_line[0:WIDTH/2-1],mask_line[0:WIDTH/16-1];
 reg[9:0] read_index;reg[63:0] ram_data;reg ram_valid;reg[2:0] ram_kind;reg ram_last;
 wire[31:0] rgb_pixel={(user_i?source_frame_id[7:0]:frame_id[7:0]),data_i[23:0]};
 always @(posedge clk)begin
  if(valid_i&&state==COLLECT&&x<WIDTH)begin
   if(x[0])rgb_line[x>>1]<={rgb_pixel,rgb_hold};
   if(x[3:0]==15)mask_line[x>>4]<={data_i[51:48],mask_acc[59:0]};
  end
  if(state==RGB&&read_index<WIDTH/2)ram_data<=rgb_line[read_index];
  else if(state==MASK&&read_index<WIDTH/16)ram_data<=mask_line[read_index];
 end
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   state<=COLLECT;header<=0;x<=0;y<=0;line_final<=0;frame_id<=0;epoch<=0;cfg_flags<=0;area<=0;sum_v<=0;pixel_hash<=0;
   rx0<=0;ry0<=0;rx1<=0;ry1<=0;rgb_hold<=0;hs_acc<=0;mask_acc<=0;hs_word<=0;hs_pending<=0;hs_last<=0;
   read_index<=0;ram_valid<=0;ram_kind<=0;ram_last<=0;word_o<=0;valid_o<=0;error_o<=0;
  end else begin
   valid_o<=0;ram_valid<=0;
   if(valid_i&&state!=COLLECT)error_o<=1;
   if(valid_i&&state==COLLECT)begin
    if(user_i)begin
     if(x!=0||y!=0)error_o<=1;
     frame_id<=source_frame_id;epoch<=config_epoch;cfg_flags<=flags;rx0<=roi_x0;ry0<=roi_y0;rx1<=roi_x1;ry1<=roi_y1;
     area<=(roi_x1-roi_x0)*(roi_y1-roi_y0);sum_v<=data_i[47:40];pixel_hash<={8'd0,data_i[23:0]};
     word_o<={source_frame_id,32'h43564d31};valid_o<=1;header<=1;
    end else begin sum_v<=sum_v+data_i[47:40];pixel_hash<={pixel_hash[26:0],pixel_hash[31:27]}^{8'd0,data_i[23:0]};end
    rgb_hold<=rgb_pixel;hs_acc[x[1:0]*16+:16]<={data_i[39:32],data_i[31:24]};mask_acc[x[3:0]*4+:4]<=data_i[51:48];
    if(x[1:0]==3)begin
     if(hs_pending)error_o<=1;
     hs_word<={data_i[39:32],data_i[31:24],hs_acc[47:0]};hs_pending<=1;hs_last<=x==WIDTH-1;
    end
    if(last_i)begin
     if(x!=WIDTH-1)error_o<=1;
     x<=0;line_final<=y==HEIGHT-1;y<=y==HEIGHT-1?0:y+1;
    end else begin if(x==WIDTH-1)error_o<=1;x<=x+1;end
   end
   if(header!=0)begin
    valid_o<=1;
    case(header)
     1:word_o<={{6'd0,ry0},{6'd0,rx0},H16,W16};
     2:word_o<={epoch,{6'd0,ry1},{6'd0,rx1}};
     3:word_o<={cfg_flags,32'h48533136};
     default:word_o<=0;
    endcase
    header<=header==3?0:header+1;
   end else if(hs_pending)begin
    word_o<=hs_word;valid_o<=1;hs_pending<=0;
    if(hs_last)begin state<=RGB;read_index<=0;end
   end
   if(state==RGB&&read_index<WIDTH/2)begin ram_valid<=1;ram_kind<=RGB;ram_last<=read_index==WIDTH/2-1;read_index<=read_index+1;end
   else if(state==MASK&&read_index<WIDTH/16)begin ram_valid<=1;ram_kind<=MASK;ram_last<=read_index==WIDTH/16-1;read_index<=read_index+1;end
   if(ram_valid)begin
    word_o<=ram_data;valid_o<=1;
    if(ram_last)begin
     read_index<=0;
     if(ram_kind==RGB)state<=MASK;
     else state<=line_final?FOOT0:COLLECT;
    end
   end
   if(state==FOOT0)begin word_o<={area,sum_v};valid_o<=1;state<=FOOT1;end
   else if(state==FOOT1)begin word_o<={frame_id,pixel_hash};valid_o<=1;state<=COLLECT;end
  end
 end
endmodule
