
/*******************************MILIANKE*******************************
*Company : MiLianKe Electronic Technology Co., Ltd.
*WebSite:https://www.milianke.com
*TechWeb:https://www.uisrc.com
*tmall-shop:https://milianke.tmall.com
*jd-shop:https://milianke.jd.com
*taobao-shop1: https://milianke.taobao.com
*Create Date: 2023/03/23
*Module Name:
*File Name:
*Description: 
*The reference demo provided by Milianke is only used for learning. 
*We cannot ensure that the demo itself is free of bugs, so users 
*should be responsible for the technical problems and consequences
*caused by the use of their own products.
*Copyright: Copyright (c) MiLianKe
*All rights reserved.
*Revision: 4.2
*Signal description
*1) I_ input
*2) O_ output
*3) IO_ input output
*4) S_ system internal signal
*5) _n activ low
*6) _dg debug signal 
*7) _r delay or register
*8) _s state mechine
*********************************************************************/

/*********uiFDMA_abd5ac4467e0(AXI-FAST DMA Controller)基于AXI总线的自定义内存控制器***********
--1.代码简洁，占用极少逻辑资源，代码结构清晰，逻辑设计严谨，读写对称
--2.fdma控制信号，简化了AXI总线的控制，根据I_fdma_wsize和I_fdma_rsize可以自动完成AXI总线的控制，完成数据的搬运
--3版本号说明
--1.0 初次发布
--2.0 修改型号定义，解决1.0版本中，last信号必须连续前一个valid的bug
--3.0 修改,AXI-burst最大burst 256
--3.1 修改可以设置AXI burst长度
--3.2 解决3.1版本中，当总的burst长度是奇数的时候出现错误，修改端口命名规则，设置I代表了输入信号，O代表了输出信号
--3.3 读通道增加背靠背burst机制
--4.0 简单优化
--4.1 简单优化
--4.2 增加复位，解决启动后再次复位问题部分信号不能有效初始化
*********************************************************************/
`timescale 1ns / 1ns

module uiFDMA_abd5ac4467e0#
(
parameter  integer         M_AXI_B2B_SET			= 3		    , //读通道背靠背多次连续burst
parameter  integer         M_AXI_ID_WIDTH			= 6		, //ID,demo中没用到
parameter  integer         M_AXI_ID			        = 0		    , //ID,demo中没用到
parameter  integer         M_AXI_ADDR_WIDTH			= 32		, //内存地址位宽
parameter  integer         M_AXI_DATA_WIDTH			= 64		, //AXI总线的数据位宽
parameter  integer		   M_AXI_MAX_BURST_LEN      = 16          //AXI总线的burst 大小，对于AXI4，支持任意长度，对于AXI3以下最大16
)
(
input   wire [M_AXI_ADDR_WIDTH-1 : 0]      I_fdma_waddr          ,//FDMA写通道地址
input                                      I_fdma_wareq          ,//FDMA写通道请求
input   wire [15 : 0]                      I_fdma_wsize          ,//FDMA写通道一次FDMA的传输大小                                            
output                                     O_fdma_wbusy          ,//FDMA处于BUSY状态，AXI总线正在写操作  
				
input   wire [M_AXI_DATA_WIDTH-1 :0]       I_fdma_wdata		     ,//FDMA写数据
output  wire                               O_fdma_wvalid         ,//FDMA写有效
input	wire                               I_fdma_wready		 ,//FDMA写准备好，用户可以写数据

input   wire [M_AXI_ADDR_WIDTH-1 : 0]      I_fdma_raddr          ,// FDMA读通道地址
input                                      I_fdma_rareq          ,// FDMA读通道请求
input   wire [15 : 0]                      I_fdma_rsize          ,// FDMA读通道一次FDMA的传输大小                                      
output                                     O_fdma_rbusy          ,// FDMA处于BUSY状态，AXI总线正在读操作 
				
output  wire [M_AXI_DATA_WIDTH-1 :0]       O_fdma_rdata		     ,// FDMA读数据
output  wire                               O_fdma_rvalid         ,// FDMA 读有效
input	wire                               I_fdma_rready		 ,// FDMA读准备好，用户可以读数据

//以下为AXI总线信号		
input 	wire  								M_AXI_ACLK			,
input 	wire  								M_AXI_ARESETN		,
output 	wire [M_AXI_ID_WIDTH-1 : 0]		    M_AXI_AWID			,
output 	wire [M_AXI_ADDR_WIDTH-1 : 0] 	    M_AXI_AWADDR		,
output 	wire [7 : 0]						M_AXI_AWLEN			,
output 	wire [2 : 0] 						M_AXI_AWSIZE		,
output 	wire [1 : 0] 						M_AXI_AWBURST		,
output 	wire  								M_AXI_AWLOCK		,
output 	wire [3 : 0] 						M_AXI_AWCACHE		,
output 	wire [2 : 0] 						M_AXI_AWPROT		,  
output 	wire [3 : 0] 						M_AXI_AWQOS			,
output 	wire  								M_AXI_AWVALID		,
input	wire  								M_AXI_AWREADY		,
output  wire [M_AXI_ID_WIDTH-1 : 0] 		M_AXI_WID			,
output  wire [M_AXI_DATA_WIDTH-1 : 0] 	    M_AXI_WDATA			,
output  wire [M_AXI_DATA_WIDTH/8-1 : 0] 	M_AXI_WSTRB			,
output  wire  								M_AXI_WLAST			, 			
output  wire  								M_AXI_WVALID		,
input   wire  								M_AXI_WREADY		,
input   wire [M_AXI_ID_WIDTH-1 : 0] 		M_AXI_BID			,
input   wire [1 : 0] 						M_AXI_BRESP			,
input   wire  								M_AXI_BVALID		,
output  wire  								M_AXI_BREADY		, 
output  wire [M_AXI_ID_WIDTH-1 : 0] 		M_AXI_ARID			,	 

output  wire [M_AXI_ADDR_WIDTH-1 : 0] 	    M_AXI_ARADDR		,	 	
output  wire [7 : 0] 						M_AXI_ARLEN			,	 
output  wire [2 : 0] 						M_AXI_ARSIZE		,	 
output  wire [1 : 0] 						M_AXI_ARBURST		,	 
output  wire  								M_AXI_ARLOCK		,	 
output  wire [3 : 0] 						M_AXI_ARCACHE		,	 
output  wire [2 : 0] 						M_AXI_ARPROT		,	 
output  wire [3 : 0] 						M_AXI_ARQOS			,	 	   
output  wire  								M_AXI_ARVALID		,	 
input   wire  								M_AXI_ARREADY		,	 
input   wire [M_AXI_ID_WIDTH-1 : 0] 		M_AXI_RID			,	 
input   wire [M_AXI_DATA_WIDTH-1 : 0] 	    M_AXI_RDATA			,	 
input   wire [1 : 0] 						M_AXI_RRESP			,	 
input   wire  								M_AXI_RLAST			,	 
input   wire  								M_AXI_RVALID		,    
output  wire  								M_AXI_RREADY				
	);

//计算数据位宽
function integer clogb2 (input integer bit_depth);              
begin                                                        
	    for(clogb2=0; bit_depth>0; clogb2=clogb2+1)                   
	        bit_depth = bit_depth >> 1;                               
end                                                           
endfunction 

localparam AXI_BYTES =  M_AXI_DATA_WIDTH/8;
localparam [3:0] MAX_BURST_LEN_SIZE = clogb2(M_AXI_MAX_BURST_LEN)  -1;         
                                                    
// Camera write channel. Address, data and response are separate AXI channels.
// Keep AW and W payload stable under backpressure and drain every B response.
localparam integer WRITE_CREDITS=(M_AXI_B2B_SET<1)?1:((M_AXI_B2B_SET>15)?15:M_AXI_B2B_SET);
reg write_active;
reg [M_AXI_ADDR_WIDTH-1:0] write_address,write_data_address;
reg [15:0] write_unissued,write_data_unstarted;
reg [8:0] write_position;
reg [4:0] write_outstanding,write_data_bursts;
wire [15:0] write_page_words=(13'd4096-{1'b0,write_address[11:0]}) >> clogb2(AXI_BYTES-1);
wire [15:0] write_max_words=(write_unissued>=M_AXI_MAX_BURST_LEN)?M_AXI_MAX_BURST_LEN:write_unissued;
wire [15:0] write_burst_words=(write_max_words>write_page_words)?write_page_words:write_max_words;
wire [15:0] data_page_words=(13'd4096-{1'b0,write_data_address[11:0]}) >> clogb2(AXI_BYTES-1);
wire [15:0] data_max_words=(write_data_unstarted>=M_AXI_MAX_BURST_LEN)?M_AXI_MAX_BURST_LEN:write_data_unstarted;
wire [15:0] data_burst_words=(data_max_words>data_page_words)?data_page_words:data_max_words;
assign M_AXI_AWID=M_AXI_ID;
assign M_AXI_AWADDR=write_address;
assign M_AXI_AWLEN=write_burst_words[7:0]-8'd1;
assign M_AXI_AWSIZE=clogb2(AXI_BYTES-1);
assign M_AXI_AWBURST=2'b01;
assign M_AXI_AWLOCK=1'b0;
assign M_AXI_AWCACHE=4'b0010;
assign M_AXI_AWPROT=3'd0;
assign M_AXI_AWQOS=4'd0;
assign M_AXI_AWVALID=write_active&&(write_unissued!=0)&&(write_outstanding<WRITE_CREDITS);
assign M_AXI_WDATA=I_fdma_wdata;
assign M_AXI_WSTRB={AXI_BYTES{1'b1}};
assign M_AXI_WVALID=write_active&&(write_data_bursts!=0)&&I_fdma_wready;
// Register WLAST before presenting it to the hard PS AXI port.
reg write_last;
reg[8:0]data_current_words;
function[8:0]words_for;
 input[15:0]words;input[11:0]low_address;reg[15:0]page,maximum;
 begin page=(13'd4096-{1'b0,low_address}) >> clogb2(AXI_BYTES-1);
 maximum=words>=M_AXI_MAX_BURST_LEN?M_AXI_MAX_BURST_LEN:words;
 words_for=maximum>page?page:maximum;end
endfunction
wire[8:0]following_words=words_for(write_data_unstarted-data_current_words,write_data_address[11:0]+data_current_words*AXI_BYTES);
assign M_AXI_WLAST=write_last;
assign M_AXI_BREADY=write_active;
wire write_address_accepted=M_AXI_AWVALID&&M_AXI_AWREADY;
wire write_data_accepted=M_AXI_WVALID&&M_AXI_WREADY;
wire write_data_last=write_data_accepted&&M_AXI_WLAST;
wire write_response_accepted=M_AXI_BVALID&&M_AXI_BREADY;
assign O_fdma_wbusy=write_active;
assign O_fdma_wvalid=write_data_accepted;
always @(posedge M_AXI_ACLK)begin
 if(!M_AXI_ARESETN)begin
  write_last<=0;data_current_words<=0;write_active<=0;write_address<=0;write_data_address<=0;
  write_unissued<=0;write_data_unstarted<=0;write_position<=0;
  write_outstanding<=0;write_data_bursts<=0;
 end else if(!write_active&&I_fdma_wareq&&(I_fdma_wsize!=0))begin
  write_last<=words_for(I_fdma_wsize,I_fdma_waddr[11:0])==1;data_current_words<=words_for(I_fdma_wsize,I_fdma_waddr[11:0]);
  write_active<=1;write_address<=I_fdma_waddr;write_data_address<=I_fdma_waddr;
  write_unissued<=I_fdma_wsize;write_data_unstarted<=I_fdma_wsize;
  write_position<=0;write_outstanding<=0;write_data_bursts<=0;
 end else begin
  if(write_address_accepted)begin
   write_address<=write_address+write_burst_words*AXI_BYTES;
   write_unissued<=write_unissued-write_burst_words;
  end
  case({write_address_accepted,write_response_accepted})
   2'b10:write_outstanding<=write_outstanding+1;
   2'b01:write_outstanding<=write_outstanding-1;
  endcase
  case({write_address_accepted,write_data_last})
   2'b10:write_data_bursts<=write_data_bursts+1;
   2'b01:write_data_bursts<=write_data_bursts-1;
  endcase
  if(write_data_accepted)begin
   if(M_AXI_WLAST)begin
    write_position<=0;write_last<=following_words==1;data_current_words<=following_words;
    write_data_address<=write_data_address+data_current_words*AXI_BYTES;
    write_data_unstarted<=write_data_unstarted-data_current_words;
   end else begin write_position<=write_position+1;write_last<=write_position==data_current_words-2;end
  end
  if(write_active&&write_unissued==0&&write_data_unstarted==0&&write_outstanding==0)write_active<=0;
 end
end

// Camera read channel: keep accepted bursts in flight across DDR latency.
// ARVALID and its payload remain stable until ARREADY accepts the address.
// Credits are returned only by an accepted AXI RLAST, never by elapsed cycles.
localparam integer READ_CREDITS=(M_AXI_B2B_SET<1)?1:((M_AXI_B2B_SET>15)?15:M_AXI_B2B_SET);
reg read_active;
reg [M_AXI_ADDR_WIDTH-1:0] read_address;
reg [15:0] read_unissued,read_remaining;
reg [4:0] read_outstanding;
wire [15:0] page_words=(13'd4096-{1'b0,read_address[11:0]}) >> clogb2(AXI_BYTES-1);
wire [15:0] max_words=(read_unissued>=M_AXI_MAX_BURST_LEN)?M_AXI_MAX_BURST_LEN:read_unissued;
wire [15:0] read_burst_words=(max_words>page_words)?page_words:max_words;
assign M_AXI_ARID=M_AXI_ID;
assign M_AXI_ARADDR=read_address;
assign M_AXI_ARLEN=read_burst_words[7:0]-8'd1;
assign M_AXI_ARSIZE=clogb2(AXI_BYTES-1);
assign M_AXI_ARBURST=2'b01;
assign M_AXI_ARLOCK=1'b0;
assign M_AXI_ARCACHE=4'b0010;
assign M_AXI_ARPROT=3'd0;
assign M_AXI_ARQOS=4'd0;
assign M_AXI_ARVALID=read_active&&(read_unissued!=0)&&(read_outstanding<READ_CREDITS);
assign M_AXI_RREADY=I_fdma_rready&&read_active;
wire read_address_accepted=M_AXI_ARVALID&&M_AXI_ARREADY;
wire read_data_accepted=M_AXI_RVALID&&M_AXI_RREADY;
wire read_response_last=read_data_accepted&&M_AXI_RLAST;
assign O_fdma_rbusy=read_active;
assign O_fdma_rdata=M_AXI_RDATA;
assign O_fdma_rvalid=read_data_accepted;
always @(posedge M_AXI_ACLK)begin
 if(!M_AXI_ARESETN)begin
  read_active<=0;read_address<=0;read_unissued<=0;read_remaining<=0;read_outstanding<=0;
 end else if(!read_active&&I_fdma_rareq&&(I_fdma_rsize!=0))begin
  read_active<=1;read_address<=I_fdma_raddr;
  read_unissued<=I_fdma_rsize;read_remaining<=I_fdma_rsize;read_outstanding<=0;
 end else begin
  if(read_address_accepted)begin
   read_address<=read_address+read_burst_words*AXI_BYTES;
   read_unissued<=read_unissued-read_burst_words;
  end
  case({read_address_accepted,read_response_last})
   2'b10:read_outstanding<=read_outstanding+1;
   2'b01:read_outstanding<=read_outstanding-1;
  endcase
  if(read_data_accepted)begin
   read_remaining<=read_remaining-1;
   if(read_remaining==1)read_active<=0;
  end
 end
end
endmodule
