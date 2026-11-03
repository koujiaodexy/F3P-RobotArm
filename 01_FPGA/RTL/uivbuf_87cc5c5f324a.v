
/*******************************MILIANKE*******************************
*Company : MiLianKe Electronic Technology Co., Ltd.
*WebSite:https://www.milianke.com
*TechWeb:https://www.uisrc.com
*tmall-shop:https://milianke.tmall.com
*jd-shop:https://milianke.jd.com
*taobao-shop1: https://milianke.taobao.com
*Create Date: 2021/10/15
*File Name: uivbuf_87cc5c5f324a.v
*Description: 
*Declaration:
*The reference demo provided by Milianke is only used for learning. 
*We cannot ensure that the demo itself is free of bugs, so users 
*should be responsible for the technical problems and consequences
*caused by the use of their own products.
*Copyright: Copyright (c) MiLianKe
*All rights reserved.
*Revision: 
*--1.0 20250812

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

/*********uidbuf(fdma data buffer controller)锟斤拷锟斤拷FDMA锟脚猴拷时锟斤拷锟侥伙拷锟斤拷锟斤拷锟斤拷锟斤拷***********
--锟芥本锟斤拷3.1
--锟斤拷锟斤拷锟斤拷锟斤拷锟斤拷锟斤拷锟斤拷锟狡碉拷uivbuf_87cc5c5f324a(vdma buffer controller)锟斤拷锟斤拷FDMA锟脚猴拷时锟斤拷锟侥伙拷锟斤拷锟斤拷锟斤拷锟斤拷

*********************************************************************/

module uivbuf_87cc5c5f324a#(
parameter  integer                        AXI_DATA_WIDTH = 64,  //AXI总线数据位宽

parameter  integer                        W_BUFDEPTH     = 2048, //写通道AXI设置FIFO缓存大小
parameter  integer                        W_DATAWIDTH    = 32,   //写通道AXI设置数据位宽大小
parameter  integer                        W_XSIZE        = 1920, //写通道设置X方向的数据大小，代表了每次FDMA 传输的数据长度
parameter  integer                        W_YSIZE        = 1080, //写通道设置Y方向值，代表了进行了多少次XSIZE传输
parameter  integer                        W_XDIV         = 1,    //写通道对X方向数据拆分为XDIV次传输，减少FIFO的使用

parameter  integer                        R_BUFDEPTH     = 2048, //读通道AXI设置FIFO缓存大小
parameter  integer                        R_DATAWIDTH    = 32,   //读通道AXI设置数据位宽大小
parameter  integer                        R_XSIZE        = 1920, //读通道设置X方向的数据大小，代表了每次FDMA 传输的数据长度
parameter  integer                        R_YSIZE        = 1080, //读通道设置Y方向值，代表了进行了多少次XSIZE传输
parameter  integer                        R_XDIV         = 1     //读通道对X方向数据拆分为XDIV次传输，减少FIFO的使用 
) 
(
input     wire                            I_ui_clk      ,  
input     wire                            I_ui_rstn     ,  
// -W_FIFO--------------
input     wire                            I_W_sync      ,
input     wire                            I_W_wclk      , 
input     wire                            I_W_tuser     ,  
input     wire                            I_W_tvalid    ,  
input     wire [W_DATAWIDTH -1 : 0]       I_W_tdata     ,  
input     wire                            I_W_tlast     ,
output    wire                            O_W_tready    ,
output    wire                            O_W_tlocked ,

output    wire                            O_s2mm_tuser  ,
output    wire                            O_s2mm_tvalid ,
output    wire [AXI_DATA_WIDTH -1: 0]     O_s2mm_tdata  ,
input     wire                            I_s2mm_tready ,
output    wire                            O_s2mm_tlast  ,
// -R_FIFO--------------
input     wire                            I_R_sync      ,
input     wire                            I_R_rclk      ,  
input     wire                            I_R_tready    ,  
output    wire                            O_R_tuser     ,
output    wire                            O_R_tvalid    ,
output    wire [R_DATAWIDTH- 1 : 0]       O_R_tdata     ,  
output    wire                            O_R_tlast     ,
output    reg                             O_R_tlocked   ,

input     wire                            I_mm2s_tuser  , 
input     wire                            I_mm2s_tvalid ,
input     wire [AXI_DATA_WIDTH -1: 0]     I_mm2s_tdata  ,
output    wire                            O_mm2s_tready ,
input     wire                            I_mm2s_tlast   

);

// 计算Log2
function integer clog2;
  input integer value;
  begin
    for (clog2 = 0; value > 0; clog2 = clog2 + 1) value = value >> 1;
  end
endfunction

//FDMA读写状态机的状态值，一般4个状态值即可 
localparam      S_IDLE            = 2'd0;
localparam      S_RST             = 2'd1;
localparam      S_DATA1           = 2'd2;
localparam      S_DATA2           = 2'd3;

localparam      WFIFO_DEPTH           = W_BUFDEPTH/W_XDIV;  //写通道FIFO深度
localparam      W_WR_DATA_COUNT_WIDTH = clog2(WFIFO_DEPTH);  //计算FIFO的写通道位宽
localparam      W_RD_DATA_COUNT_WIDTH = clog2(
                           WFIFO_DEPTH * W_DATAWIDTH / AXI_DATA_WIDTH
                ); 

localparam      VDMA_WX_BURST     = (W_XSIZE*W_DATAWIDTH/AXI_DATA_WIDTH)/W_XDIV; //FDMA BURST 一次的大小

reg [1 : 0]     W_MS              = 0;
reg             W_REQ             = 0 ;
reg [8 : 0]     wrst_cnt          = 0;

wire            W_empty;
reg             W_empty_r1,W_empty_r2,W_empty_r3;
reg [15 :0]     w_xcnt            = 0;
reg [15 :0]     w_ycnt            = 0;
reg [15 :0]     s2m_xcnt          = 0;
reg [15 :0]     s2m_ycnt          = 0;
reg             wfifo_rst_done    = 0;
reg             wfifo_rst_lock    = 0;

reg             s2m_ready_r1,s2m_ready_r2;
always @(posedge I_W_wclk) begin
                s2m_ready_r1      <= I_s2mm_tready;
                s2m_ready_r2      <= s2m_ready_r1;
end

reg             W_sync_r1,W_sync_r2, W_sync_r3;

always @(posedge I_ui_clk) begin
                W_sync_r1       <= I_W_sync;
                W_sync_r2       <= W_sync_r1;
                W_sync_r3       <= W_sync_r2 | W_sync_r1 |  I_W_sync;        
end 

//FIFO ?同步复位计数器
always @(posedge I_W_wclk or negedge I_ui_rstn) begin
  if (~I_ui_rstn) begin
                wrst_cnt          <= 0;
                wfifo_rst_done    <= 0;
                wfifo_rst_lock    <= 0;
  end else if (I_W_tuser & (W_empty == 1'b0)) begin //同步丢失，复位FIFO 重新同步
                wfifo_rst_lock    <= 1;
                wfifo_rst_done    <= 0;
                wrst_cnt          <= 0;
  end else if (wfifo_rst_lock & (wrst_cnt[8] == 0))  //对FIFO复位
                wrst_cnt          <= wrst_cnt + 1'b1;
  else if(W_MS == S_IDLE & s2m_ready_r2 & I_W_tuser)begin  //FIFO复位完成，或者第一次等待s2m_ready_r2=1 设置wfifo_rst_done；
                wrst_cnt          <= 0;
                wfifo_rst_done    <= 1;
                wfifo_rst_lock    <= 0;
  end
end

//帧同步，对于视频有效
reg             wfifo_rst_done_r1 = 1'b0, wfifo_rst_done_r2 = 1'b0, wfifo_rst_done_r3 = 1'b0;
always @(posedge I_ui_clk) begin
                wfifo_rst_done_r1   <= wfifo_rst_done;
                wfifo_rst_done_r2   <= wfifo_rst_done_r1;
end

//延迟1拍，同时对
reg             W_tuser_r3,W_tuser_r2, W_tuser_r1;
reg             W_tvalid_r1;
reg             W_tlast_r1,W_tlast_r2;
reg [W_DATAWIDTH -1 : 0]       W_tdata_r1;
always @(posedge I_W_wclk) begin
                W_tuser_r1      <= I_W_tuser;
                W_tuser_r2      <= W_tuser_r1;
                W_tlast_r1      <= I_W_tlast;
                W_tlast_r2      <= W_tlast_r1;

                W_tvalid_r1     <= I_W_tvalid;
                W_tdata_r1      <= I_W_tdata;          
               
                W_tuser_r3      <= W_tuser_r2|W_tuser_r1|I_W_tuser;
end  

//计算XSIZE，本代码用于调试时候debug使用 
always @(posedge I_W_wclk ) begin
  if(wfifo_rst_done == 0)                   
                w_xcnt            <= 0;
  else if({W_tuser_r2, W_tuser_r1} == 2'b01)  
                w_xcnt            <= 0;
  else if({W_tlast_r2 & W_tlast_r1} == 2'b01)           
                w_xcnt            <= 0;
  else if(W_tvalid_r1)                       
                w_xcnt            <= w_xcnt + 1'b1;
end

always @(posedge I_W_wclk ) begin
  if(wfifo_rst_done == 0)                   
                w_ycnt            <= 0;
  else if (~W_tlast_r2 & W_tlast_r1 ) begin //同步I_W_tlast计数同步
    if (w_ycnt == W_YSIZE - 1)              
                w_ycnt            <= 0;
    else                                    
                w_ycnt            <= w_ycnt + 1'b1;  //?帧计数器
  end
end

//写状态机帧同步
reg             wfs_r1,wfs_r2,wfs_r3,wfs_r4;
always @(posedge I_ui_clk) begin
                wfs_r1            <= W_tuser_r3;
                wfs_r2            <= wfs_r1;
                wfs_r3            <= wfs_r2;
                wfs_r4            <= wfs_r3;
end

wire            w_fs;
assign          w_fs              = {wfs_r4,wfs_r3} == 2'b10 ? 1 : 0;

assign          O_s2mm_tlast      = (s2m_xcnt == VDMA_WX_BURST - 1'b1) & O_s2mm_tvalid; //产生tlast
wire            s2m_end           = O_s2mm_tlast & (s2m_ycnt == W_YSIZE - 1'b1); //结束本次传输

reg s2mm_tvalid_en;
//写通道状态机，采用4个状态值描述
always @(posedge I_ui_clk or negedge I_ui_rstn) begin
  if (!I_ui_rstn) begin
                W_MS              <= S_IDLE;
                s2mm_tvalid_en    <= 1'b0;
  end 
  else begin
    case (W_MS)
      S_IDLE: begin
                s2mm_tvalid_en    <= 1'b0;
                W_MS              <= (W_sync_r3 & wfifo_rst_done_r1) ? S_RST : W_MS; //帧同步，其中I_W_sync用于具有vs同步的情况，或者设置1，w_fs使用tuser同步，只有当FIFO为空的情况才会传输，如果FIFO满，说明帧间隔太小，或者出错
      end
      S_RST:begin//帧同步，对于非视频数据直接跳过,对于视频数据，会同步每一帧，并且复位数据FIFO
                W_MS              <=  w_fs  ?  S_DATA1 : W_MS;
      end
      S_DATA1: begin  //发送写WDMA请求,或者W通道失去锁的情况，一直写直到本帧写结束
                W_MS              <= W_REQ ? S_DATA2 : S_DATA1;
      end
      S_DATA2: begin  //写有效数据
        if(O_s2mm_tlast) begin
                s2mm_tvalid_en    <= 1'b0;
          if(s2m_end) 
                W_MS              <= S_IDLE;
          else 
                W_MS              <= S_DATA1;  
        end
        else begin
                s2mm_tvalid_en    <= 1'b1;
                W_MS              <= W_MS;
        end
      end
      default:  W_MS              <= S_IDLE;
      endcase
  end
end

assign O_s2mm_tvalid = s2mm_tvalid_en & I_s2mm_tready & O_R_tlocked;
//计算s2m_xsize 计算s2m_ysize
always @(posedge I_ui_clk or negedge I_ui_rstn) begin
  if (~I_ui_rstn) begin
                s2m_xcnt          <= 0;  
                s2m_ycnt          <= 0;
  end
  else if(W_MS == S_DATA2 )begin
    if(O_s2mm_tvalid)
        if(s2m_xcnt == VDMA_WX_BURST - 1'b1)  begin 
                s2m_xcnt          <= 0;  
                s2m_ycnt          <= s2m_ycnt + 1'b1; 
        end
        else  
                s2m_xcnt          <= s2m_xcnt + 1'b1;
    else 
                s2m_xcnt          <= s2m_xcnt;
  end
  else if(W_MS == S_IDLE) begin  
                s2m_xcnt          <= 0;  
                s2m_ycnt          <= 0;
  end
end

reg tuser_r1,tuser_r2;
always @(posedge I_ui_clk ) begin
                tuser_r1          <= O_s2mm_tvalid;
end

reg s2m_tuser_locked;
always @(posedge I_ui_clk ) begin
  if(O_s2mm_tuser)  
                s2m_tuser_locked  <= 1'b1;
  else if(W_MS == S_IDLE )
                s2m_tuser_locked  <= 1'b0;
end

assign          O_s2mm_tuser      = O_s2mm_tvalid & (tuser_r1== 1'b0) & (s2m_tuser_locked == 1'b0);

  //读通道的数据FIFO，采用了原语调用xpm_fifo_async fifo，当FIFO存储空间有足够空余，满足一次FDMA的burst即可发出请求
wire [W_RD_DATA_COUNT_WIDTH - 1'b1 :0]  W_rcnt;

always @(posedge I_ui_clk) 
                W_REQ             <= (W_rcnt >= VDMA_WX_BURST - 1) | (wfifo_rst_done == 1'b0);//当FIFO reset阶段，当W_MS状态机正在有数据发送需要等待发送完成
    
wire            W_full_pro;
wire            O_W_full;
assign          O_W_tready        = 1'b1;

wire            wfifo_wen         =  I_W_tvalid & wfifo_rst_done;
wire            wfifo_rst         = (wrst_cnt >10) & (wrst_cnt <80) ;//帧同步期间，复位40个I_W_wclk的周期

assign          O_W_tlocked       = wfifo_rst_done;

sfifo_87cc5c5f324a #(
.DATA_WIDTH_W(W_DATAWIDTH),
.DATA_WIDTH_R(AXI_DATA_WIDTH),
.ADDR_WIDTH_W(W_WR_DATA_COUNT_WIDTH),
.ADDR_WIDTH_R(W_RD_DATA_COUNT_WIDTH),
.SHOW_AHEAD_EN(1),
.OUTREG_EN("NOREG")
) wdbuf_fifo (
.rst            ((I_ui_rstn == 1'b0) | wfifo_rst ),
.clkw           (I_W_wclk                        ),
.we             (wfifo_wen                       ),
.di             (I_W_tdata                       ),
.full_flag      (O_W_full                        ),
.afull          (W_full_pro                      ),
.clkr           (I_ui_clk                        ),
.re             (O_s2mm_tvalid                   ),
.dout           (O_s2mm_tdata                    ),
.empty_flag     (W_empty                         ),
.rdusedw        (W_rcnt                          )
);

localparam      VDMA_RX_BURST          = (R_XSIZE*R_DATAWIDTH/AXI_DATA_WIDTH)/R_XDIV; //FDMA BURST 一次的大小
localparam      RFIFO_DEPTH            = (R_BUFDEPTH*R_DATAWIDTH/AXI_DATA_WIDTH)/R_XDIV;//R_BUFDEPTH/(V_DATA_WIDTH/R_DATAWIDTH);
localparam      R_WR_DATA_COUNT_WIDTH  = clog2(RFIFO_DEPTH);  //FIFO数据位宽计算
localparam      R_RD_DATA_COUNT_WIDTH  = clog2(R_BUFDEPTH);  //FIFO数据位宽计算

reg [1  : 0]    R_MS;
wire            R_empty;   //synthesis keep
wire            R_tvalid;  //synthesis keep
assign          R_tvalid          = ~R_empty;
assign          O_R_tvalid        = I_R_tready;

reg             r_tuser_lock;  //synthesis keep
reg             r_tlast;  //synthesis keep
reg [15 : 0]    r_xcnt;  //synthesis keep
reg             fram_end;  //synthesis keep
reg [15 : 0]    r_ycnt;  //synthesis keep

assign          O_R_tuser         = r_tuser_lock & O_R_tvalid;
assign          O_R_tlast         = (r_xcnt == R_XSIZE - 1) & O_R_tvalid;

always @(posedge I_R_rclk or negedge I_ui_rstn) begin
  if (~I_ui_rstn)begin 
                r_xcnt      <= 0;
  end
  else if (O_R_tvalid) begin
    if (r_xcnt == R_XSIZE - 1) 
                r_xcnt          <= 0;
    else        r_xcnt          <= r_xcnt + 1'b1;
  end
end

always @(posedge I_R_rclk or negedge I_ui_rstn) begin
  if (~I_ui_rstn) begin
                r_tuser_lock    <= 1'b1;
                r_ycnt          <= 0;
  end 
  else begin
    if (O_R_tlast) begin
      if (r_ycnt == R_YSIZE - 1) begin
                r_tuser_lock    <= 1'b1;
                r_ycnt          <= 0;
      end else  r_ycnt          <= r_ycnt + 1'b1;
    end 
    else if (O_R_tuser) 
                r_tuser_lock    <= 1'b0;
  end
end

wire [11  : 0]  mm2s_wfifo_cnt;
wire [11  : 0]  mm2s_rfifo_cnt;
assign          O_mm2s_tready    = (R_MS == S_DATA2) ;

//mm2s stream ready
always @(posedge I_ui_clk or negedge I_ui_rstn) begin
    if(I_ui_rstn == 0)
                O_R_tlocked   <= 1'b0;
    else if(mm2s_wfifo_cnt >  (VDMA_RX_BURST - 5) )
                O_R_tlocked   <= 1'b1;
    else 
                O_R_tlocked   <= O_R_tlocked;
end

reg  [7   : 0]  rfifo_rst_cnt; 
reg             m2s_tlast_r1;  //synthesis keep
always @(posedge I_ui_clk ) begin
                m2s_tlast_r1 <= I_mm2s_tlast;
end

reg [11   :0]  m2s_xcnt,m2s_ycnt;
always @(posedge I_ui_clk or negedge I_ui_rstn) begin
    if(I_ui_rstn == 0)
                m2s_ycnt     <= 0;
    else if(I_mm2s_tuser)
                m2s_ycnt     <= 0;
    else if({I_mm2s_tlast,m2s_tlast_r1} == 2'b10)
                m2s_ycnt     <= m2s_ycnt + 1'b1;
end

reg             R_sync_r1,R_sync_r2, R_sync_r3;

always @(posedge I_ui_clk) begin
                R_sync_r1       <= I_R_sync;
                R_sync_r2       <= R_sync_r1;
                R_sync_r3       <= R_sync_r2 | R_sync_r1 |  I_R_sync;        
end  

wire [11:0] R_req;

assign R_req = mm2s_wfifo_cnt < (VDMA_RX_BURST >> 1);

//读通道状态机，采用4个状态值描述
reg             R_first_pass;
always @(posedge I_ui_clk or negedge I_ui_rstn) begin
  if (!I_ui_rstn) begin
                R_first_pass      <= 1'b1;
                R_MS              <= S_IDLE;
                rfifo_rst_cnt     <= 0;
  end 
  else begin
    case (R_MS)
      S_IDLE: begin
                
                R_MS              <= (R_sync_r3|R_first_pass)  ?  S_RST : R_MS; //帧同步，其中R_sync_r3用于具有vs同步的情况，或者设置1
      end
      S_RST:begin//帧同步会同步每一帧，并且复位数据FIFO
                R_first_pass      <= 0;
                if(rfifo_rst_cnt[7] == 1'b1 )begin
                  rfifo_rst_cnt   <= 0;
                  R_MS            <= S_DATA1 ; 
                end
                else begin
                  rfifo_rst_cnt   <= rfifo_rst_cnt + 1'b1;
                  R_MS            <= R_MS;
                end
      end
      S_DATA1: begin  //发送写RDMA请求,或者R通道错误的情况，一直写直到本帧写结束
                if(m2s_ycnt == R_YSIZE)
                    R_MS <= S_IDLE;
                else if(R_req)
                    R_MS <= S_DATA2;
      end
      S_DATA2: begin  //读有效数据
                if({I_mm2s_tlast,m2s_tlast_r1} == 2'b10)
                    R_MS <= S_DATA1;
                else 
                    R_MS <= R_MS;
      end
      default:  R_MS              <= S_IDLE;
      endcase
  end
end

wire  rfifo_rst;
assign  rfifo_rst = (rfifo_rst_cnt >40) & (rfifo_rst_cnt < 90);

/*
wdg wdg_inst
(
.probe0(I_mm2s_tdata[23:0]),
.probe1(I_mm2s_tuser),
.probe2(I_mm2s_tlast),
.probe3(I_mm2s_tvalid),
.probe4(O_mm2s_tready),
.probe5(R_MS),
.probe6(m2s_ycnt),
.probe7(mm2s_wfifo_cnt),
.probe8(R_req),
.probe9(O_R_tvalid),
.probe10(O_R_tdata),
.probe11(R_empty),
.clk(I_ui_clk)
);

wdg1 wdg1_inst
(
.probe0(O_R_tvalid),
.probe1(O_R_tdata),
.probe2(I_R_sync),
.clk(I_R_rclk)
);*/

sfifo_87cc5c5f324a #(
.DATA_WIDTH_W(AXI_DATA_WIDTH),
.DATA_WIDTH_R(R_DATAWIDTH),
.ADDR_WIDTH_W(R_WR_DATA_COUNT_WIDTH),
.ADDR_WIDTH_R(R_RD_DATA_COUNT_WIDTH),
.SHOW_AHEAD_EN(1),
.OUTREG_EN("NOREG")
) rdbuf_fifo (
.rst            (I_ui_rstn == 1'b0 | rfifo_rst  ),
.clkw           (I_ui_clk                       ),
.we             (I_mm2s_tvalid & O_mm2s_tready  ),
.di             (I_mm2s_tdata                   ),
.clkr           (I_R_rclk                       ),
.re             (O_R_tvalid                     ),
.dout           (O_R_tdata                      ),
.wrusedw        (mm2s_wfifo_cnt                 ),
.rdusedw        (mm2s_rfifo_cnt                 ),
.empty_flag     (R_empty                        )
);

// dgwt  dgwt_inst
// (
// .probe0         (wfifo_rst_done_r2              ),
// .probe1         (O_s2mm_tuser                   ),
// .probe2         (O_s2mm_tlast                   ),
// .probe3         (O_s2mm_tvalid                  ),
// .probe4         (I_s2mm_tready                  ),
// .probe5         (O_s2mm_tdata                   ),
// .probe6         (s2m_xcnt                       ),
// .probe7         (I_ui_rstn                        ),
// .probe8         (W_rcnt                         ),
// .probe9         (W_MS                           ),
// .probe10        (I_mm2s_tuser     ),
// .probe11        (I_mm2s_tlast     ),
// .probe12        (O_mm2s_tready    ),
// .probe13        (I_mm2s_tvalid    ),
// .probe14        (I_mm2s_tdata     ),
// .probe15        (mm2s_wfifo_cnt   ),
// .clk            (I_ui_clk                       )
// );

/*
dg2  dg2_inst
(
.probe0     (O_R_tuser        ),
.probe1     (O_R_tlast        ),
.probe2     (r_tuser_lock     ),
.probe3     (O_R_tvalid       ),
.probe4     (O_mm2s_locked    ),

.probe6     (O_R_tdata        ),
.probe7     (r_xcnt[11:0]     ),
.probe8     (r_ycnt[11:0]     ),
.clk        (I_R_rclk         )
);
*/

endmodule

