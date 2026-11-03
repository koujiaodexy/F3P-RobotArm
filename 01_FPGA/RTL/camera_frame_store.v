`timescale 1ns/1ps
// One frozen RAW8 frame in PL RAM. No DMA and no writes into Linux memory.
// Keep a 2x2 Bayer block from each 6x6 source block: 1920x1080 -> 640x360.
module camera_frame_store #(
 parameter SOURCE_WIDTH=1920,parameter SOURCE_HEIGHT=1080,
 parameter WORDS=(SOURCE_WIDTH/3)*(SOURCE_HEIGHT/3)/4
)(
 input wire pixel_clk,bus_clk,rst_n,enable_i,
 input wire valid_i,user_i,last_i,input wire [39:0] raw_i,
 input wire [31:0] request_i,page_i,input wire [4:0] page_word_i,
 output wire [31:0] page_data_o,output reg [31:0] page_ack_o,
 output wire [31:0] done_o,words_o,frames_o,debug_o,
 output wire ready_o,busy_o,error_o,page_busy_o
);
 reg [31:0] memory[0:WORDS-1];
 reg write_enable;reg [15:0] write_address;reg [31:0] write_data;
 // Pipeline the RAM write so sensor-valid decoding does not fan out to every RAM bank.
 always @(posedge pixel_clk)if(write_enable)memory[write_address]<=write_data;
 reg en1,en2;reg [31:0] req1,req2,seen,active_seq,done;
 reg armed,running,ready,error;
 reg [15:0] pointer;reg [15:0] pair;
 reg [10:0] groups,row;reg [1:0] phase;reg [2:0] row_phase;
 reg [31:0] frames;
 wire [7:0] p0=raw_i[9:2],p1=raw_i[19:12],p2=raw_i[29:22],p3=raw_i[39:32];
 always @(posedge pixel_clk or negedge rst_n)begin
  if(!rst_n)begin
   en1<=0;en2<=0;req1<=0;req2<=0;seen<=0;active_seq<=0;done<=0;
   armed<=0;running<=0;ready<=0;error<=0;pointer<=0;pair<=0;groups<=0;row<=0;phase<=0;row_phase<=0;frames<=0;
   write_enable<=0;write_address<=0;write_data<=0;
  end else begin
   write_enable<=0;
   en1<=enable_i;en2<=en1;req1<=request_i;req2<=req1;
   if(valid_i&&user_i)frames<=frames+1;
   if(!en2)begin armed<=0;running<=0;ready<=0;error<=0;seen<=req2;end
   else if(req2!=seen)begin
    seen<=req2;active_seq<=req2;armed<=1;running<=0;ready<=0;error<=0;pointer<=0;
   end else if(armed&&valid_i&&user_i)begin
    armed<=0;running<=1;row<=0;row_phase<=0;groups<=1;phase<=1;pair<={p1,p0};pointer<=0;
   end else if(running&&valid_i)begin
    if(user_i)begin running<=0;error<=1;done<=active_seq;end
    else if(groups>=SOURCE_WIDTH/4)begin running<=0;error<=1;done<=active_seq;end
    else begin
     if(row_phase<2)begin
      if(phase==0)pair<={p1,p0};
      else if(phase==1)begin
       if(pointer<WORDS)begin write_enable<=1;write_address<=pointer;write_data<={p3,p2,pair};pointer<=pointer+1;end
       else begin running<=0;error<=1;done<=active_seq;end
      end
     end
     phase<=phase==2?0:phase+1;groups<=groups+1;
     if(last_i)begin
      if(groups!=SOURCE_WIDTH/4-1)begin running<=0;error<=1;done<=active_seq;end
      else if(row==SOURCE_HEIGHT-1)begin
       running<=0;done<=active_seq;
       if(pointer==WORDS)ready<=1;else error<=1;
      end else begin
       groups<=0;phase<=0;row<=row+1;row_phase<=row_phase==5?0:row_phase+1;
      end
     end
    end
   end
  end
 end
 // Held payload remains stable from completion until the next request.
 reg ready1,ready2,busy1,busy2,error1,error2;
 reg [31:0] done1,done2,frames1,frames2;
 reg [15:0] pointer1,pointer2;reg [31:0] debug1,debug2;
 function [31:0] ungray;input[31:0] v;integer k;begin ungray[31]=v[31];for(k=30;k>=0;k=k-1)ungray[k]=ungray[k+1]^v[k];end endfunction
 wire [31:0] frames_gray=(frames>>1)^frames;
 assign ready_o=ready2&&(done2==request_i)&&enable_i;
 assign busy_o=busy2;assign error_o=error2&&(done2==request_i);
 assign done_o=done2;assign words_o={16'd0,pointer2};assign frames_o=ungray(frames2);assign debug_o=debug2;
 reg [31:0] cache[0:31];reg loading,load_phase;
 reg [4:0] load_index;reg [31:0] load_token,seen_request;
 reg [15:0] read_base;wire [15:0] read_address=read_base+load_index;
 reg [31:0] read_data;
 always @(posedge bus_clk)if(read_address<WORDS)read_data<=memory[read_address];
 assign page_data_o=cache[page_word_i];assign page_busy_o=loading;
 always @(posedge bus_clk or negedge rst_n)begin
  if(!rst_n)begin
   ready1<=0;ready2<=0;busy1<=0;busy2<=0;error1<=0;error2<=0;done1<=0;done2<=0;
   frames1<=0;frames2<=0;pointer1<=0;pointer2<=0;debug1<=0;debug2<=0;
   loading<=0;load_phase<=0;load_index<=0;load_token<=0;seen_request<=0;read_base<=0;page_ack_o<=32'hffffffff;
  end else begin
   ready1<=ready;ready2<=ready1;busy1<=armed||running;busy2<=busy1;error1<=error;error2<=error1;
   done1<=done;done2<=done1;frames1<=frames_gray;frames2<=frames1;pointer1<=pointer;pointer2<=pointer1;
   debug1<={5'd0,row,row_phase,phase,groups};debug2<=debug1;
   if(!enable_i||request_i!=seen_request)begin
    seen_request<=request_i;loading<=0;page_ack_o<=32'hffffffff;
   end else if(!ready_o)begin loading<=0;page_ack_o<=32'hffffffff;end
   else if(loading)begin
    if(!load_phase)load_phase<=1;
    else begin
     cache[load_index]<=read_data;load_phase<=0;
     if(load_index==31)begin page_ack_o<=load_token;loading<=0;end
     else load_index<=load_index+1;
    end
   end else if(page_i!=page_ack_o&&page_i[10:0]<(WORDS+31)/32)begin
    load_token<=page_i;read_base<={page_i[10:0],5'd0};load_index<=0;load_phase<=0;loading<=1;
   end
  end
 end
endmodule
