`timescale 1ns/1ps
// GP1 keeps the existing ERAM-controller path. Only the new 64KiB SoftNPU
// aperture is routed to AXI-Lite. Neural config accesses are aligned words;
// unsupported neural bursts are drained and answered DECERR, never sent to ARM.
module f3p_gp1_softnpu_bridge #(
 parameter [32:0] SOFT_BASE=33'h0a0010000
)(
 input wire clk,rst_n,
 input wire [11:0] s_awid,s_arid,
 input wire [32:0] s_awaddr,s_araddr,
 input wire [3:0] s_awlen,s_arlen,
 input wire [1:0] s_awsize,s_arsize,s_awburst,s_arburst,
 input wire s_awlock,s_arlock,
 input wire [2:0] s_awprot,s_arprot,
 input wire s_awvalid,s_arvalid,
 output wire s_awready,s_arready,
 input wire [31:0] s_wdata,input wire [3:0] s_wstrb,input wire s_wvalid,
 output wire s_wready,
 output wire [11:0] s_bid,s_rid,
 output wire [1:0] s_bresp,s_rresp,
 output wire s_bvalid,s_rvalid,s_rlast,
 input wire s_bready,s_rready,
 output wire [31:0] s_rdata,
 output reg [11:0] m0_awid,m0_arid,
 output reg [32:0] m0_awaddr,m0_araddr,
 output reg [3:0] m0_awlen,m0_arlen,
 output reg [1:0] m0_awsize,m0_arsize,m0_awburst,m0_arburst,
 output reg m0_awlock,m0_arlock,
 output wire m0_awvalid,m0_arvalid,
 input wire m0_awready,m0_arready,
 output wire [31:0] m0_wdata,output wire [3:0] m0_wstrb,output wire m0_wvalid,
 input wire m0_wready,
 input wire [11:0] m0_bid,m0_rid,
 input wire [1:0] m0_bresp,m0_rresp,
 input wire m0_bvalid,m0_rvalid,m0_rlast,
 output wire m0_bready,m0_rready,
 input wire [31:0] m0_rdata,
 output wire [32:0] m1_awaddr,m1_araddr,
 output reg [2:0] m1_awprot,m1_arprot,
 output wire m1_awvalid,m1_arvalid,
 input wire m1_awready,m1_arready,
 output wire [31:0] m1_wdata,output wire [3:0] m1_wstrb,output wire m1_wvalid,
 input wire m1_wready,
 input wire [1:0] m1_bresp,m1_rresp,
 input wire m1_bvalid,m1_rvalid,
 output wire m1_bready,m1_rready,
 input wire [31:0] m1_rdata
);
 reg write_busy,write_soft,write_error,aw_done,w_done;
 reg read_busy,read_soft,read_error,ar_done;
 reg [3:0] write_left,read_left;
 wire aw_soft=s_awaddr[32:16]==SOFT_BASE[32:16];
 wire ar_soft=s_araddr[32:16]==SOFT_BASE[32:16];
 assign s_awready=rst_n&&!write_busy;
 assign s_arready=rst_n&&!read_busy;
 assign m0_awvalid=rst_n&&write_busy&&!write_soft&&!write_error&&!aw_done;
 assign m1_awvalid=rst_n&&write_busy&&write_soft&&!write_error&&!aw_done;
 assign m0_arvalid=rst_n&&read_busy&&!read_soft&&!read_error&&!ar_done;
 assign m1_arvalid=rst_n&&read_busy&&read_soft&&!read_error&&!ar_done;
 assign m1_awaddr=m0_awaddr-SOFT_BASE;assign m1_araddr=m0_araddr-SOFT_BASE;
 assign m0_wdata=s_wdata;assign m1_wdata=s_wdata;
 assign m0_wstrb=s_wstrb;assign m1_wstrb=s_wstrb;
 assign m0_wvalid=rst_n&&write_busy&&!write_soft&&!write_error&&!w_done&&s_wvalid;
 assign m1_wvalid=rst_n&&write_busy&&write_soft&&!write_error&&!w_done&&s_wvalid;
 assign s_wready=rst_n&&write_busy&&!w_done&&(write_error?1'b1:(write_soft?m1_wready:m0_wready));
 wire response_ready=write_busy&&aw_done&&w_done;
 assign s_bvalid=rst_n&&response_ready&&(write_error?1'b1:(write_soft?m1_bvalid:m0_bvalid));
 assign s_bid=write_soft?m0_awid:m0_bid;
 assign s_bresp=write_error?2'b11:(write_soft?m1_bresp:m0_bresp);
 assign m0_bready=rst_n&&response_ready&&!write_error&&!write_soft&&s_bready;
 assign m1_bready=rst_n&&response_ready&&!write_error&&write_soft&&s_bready;
 assign s_rvalid=rst_n&&read_busy&&ar_done&&(read_error?1'b1:(read_soft?m1_rvalid:m0_rvalid));
 assign s_rdata=read_error?32'd0:(read_soft?m1_rdata:m0_rdata);
 assign s_rid=read_soft?m0_arid:m0_rid;
 assign s_rresp=read_error?2'b11:(read_soft?m1_rresp:m0_rresp);
 assign s_rlast=read_error?(read_left==0):(read_soft?1'b1:m0_rlast);
 assign m0_rready=rst_n&&read_busy&&ar_done&&!read_error&&!read_soft&&s_rready;
 assign m1_rready=rst_n&&read_busy&&ar_done&&!read_error&&read_soft&&s_rready;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   write_busy<=0;write_soft<=0;write_error<=0;aw_done<=0;w_done<=0;write_left<=0;
   read_busy<=0;read_soft<=0;read_error<=0;ar_done<=0;read_left<=0;
   m0_awid<=0;m0_arid<=0;m0_awaddr<=0;m0_araddr<=0;m0_awlen<=0;m0_arlen<=0;
   m0_awsize<=0;m0_arsize<=0;m0_awburst<=0;m0_arburst<=0;m0_awlock<=0;m0_arlock<=0;
   m1_awprot<=0;m1_arprot<=0;
  end else begin
   if(s_awvalid&&s_awready)begin
    write_busy<=1;write_soft<=aw_soft;
    write_error<=aw_soft&&(s_awlen!=0||s_awsize!=2||s_awaddr[1:0]!=0);
    aw_done<=aw_soft&&(s_awlen!=0||s_awsize!=2||s_awaddr[1:0]!=0);w_done<=0;write_left<=s_awlen;
    m0_awid<=s_awid;m0_awaddr<=s_awaddr;m0_awlen<=s_awlen;m0_awsize<=s_awsize;
    m0_awburst<=s_awburst;m0_awlock<=s_awlock;m1_awprot<=s_awprot;
   end
   if((m0_awvalid&&m0_awready)||(m1_awvalid&&m1_awready))aw_done<=1;
   if(s_wvalid&&s_wready)begin
    if(write_left==0)w_done<=1;else write_left<=write_left-1'b1;
   end
   if(s_bvalid&&s_bready)write_busy<=0;
   if(s_arvalid&&s_arready)begin
    read_busy<=1;read_soft<=ar_soft;
    read_error<=ar_soft&&(s_arlen!=0||s_arsize!=2||s_araddr[1:0]!=0);
    ar_done<=ar_soft&&(s_arlen!=0||s_arsize!=2||s_araddr[1:0]!=0);read_left<=s_arlen;
    m0_arid<=s_arid;m0_araddr<=s_araddr;m0_arlen<=s_arlen;m0_arsize<=s_arsize;
    m0_arburst<=s_arburst;m0_arlock<=s_arlock;m1_arprot<=s_arprot;
   end
   if((m0_arvalid&&m0_arready)||(m1_arvalid&&m1_arready))ar_done<=1;
   if(s_rvalid&&s_rready)begin
    if(s_rlast)read_busy<=0;else if(read_error)read_left<=read_left-1'b1;
   end
  end
 end
endmodule
