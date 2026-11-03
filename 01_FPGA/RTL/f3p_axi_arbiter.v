`timescale 1ns/1ps
// Two independent AXI masters share one DDR port. One outstanding burst per
// direction; round-robin admission, stable held addresses, registered W/R data.
// Master 0 is the existing camera FDMA; master 1 is SoftNPU. IDs are preserved.
module f3p_axi_arbiter #(
 parameter ADDR_W=33, DATA_W=64, ID_W=6, LEN_W=4, SIZE_W=3
)(
 input wire clk,rst_n,
 input wire [2*ID_W-1:0] s_awid,s_arid,
 input wire [2*ADDR_W-1:0] s_awaddr,s_araddr,
 input wire [2*LEN_W-1:0] s_awlen,s_arlen,
 input wire [2*SIZE_W-1:0] s_awsize,s_arsize,
 input wire [3:0] s_awburst,s_arburst,
 input wire [1:0] s_awlock,s_arlock,
 input wire [7:0] s_awcache,s_arcache,
 input wire [5:0] s_awprot,s_arprot,
 input wire [1:0] s_awvalid,s_arvalid,
 output wire [1:0] s_awready,s_arready,
 input wire [2*DATA_W-1:0] s_wdata,
 input wire [2*(DATA_W/8)-1:0] s_wstrb,
 input wire [1:0] s_wlast,s_wvalid,
 output wire [1:0] s_wready,
 output wire [2*ID_W-1:0] s_bid,s_rid,
 output wire [3:0] s_bresp,s_rresp,
 output wire [1:0] s_bvalid,s_rvalid,s_rlast,
 input wire [1:0] s_bready,s_rready,
 output wire [2*DATA_W-1:0] s_rdata,
 output reg [ID_W-1:0] m_awid,m_arid,
 output reg [ADDR_W-1:0] m_awaddr,m_araddr,
 output reg [LEN_W-1:0] m_awlen,m_arlen,
 output reg [SIZE_W-1:0] m_awsize,m_arsize,
 output reg [1:0] m_awburst,m_arburst,
 output reg m_awlock,m_arlock,
 output reg [3:0] m_awcache,m_arcache,
 output reg [2:0] m_awprot,m_arprot,
 output wire m_awvalid,m_arvalid,
 input wire m_awready,m_arready,
 output reg [DATA_W-1:0] m_wdata,
 output reg [DATA_W/8-1:0] m_wstrb,
 output reg m_wlast,
 output wire m_wvalid,
 input wire m_wready,
 input wire [ID_W-1:0] m_bid,m_rid,
 input wire [1:0] m_bresp,m_rresp,
 input wire m_bvalid,m_rvalid,m_rlast,
 output wire m_bready,m_rready,
 input wire [DATA_W-1:0] m_rdata
);
 reg write_busy,write_owner,last_write,aw_done,source_done,sink_done,wvalid;
 reg read_busy,read_owner,last_read,ar_done,rvalid,rlast;
 reg [DATA_W-1:0] rdata;
 reg [ID_W-1:0] rid;
 reg [1:0] rresp;
 wire choose_w=s_awvalid[1]&&(!s_awvalid[0]||!last_write);
 wire choose_r=s_arvalid[1]&&(!s_arvalid[0]||!last_read);
 assign s_awready=rst_n&&!write_busy?(choose_w?2'b10:2'b01):2'b00;
 assign s_arready=rst_n&&!read_busy?(choose_r?2'b10:2'b01):2'b00;
 assign m_awvalid=rst_n&&write_busy&&!aw_done;
 assign m_arvalid=rst_n&&read_busy&&!ar_done;
 assign m_wvalid=rst_n&&wvalid;
 wire word_space=!wvalid||m_wready;
 assign s_wready=rst_n&&write_busy&&!source_done&&word_space?(write_owner?2'b10:2'b01):2'b00;
 wire take_word=|(s_wvalid&s_wready);
 assign s_bid={2{m_bid}};
 assign s_bresp={2{m_bresp}};
 assign s_bvalid=rst_n&&write_busy&&aw_done&&sink_done&&m_bvalid?(write_owner?2'b10:2'b01):2'b00;
 assign m_bready=rst_n&&write_busy&&aw_done&&sink_done&&s_bready[write_owner];
 assign s_rid={2{rid}};assign s_rresp={2{rresp}};
 assign s_rdata={2{rdata}};assign s_rlast={2{rlast}};
 assign s_rvalid=rst_n&&read_busy&&rvalid?(read_owner?2'b10:2'b01):2'b00;
 wire give_read=rvalid&&s_rready[read_owner];
 assign m_rready=rst_n&&read_busy&&ar_done&&(!rvalid||s_rready[read_owner]);
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   write_busy<=0;write_owner<=0;last_write<=1;aw_done<=0;source_done<=0;sink_done<=0;wvalid<=0;
   read_busy<=0;read_owner<=0;last_read<=1;ar_done<=0;rvalid<=0;rlast<=0;rdata<=0;rid<=0;rresp<=0;
   m_awid<=0;m_awaddr<=0;m_awlen<=0;m_awsize<=0;m_awburst<=0;m_awlock<=0;m_awcache<=0;m_awprot<=0;
   m_arid<=0;m_araddr<=0;m_arlen<=0;m_arsize<=0;m_arburst<=0;m_arlock<=0;m_arcache<=0;m_arprot<=0;
   m_wdata<=0;m_wstrb<=0;m_wlast<=0;
  end else begin
   if(!write_busy&&|(s_awvalid&s_awready))begin
    write_busy<=1;write_owner<=choose_w;last_write<=choose_w;aw_done<=0;source_done<=0;sink_done<=0;
    m_awid<=s_awid[choose_w*ID_W+:ID_W];m_awaddr<=s_awaddr[choose_w*ADDR_W+:ADDR_W];
    m_awlen<=s_awlen[choose_w*LEN_W+:LEN_W];m_awsize<=s_awsize[choose_w*SIZE_W+:SIZE_W];
    m_awburst<=s_awburst[choose_w*2+:2];m_awlock<=s_awlock[choose_w];
    m_awcache<=s_awcache[choose_w*4+:4];m_awprot<=s_awprot[choose_w*3+:3];
   end
   if(m_awvalid&&m_awready)aw_done<=1;
   if(take_word)begin
    m_wdata<=s_wdata[write_owner*DATA_W+:DATA_W];m_wstrb<=s_wstrb[write_owner*(DATA_W/8)+:(DATA_W/8)];
    m_wlast<=s_wlast[write_owner];wvalid<=1;
    if(s_wlast[write_owner])source_done<=1;
   end else if(m_wvalid&&m_wready)wvalid<=0;
   if(m_wvalid&&m_wready&&m_wlast)sink_done<=1;
   if(m_bvalid&&m_bready)write_busy<=0;
   if(!read_busy&&|(s_arvalid&s_arready))begin
    read_busy<=1;read_owner<=choose_r;last_read<=choose_r;ar_done<=0;
    m_arid<=s_arid[choose_r*ID_W+:ID_W];m_araddr<=s_araddr[choose_r*ADDR_W+:ADDR_W];
    m_arlen<=s_arlen[choose_r*LEN_W+:LEN_W];m_arsize<=s_arsize[choose_r*SIZE_W+:SIZE_W];
    m_arburst<=s_arburst[choose_r*2+:2];m_arlock<=s_arlock[choose_r];
    m_arcache<=s_arcache[choose_r*4+:4];m_arprot<=s_arprot[choose_r*3+:3];
   end
   if(m_arvalid&&m_arready)ar_done<=1;
   if(m_rvalid&&m_rready)begin rvalid<=1;rdata<=m_rdata;rid<=m_rid;rresp<=m_rresp;rlast<=m_rlast;end
   else if(give_read)rvalid<=0;
   if(give_read&&rlast)begin read_busy<=0;ar_done<=0;end
  end
 end
endmodule
