`timescale 1ns/1ps
// Six bounded slots in the already reserved DDR range. Never addresses Linux RAM.
module vision_compact_dma #(parameter WIDTH=480,HEIGHT=270,AW=11)(
 input wire ui_clk,ui_rst_n,enable,pixel_clk,pixel_rst_n,
 input wire[63:0]word_i,input wire valid_i,
 output wire[31:0]waddr,output wire[15:0]wsize,output wire wreq,
 output wire[63:0]wdata,output wire wready,input wire wbusy,wpop,
 output reg[31:0]completed,completed_id,output reg[2:0]completed_bank,
 output wire[31:0]errors,output wire active
);
 localparam FRAME_WORDS=WIDTH*13/16*HEIGHT+6;
 localparam[31:0]BASE=32'h3d800000,END=32'h3de00000;
 localparam CALC=0,WAIT=1,REQUEST=2,DRAIN=3;
 reg en1,en2,live;reg[1:0]state;
 always @(posedge ui_clk or negedge ui_rst_n)begin
  if(!ui_rst_n)begin en1<=0;en2<=0;live<=0;end
  else begin en1<=enable;en2<=en1;if(en2)live<=1;else if(!wbusy)live<=0;end
 end
 wire fifo_rst_n=ui_rst_n&&(en2||live);
 reg pe1,pe2;always @(posedge pixel_clk or negedge pixel_rst_n)begin
  if(!pixel_rst_n)begin pe1<=0;pe2<=0;end else begin pe1<=enable;pe2<=pe1;end
 end
 wire full,empty,fv;wire[AW:0]fc;wire[63:0]fd;
 reg[63:0]head,tail;reg[1:0]hc;
 wire prefetch=!empty&&({1'b0,hc}+fv<2);
 vision_async_fifo #(.AW(AW),.DW(64))fifo(.rst_n(fifo_rst_n),.wclk(pixel_clk),.rclk(ui_clk),.we(valid_i&&pe2),.di(word_i),.full(full),.re(prefetch),.dout(fd),.valid(fv),.empty(empty),.count(fc));
 reg overflow;always @(posedge pixel_clk or negedge fifo_rst_n)begin
  if(!fifo_rst_n)overflow<=0;else if(valid_i&&pe2&&full)overflow<=1;
 end
 reg ov1,ov2;reg[31:0]guard_error,transfer_error;
 reg[2:0]bank;reg[16:0]offset,advanced_offset;reg final_burst,address_safe;reg[31:0]prepared_address;reg[8:0]burst_size,beats;reg[2:0]settle;reg[AW:0]fc_reg;reg[AW+2:0]available;
 reg[31:0]frame_id;
 wire[31:0]slot_base=BASE+{9'd0,bank,20'd0};
 wire[31:0]address=prepared_address;
 wire[31:0]remaining=FRAME_WORDS-offset;
 wire[15:0]next_size=remaining>=256?16'd256:remaining[15:0];
 wire[32:0]end_address={1'b0,address}+{21'd0,burst_size,3'd0};
 wire guard=address>=BASE&&address[2:0]==0&&end_address<={1'b0,END}&&burst_size!=0&&burst_size<=256&&bank<6;
 assign waddr=address;assign wsize=burst_size;assign wdata=head;assign wready=hc!=0;
 assign wreq=state==REQUEST&&en2&&address_safe&&!ov2;assign active=live;
 assign errors={29'd0,transfer_error!=0,guard_error!=0,ov2};
 always @(posedge ui_clk or negedge ui_rst_n)begin
  if(!ui_rst_n)begin ov1<=0;ov2<=0;end else begin ov1<=overflow;ov2<=ov1;end
 end
 always @(posedge ui_clk or negedge fifo_rst_n)begin
  if(!fifo_rst_n)begin head<=0;tail<=0;hc<=0;state<=CALC;settle<=0;fc_reg<=0;available<=0;bank<=0;offset<=0;advanced_offset<=0;final_burst<=0;address_safe<=0;prepared_address<=BASE;burst_size<=0;beats<=0;frame_id<=0;completed<=0;completed_id<=0;completed_bank<=0;guard_error<=0;transfer_error<=0;end
  else begin
   fc_reg<=fc;available<={3'd0,fc_reg}+hc+fv;address_safe<=guard;
   case({fv,wpop})
    2'b10:begin if(hc==0)head<=fd;else tail<=fd;hc<=hc+1;end
    2'b01:begin head<=tail;hc<=hc-1;end
    2'b11:begin if(hc==1)head<=fd;else begin head<=tail;tail<=fd;end end
   endcase
   if(wpop)begin
    if(hc==0)transfer_error<=transfer_error+1;
    if(offset==0&&beats==0)begin frame_id<=head[63:32];if(head[31:0]!=32'h43564d31)transfer_error<=transfer_error+1;end
    beats<=beats+1;
   end
   case(state)
    CALC:begin prepared_address<=slot_base+{12'd0,offset,3'd0};burst_size<=next_size[8:0];advanced_offset<=offset+next_size[8:0];final_burst<=remaining<=256;beats<=0;settle<=0;state<=WAIT;end
    WAIT:begin if(settle<3)settle<=settle+1;else if(en2&&!ov2&&available>=burst_size)state<=REQUEST;end
    REQUEST:begin if(!address_safe)guard_error<=guard_error+1;if(wbusy)state<=DRAIN;end
    DRAIN:if(!wbusy)begin
     if(beats!=burst_size)transfer_error<=transfer_error+1;
     if(final_burst)begin
      completed<=completed+1;completed_id<=frame_id;completed_bank<=bank;bank<=bank==5?0:bank+1;offset<=0;
     end else offset<=advanced_offset;
     state<=CALC;
    end
   endcase
  end
 end
endmodule
