/************************************************************\
**	Copyright (c) 2012-2025 anlogic Inc.
**	All Right Reserved.
\************************************************************/
/************************************************************\
**	Gen time	:	2025-10-10 18:13:17
**	DI version	:	174302 2025/09/09
**	TD version	:	6.2.1(build number:175876)
\************************************************************/

module system (
    output wire[15:0] O_dma_debug,
    input wire I_cam_window_ink,input wire I_cam_display,input wire[31:0] I_cam_pixel,
    output wire O_camera_de,O_camera_vs,output wire[16:0] O_linux_line_gray,
    input     wire       [31:0] I_fdma_waddr ,
    input     wire              I_fdma_wareq ,
    input     wire       [15:0] I_fdma_wsize ,
    input     wire       [63:0] I_fdma_wdata ,
    input     wire              I_fdma_wready ,
    input     wire       [31:0] I_fdma_raddr ,
    input     wire              I_fdma_rareq ,
    input     wire       [15:0] I_fdma_rsize ,
    input     wire              I_fdma_rready ,
    input     wire       [31:0] I_mwdata ,
    input     wire              I_pixel_clk ,
    input     wire              I_serial_clk ,
    input     wire              I_irq2 ,
    output    wire              O_ui_clk ,
    output    wire              O_ui_rstn ,
    output    wire              O_fdma_wbusy ,
    output    wire              O_fdma_wvalid ,
    output    wire              O_fdma_rbusy ,
    output    wire       [63:0] O_fdma_rdata ,
    output    wire              O_fdma_rvalid ,
    output    wire              O_mrstn ,
    output    wire        [7:0] O_maddr ,
    output    wire        [3:0] O_mweb ,
    output    wire              O_mcsb ,
    output    wire       [31:0] O_mrdata ,
    output    wire              O_mclk ,
    output    wire              O_hdmi_clk_p ,
    output    wire        [2:0] O_hdmi_tx_p ,
    output    wire              O_refclk
); 
    wire [32:0]       w_port__ARM_Processor_System_0__master_gp0_axi_araddr ;
    wire [31:0]       w_port__AXI_Protocol_Converter_0__us_axi_araddr ;
    wire [32:0]       w_net__ARM_Processor_System_0__master_gp0_axi_araddr ; 

    wire [1:0]        w_port__ARM_Processor_System_0__master_gp0_axi_arburst ;
    wire [1:0]        w_port__AXI_Protocol_Converter_0__us_axi_arburst ;
    wire [1:0]        w_net__ARM_Processor_System_0__master_gp0_axi_arburst ; 

    wire [3:0]        w_port__ARM_Processor_System_0__master_gp0_axi_arcache ;
    wire [3:0]        w_port__AXI_Protocol_Converter_0__us_axi_arcache ;
    wire [3:0]        w_net__ARM_Processor_System_0__master_gp0_axi_arcache ; 

    wire [11:0]       w_port__ARM_Processor_System_0__master_gp0_axi_arid ;
    wire [11:0]       w_port__AXI_Protocol_Converter_0__us_axi_arid ;
    wire [11:0]       w_net__ARM_Processor_System_0__master_gp0_axi_arid ; 

    wire [3:0]        w_port__ARM_Processor_System_0__master_gp0_axi_arlen ;
    wire [7:0]        w_port__AXI_Protocol_Converter_0__us_axi_arlen ;
    wire [3:0]        w_net__ARM_Processor_System_0__master_gp0_axi_arlen ; 

    wire              w_port__ARM_Processor_System_0__master_gp0_axi_arlock ;
    wire [0:0]        w_port__AXI_Protocol_Converter_0__us_axi_arlock ;
    wire              w_net__ARM_Processor_System_0__master_gp0_axi_arlock ; 

    wire [2:0]        w_port__ARM_Processor_System_0__master_gp0_axi_arprot ;
    wire [2:0]        w_port__AXI_Protocol_Converter_0__us_axi_arprot ;
    wire [2:0]        w_net__ARM_Processor_System_0__master_gp0_axi_arprot ; 

    wire [1:0]        w_port__ARM_Processor_System_0__master_gp0_axi_arsize ;
    wire [2:0]        w_port__AXI_Protocol_Converter_0__us_axi_arsize ;
    wire [1:0]        w_net__ARM_Processor_System_0__master_gp0_axi_arsize ; 

    wire              w_port__ARM_Processor_System_0__master_gp0_axi_arvalid ;
    wire              w_port__AXI_Protocol_Converter_0__us_axi_arvalid ;
    wire              w_net__ARM_Processor_System_0__master_gp0_axi_arvalid ; 

    wire [32:0]       w_port__ARM_Processor_System_0__master_gp0_axi_awaddr ;
    wire [31:0]       w_port__AXI_Protocol_Converter_0__us_axi_awaddr ;
    wire [32:0]       w_net__ARM_Processor_System_0__master_gp0_axi_awaddr ; 

    wire [1:0]        w_port__ARM_Processor_System_0__master_gp0_axi_awburst ;
    wire [1:0]        w_port__AXI_Protocol_Converter_0__us_axi_awburst ;
    wire [1:0]        w_net__ARM_Processor_System_0__master_gp0_axi_awburst ; 

    wire [3:0]        w_port__ARM_Processor_System_0__master_gp0_axi_awcache ;
    wire [3:0]        w_port__AXI_Protocol_Converter_0__us_axi_awcache ;
    wire [3:0]        w_net__ARM_Processor_System_0__master_gp0_axi_awcache ; 

    wire [11:0]       w_port__ARM_Processor_System_0__master_gp0_axi_awid ;
    wire [11:0]       w_port__AXI_Protocol_Converter_0__us_axi_awid ;
    wire [11:0]       w_net__ARM_Processor_System_0__master_gp0_axi_awid ; 

    wire [3:0]        w_port__ARM_Processor_System_0__master_gp0_axi_awlen ;
    wire [7:0]        w_port__AXI_Protocol_Converter_0__us_axi_awlen ;
    wire [3:0]        w_net__ARM_Processor_System_0__master_gp0_axi_awlen ; 

    wire              w_port__ARM_Processor_System_0__master_gp0_axi_awlock ;
    wire [0:0]        w_port__AXI_Protocol_Converter_0__us_axi_awlock ;
    wire              w_net__ARM_Processor_System_0__master_gp0_axi_awlock ; 

    wire [2:0]        w_port__ARM_Processor_System_0__master_gp0_axi_awprot ;
    wire [2:0]        w_port__AXI_Protocol_Converter_0__us_axi_awprot ;
    wire [2:0]        w_net__ARM_Processor_System_0__master_gp0_axi_awprot ; 

    wire [1:0]        w_port__ARM_Processor_System_0__master_gp0_axi_awsize ;
    wire [2:0]        w_port__AXI_Protocol_Converter_0__us_axi_awsize ;
    wire [1:0]        w_net__ARM_Processor_System_0__master_gp0_axi_awsize ; 

    wire              w_port__ARM_Processor_System_0__master_gp0_axi_awvalid ;
    wire              w_port__AXI_Protocol_Converter_0__us_axi_awvalid ;
    wire              w_net__ARM_Processor_System_0__master_gp0_axi_awvalid ; 

    wire              w_port__ARM_Processor_System_0__master_gp0_axi_bready ;
    wire              w_port__AXI_Protocol_Converter_0__us_axi_bready ;
    wire              w_net__ARM_Processor_System_0__master_gp0_axi_bready ; 

    wire              w_port__ARM_Processor_System_0__master_gp0_axi_rready ;
    wire              w_port__AXI_Protocol_Converter_0__us_axi_rready ;
    wire              w_net__ARM_Processor_System_0__master_gp0_axi_rready ; 

    wire [31:0]       w_port__ARM_Processor_System_0__master_gp0_axi_wdata ;
    wire [31:0]       w_port__AXI_Protocol_Converter_0__us_axi_wdata ;
    wire [31:0]       w_net__ARM_Processor_System_0__master_gp0_axi_wdata ; 

    wire              w_port__ARM_Processor_System_0__master_gp0_axi_wlast ;
    wire              w_port__AXI_Protocol_Converter_0__us_axi_wlast ;
    wire              w_net__ARM_Processor_System_0__master_gp0_axi_wlast ; 

    wire [3:0]        w_port__ARM_Processor_System_0__master_gp0_axi_wstrb ;
    wire [3:0]        w_port__AXI_Protocol_Converter_0__us_axi_wstrb ;
    wire [3:0]        w_net__ARM_Processor_System_0__master_gp0_axi_wstrb ; 

    wire              w_port__ARM_Processor_System_0__master_gp0_axi_wvalid ;
    wire              w_port__AXI_Protocol_Converter_0__us_axi_wvalid ;
    wire              w_net__ARM_Processor_System_0__master_gp0_axi_wvalid ; 

    wire [32:0]       w_port__ARM_Processor_System_0__master_gp1_axi_araddr ;
    wire [9:0]        w_port__AXI_ERAM_Controller_0__araddr ;
    wire [32:0]       w_net__ARM_Processor_System_0__master_gp1_axi_araddr ; 

    wire [1:0]        w_port__ARM_Processor_System_0__master_gp1_axi_arburst ;
    wire [1:0]        w_port__AXI_ERAM_Controller_0__arburst ;
    wire [1:0]        w_net__ARM_Processor_System_0__master_gp1_axi_arburst ; 

    wire [11:0]       w_port__ARM_Processor_System_0__master_gp1_axi_arid ;
    wire [11:0]       w_port__AXI_ERAM_Controller_0__arid ;
    wire [11:0]       w_net__ARM_Processor_System_0__master_gp1_axi_arid ; 

    wire [3:0]        w_port__ARM_Processor_System_0__master_gp1_axi_arlen ;
    wire [7:0]        w_port__AXI_ERAM_Controller_0__arlen ;
    wire [3:0]        w_net__ARM_Processor_System_0__master_gp1_axi_arlen ; 

    wire              w_port__ARM_Processor_System_0__master_gp1_axi_arlock ;
    wire              w_port__AXI_ERAM_Controller_0__arlock ;
    wire              w_net__ARM_Processor_System_0__master_gp1_axi_arlock ; 

    wire [1:0]        w_port__ARM_Processor_System_0__master_gp1_axi_arsize ;
    wire [2:0]        w_port__AXI_ERAM_Controller_0__arsize ;
    wire [1:0]        w_net__ARM_Processor_System_0__master_gp1_axi_arsize ; 

    wire              w_port__ARM_Processor_System_0__master_gp1_axi_arvalid ;
    wire              w_port__AXI_ERAM_Controller_0__arvalid ;
    wire              w_net__ARM_Processor_System_0__master_gp1_axi_arvalid ; 

    wire [32:0]       w_port__ARM_Processor_System_0__master_gp1_axi_awaddr ;
    wire [9:0]        w_port__AXI_ERAM_Controller_0__awaddr ;
    wire [32:0]       w_net__ARM_Processor_System_0__master_gp1_axi_awaddr ; 

    wire [1:0]        w_port__ARM_Processor_System_0__master_gp1_axi_awburst ;
    wire [1:0]        w_port__AXI_ERAM_Controller_0__awburst ;
    wire [1:0]        w_net__ARM_Processor_System_0__master_gp1_axi_awburst ; 

    wire [11:0]       w_port__ARM_Processor_System_0__master_gp1_axi_awid ;
    wire [11:0]       w_port__AXI_ERAM_Controller_0__awid ;
    wire [11:0]       w_net__ARM_Processor_System_0__master_gp1_axi_awid ; 

    wire [3:0]        w_port__ARM_Processor_System_0__master_gp1_axi_awlen ;
    wire [7:0]        w_port__AXI_ERAM_Controller_0__awlen ;
    wire [3:0]        w_net__ARM_Processor_System_0__master_gp1_axi_awlen ; 

    wire              w_port__ARM_Processor_System_0__master_gp1_axi_awlock ;
    wire              w_port__AXI_ERAM_Controller_0__awlock ;
    wire              w_net__ARM_Processor_System_0__master_gp1_axi_awlock ; 

    wire [1:0]        w_port__ARM_Processor_System_0__master_gp1_axi_awsize ;
    wire [2:0]        w_port__AXI_ERAM_Controller_0__awsize ;
    wire [1:0]        w_net__ARM_Processor_System_0__master_gp1_axi_awsize ; 

    wire              w_port__ARM_Processor_System_0__master_gp1_axi_awvalid ;
    wire              w_port__AXI_ERAM_Controller_0__awvalid ;
    wire              w_net__ARM_Processor_System_0__master_gp1_axi_awvalid ; 

    wire              w_port__ARM_Processor_System_0__master_gp1_axi_bready ;
    wire              w_port__AXI_ERAM_Controller_0__bready ;
    wire              w_net__ARM_Processor_System_0__master_gp1_axi_bready ; 

    wire              w_port__ARM_Processor_System_0__master_gp1_axi_rready ;
    wire              w_port__AXI_ERAM_Controller_0__rready ;
    wire              w_net__ARM_Processor_System_0__master_gp1_axi_rready ; 

    wire [31:0]       w_port__ARM_Processor_System_0__master_gp1_axi_wdata ;
    wire [31:0]       w_port__AXI_ERAM_Controller_0__wdata ;
    wire [31:0]       w_net__ARM_Processor_System_0__master_gp1_axi_wdata ; 

    wire [3:0]        w_port__ARM_Processor_System_0__master_gp1_axi_wstrb ;
    wire [3:0]        w_port__AXI_ERAM_Controller_0__wstrb ;
    wire [3:0]        w_net__ARM_Processor_System_0__master_gp1_axi_wstrb ; 

    wire              w_port__ARM_Processor_System_0__master_gp1_axi_wvalid ;
    wire              w_port__AXI_ERAM_Controller_0__wvalid ;
    wire              w_net__ARM_Processor_System_0__master_gp1_axi_wvalid ; 

    wire              w_port__ARM_Processor_System_0__p2f_clk0 ;
    wire              w_port__ARM_Processor_System_0__slave_hp0_axi_aclk ;
    wire              w_port__VDMA_0__m_axis_mm2s_aclk ;
    wire              w_port__Processor_System_Reset_0_200__clk ;
    wire              w_port__ARM_Processor_System_0__slave_hp1_axi_aclk ;
    wire              w_port__VDMA_0__s_axis_s2mm_aclk ;
    wire              w_port__VDMA_0__m_axi_s2mm_aclk ;
    wire              w_port__VDMA_0__m_axi_mm2s_aclk ;
    wire              w_port__uiFDMA_0__M_AXI_ACLK ;
    wire              w_port__uivbuf_0__I_ui_clk ;
    wire              w_net__ARM_Processor_System_0__p2f_clk0 ; 

    wire              w_port__ARM_Processor_System_0__p2f_clk1 ;
    wire              w_port__Processor_System_Reset_0__clk ;
    wire              w_port__AXI_Matrix_0__aclk ;
    wire              w_port__VDMA_0__s_axi_lite_aclk ;
    wire              w_port__AXI_ERAM_Controller_0__aclk ;
    wire              w_port__ARM_Processor_System_0__master_gp0_axi_aclk ;
    wire              w_port__ARM_Processor_System_0__master_gp1_axi_aclk ;
    wire              w_port__video_timing_generator_v01_0__aclk ;
    wire              w_port__AXI_Protocol_Converter_0__aclk ;
    wire              w_net__ARM_Processor_System_0__p2f_clk1 ; 

    wire              w_port__ARM_Processor_System_0__p2f_clk2 ;
    wire              w_port__video_timing_generator_v01_0__ref_clk ;
    wire              w_port__ChipWatcher_0__clk ;
    wire              w_net__ARM_Processor_System_0__p2f_clk2 ; 

    wire              w_port__ARM_Processor_System_0__p2f_rst0_n ;
    wire              w_port__Processor_System_Reset_0__external_reset ;
    wire              w_net__ARM_Processor_System_0__p2f_rst0_n ; 

    wire [0:0]        w_port__ARM_Processor_System_0__pl_gpio_out ;
    wire              w_port__Processor_System_Reset_0_200__external_reset ;
    wire [0:0]        w_net__ARM_Processor_System_0__pl_gpio_out ; 

    wire              w_port__ARM_Processor_System_0__slave_hp0_axi_arready ;
    wire              w_port__uiFDMA_0__M_AXI_ARREADY ;
    wire              w_net__ARM_Processor_System_0__slave_hp0_axi_arready ; 

    wire              w_port__ARM_Processor_System_0__slave_hp0_axi_awready ;
    wire              w_port__uiFDMA_0__M_AXI_AWREADY ;
    wire              w_net__ARM_Processor_System_0__slave_hp0_axi_awready ; 

    wire [5:0]        w_port__ARM_Processor_System_0__slave_hp0_axi_bid ;
    wire [5:0]        w_port__uiFDMA_0__M_AXI_BID ;
    wire [5:0]        w_net__ARM_Processor_System_0__slave_hp0_axi_bid ; 

    wire [1:0]        w_port__ARM_Processor_System_0__slave_hp0_axi_bresp ;
    wire [1:0]        w_port__uiFDMA_0__M_AXI_BRESP ;
    wire [1:0]        w_net__ARM_Processor_System_0__slave_hp0_axi_bresp ; 

    wire              w_port__ARM_Processor_System_0__slave_hp0_axi_bvalid ;
    wire              w_port__uiFDMA_0__M_AXI_BVALID ;
    wire              w_net__ARM_Processor_System_0__slave_hp0_axi_bvalid ; 

    wire [63:0]       w_port__ARM_Processor_System_0__slave_hp0_axi_rdata ;
    wire [63:0]       w_port__uiFDMA_0__M_AXI_RDATA ;
    wire [63:0]       w_net__ARM_Processor_System_0__slave_hp0_axi_rdata ; 

    wire [5:0]        w_port__ARM_Processor_System_0__slave_hp0_axi_rid ;
    wire [5:0]        w_port__uiFDMA_0__M_AXI_RID ;
    wire [5:0]        w_net__ARM_Processor_System_0__slave_hp0_axi_rid ; 

    wire              w_port__ARM_Processor_System_0__slave_hp0_axi_rlast ;
    wire              w_port__uiFDMA_0__M_AXI_RLAST ;
    wire              w_net__ARM_Processor_System_0__slave_hp0_axi_rlast ; 

    wire [1:0]        w_port__ARM_Processor_System_0__slave_hp0_axi_rresp ;
    wire [1:0]        w_port__uiFDMA_0__M_AXI_RRESP ;
    wire [1:0]        w_net__ARM_Processor_System_0__slave_hp0_axi_rresp ; 

    wire              w_port__ARM_Processor_System_0__slave_hp0_axi_rvalid ;
    wire              w_port__uiFDMA_0__M_AXI_RVALID ;
    wire              w_net__ARM_Processor_System_0__slave_hp0_axi_rvalid ; 

    wire              w_port__ARM_Processor_System_0__slave_hp0_axi_wready ;
    wire              w_port__uiFDMA_0__M_AXI_WREADY ;
    wire              w_net__ARM_Processor_System_0__slave_hp0_axi_wready ; 

    wire              w_port__ARM_Processor_System_0__slave_hp1_axi_arready ;
    wire              w_port__VDMA_0__m_axi_mm2s_arready ;
    wire              w_net__ARM_Processor_System_0__slave_hp1_axi_arready ; 

    wire [63:0]       w_port__ARM_Processor_System_0__slave_hp1_axi_rdata ;
    wire [63:0]       w_port__VDMA_0__m_axi_mm2s_rdata ;
    wire [63:0]       w_net__ARM_Processor_System_0__slave_hp1_axi_rdata ; 

    wire              w_port__ARM_Processor_System_0__slave_hp1_axi_rlast ;
    wire              w_port__VDMA_0__m_axi_mm2s_rlast ;
    wire              w_net__ARM_Processor_System_0__slave_hp1_axi_rlast ; 

    wire [1:0]        w_port__ARM_Processor_System_0__slave_hp1_axi_rresp ;
    wire [1:0]        w_port__VDMA_0__m_axi_mm2s_rresp ;
    wire [1:0]        w_net__ARM_Processor_System_0__slave_hp1_axi_rresp ; 

    wire              w_port__ARM_Processor_System_0__slave_hp1_axi_rvalid ;
    wire              w_port__VDMA_0__m_axi_mm2s_rvalid ;
    wire              w_net__ARM_Processor_System_0__slave_hp1_axi_rvalid ; 

    wire              w_port__AXI_ERAM_Controller_0__arready ;
    wire              w_port__ARM_Processor_System_0__master_gp1_axi_arready ;
    wire              w_net__AXI_ERAM_Controller_0__arready ; 

    wire              w_port__AXI_ERAM_Controller_0__awready ;
    wire              w_port__ARM_Processor_System_0__master_gp1_axi_awready ;
    wire              w_net__AXI_ERAM_Controller_0__awready ; 

    wire [11:0]       w_port__AXI_ERAM_Controller_0__bid ;
    wire [11:0]       w_port__ARM_Processor_System_0__master_gp1_axi_bid ;
    wire [11:0]       w_net__AXI_ERAM_Controller_0__bid ; 

    wire [1:0]        w_port__AXI_ERAM_Controller_0__bresp ;
    wire [1:0]        w_port__ARM_Processor_System_0__master_gp1_axi_bresp ;
    wire [1:0]        w_net__AXI_ERAM_Controller_0__bresp ; 

    wire              w_port__AXI_ERAM_Controller_0__bvalid ;
    wire              w_port__ARM_Processor_System_0__master_gp1_axi_bvalid ;
    wire              w_net__AXI_ERAM_Controller_0__bvalid ; 

    wire [7:0]        w_port__AXI_ERAM_Controller_0__mem_addr ;
    wire [7:0]        w_net__AXI_ERAM_Controller_0__mem_addr ; 

    wire              w_port__AXI_ERAM_Controller_0__mem_csb ;
    wire              w_net__AXI_ERAM_Controller_0__mem_csb ; 

    wire [31:0]       w_port__AXI_ERAM_Controller_0__mem_din ;
    wire [31:0]       w_net__AXI_ERAM_Controller_0__mem_din ; 

    wire [3:0]        w_port__AXI_ERAM_Controller_0__mem_web ;
    wire [3:0]        w_net__AXI_ERAM_Controller_0__mem_web ; 

    wire [31:0]       w_port__AXI_ERAM_Controller_0__rdata ;
    wire [31:0]       w_port__ARM_Processor_System_0__master_gp1_axi_rdata ;
    wire [31:0]       w_net__AXI_ERAM_Controller_0__rdata ; 

    wire [11:0]       w_port__AXI_ERAM_Controller_0__rid ;
    wire [11:0]       w_port__ARM_Processor_System_0__master_gp1_axi_rid ;
    wire [11:0]       w_net__AXI_ERAM_Controller_0__rid ; 

    wire              w_port__AXI_ERAM_Controller_0__rlast ;
    wire              w_port__ARM_Processor_System_0__master_gp1_axi_rlast ;
    wire              w_net__AXI_ERAM_Controller_0__rlast ; 

    wire [1:0]        w_port__AXI_ERAM_Controller_0__rresp ;
    wire [1:0]        w_port__ARM_Processor_System_0__master_gp1_axi_rresp ;
    wire [1:0]        w_net__AXI_ERAM_Controller_0__rresp ; 

    wire              w_port__AXI_ERAM_Controller_0__rvalid ;
    wire              w_port__ARM_Processor_System_0__master_gp1_axi_rvalid ;
    wire              w_net__AXI_ERAM_Controller_0__rvalid ; 

    wire              w_port__AXI_ERAM_Controller_0__wready ;
    wire              w_port__ARM_Processor_System_0__master_gp1_axi_wready ;
    wire              w_net__AXI_ERAM_Controller_0__wready ; 

    wire [32:0]       w_port__AXI_Matrix_0__ds0_araddr ;
    wire [8:0]        w_port__VDMA_0__axi_lite_araddr ;
    wire [32:0]       w_net__AXI_Matrix_0__ds0_araddr ; 

    wire              w_port__AXI_Matrix_0__ds0_arvalid ;
    wire              w_port__VDMA_0__axi_lite_arvalid ;
    wire              w_net__AXI_Matrix_0__ds0_arvalid ; 

    wire [32:0]       w_port__AXI_Matrix_0__ds0_awaddr ;
    wire [8:0]        w_port__VDMA_0__axi_lite_awaddr ;
    wire [32:0]       w_net__AXI_Matrix_0__ds0_awaddr ; 

    wire              w_port__AXI_Matrix_0__ds0_awvalid ;
    wire              w_port__VDMA_0__axi_lite_awvalid ;
    wire              w_net__AXI_Matrix_0__ds0_awvalid ; 

    wire              w_port__AXI_Matrix_0__ds0_bready ;
    wire              w_port__VDMA_0__axi_lite_bready ;
    wire              w_net__AXI_Matrix_0__ds0_bready ; 

    wire              w_port__AXI_Matrix_0__ds0_rready ;
    wire              w_port__VDMA_0__axi_lite_rready ;
    wire              w_net__AXI_Matrix_0__ds0_rready ; 

    wire [31:0]       w_port__AXI_Matrix_0__ds0_wdata ;
    wire [31:0]       w_port__VDMA_0__axi_lite_wdata ;
    wire [31:0]       w_net__AXI_Matrix_0__ds0_wdata ; 

    wire              w_port__AXI_Matrix_0__ds0_wvalid ;
    wire              w_port__VDMA_0__axi_lite_wvalid ;
    wire              w_net__AXI_Matrix_0__ds0_wvalid ; 

    wire [32:0]       w_port__AXI_Matrix_0__ds1_araddr ;
    wire [12:0]       w_port__video_timing_generator_v01_0__s_axi_araddr ;
    wire [32:0]       w_net__AXI_Matrix_0__ds1_araddr ; 

    wire              w_port__AXI_Matrix_0__ds1_arvalid ;
    wire              w_port__video_timing_generator_v01_0__s_axi_arvalid ;
    wire              w_net__AXI_Matrix_0__ds1_arvalid ; 

    wire [32:0]       w_port__AXI_Matrix_0__ds1_awaddr ;
    wire [12:0]       w_port__video_timing_generator_v01_0__s_axi_awaddr ;
    wire [32:0]       w_net__AXI_Matrix_0__ds1_awaddr ; 

    wire              w_port__AXI_Matrix_0__ds1_awvalid ;
    wire              w_port__video_timing_generator_v01_0__s_axi_awvalid ;
    wire              w_net__AXI_Matrix_0__ds1_awvalid ; 

    wire              w_port__AXI_Matrix_0__ds1_bready ;
    wire              w_port__video_timing_generator_v01_0__s_axi_bready ;
    wire              w_net__AXI_Matrix_0__ds1_bready ; 

    wire              w_port__AXI_Matrix_0__ds1_rready ;
    wire              w_port__video_timing_generator_v01_0__s_axi_rready ;
    wire              w_net__AXI_Matrix_0__ds1_rready ; 

    wire [31:0]       w_port__AXI_Matrix_0__ds1_wdata ;
    wire [31:0]       w_port__video_timing_generator_v01_0__s_axi_wdata ;
    wire [31:0]       w_net__AXI_Matrix_0__ds1_wdata ; 

    wire [3:0]        w_port__AXI_Matrix_0__ds1_wstrb ;
    wire [3:0]        w_port__video_timing_generator_v01_0__s_axi_wstrb ;
    wire [3:0]        w_net__AXI_Matrix_0__ds1_wstrb ; 

    wire              w_port__AXI_Matrix_0__ds1_wvalid ;
    wire              w_port__video_timing_generator_v01_0__s_axi_wvalid ;
    wire              w_net__AXI_Matrix_0__ds1_wvalid ; 

    wire              w_port__AXI_Matrix_0__us0_arready ;
    wire              w_port__AXI_Protocol_Converter_0__ds_axi_arready ;
    wire              w_net__AXI_Matrix_0__us0_arready ; 

    wire              w_port__AXI_Matrix_0__us0_awready ;
    wire              w_port__AXI_Protocol_Converter_0__ds_axi_awready ;
    wire              w_net__AXI_Matrix_0__us0_awready ; 

    wire [1:0]        w_port__AXI_Matrix_0__us0_bresp ;
    wire [1:0]        w_port__AXI_Protocol_Converter_0__ds_axi_bresp ;
    wire [1:0]        w_net__AXI_Matrix_0__us0_bresp ; 

    wire              w_port__AXI_Matrix_0__us0_bvalid ;
    wire              w_port__AXI_Protocol_Converter_0__ds_axi_bvalid ;
    wire              w_net__AXI_Matrix_0__us0_bvalid ; 

    wire [31:0]       w_port__AXI_Matrix_0__us0_rdata ;
    wire [31:0]       w_port__AXI_Protocol_Converter_0__ds_axi_rdata ;
    wire [31:0]       w_net__AXI_Matrix_0__us0_rdata ; 

    wire [1:0]        w_port__AXI_Matrix_0__us0_rresp ;
    wire [1:0]        w_port__AXI_Protocol_Converter_0__ds_axi_rresp ;
    wire [1:0]        w_net__AXI_Matrix_0__us0_rresp ; 

    wire              w_port__AXI_Matrix_0__us0_rvalid ;
    wire              w_port__AXI_Protocol_Converter_0__ds_axi_rvalid ;
    wire              w_net__AXI_Matrix_0__us0_rvalid ; 

    wire              w_port__AXI_Matrix_0__us0_wready ;
    wire              w_port__AXI_Protocol_Converter_0__ds_axi_wready ;
    wire              w_net__AXI_Matrix_0__us0_wready ; 

    wire [31:0]       w_port__AXI_Protocol_Converter_0__ds_axi_araddr ;
    wire [32:0]       w_port__AXI_Matrix_0__us0_araddr ;
    wire [31:0]       w_net__AXI_Protocol_Converter_0__ds_axi_araddr ; 

    wire [2:0]        w_port__AXI_Protocol_Converter_0__ds_axi_arprot ;
    wire [2:0]        w_port__AXI_Matrix_0__us0_arprot ;
    wire [2:0]        w_net__AXI_Protocol_Converter_0__ds_axi_arprot ; 

    wire              w_port__AXI_Protocol_Converter_0__ds_axi_arvalid ;
    wire              w_port__AXI_Matrix_0__us0_arvalid ;
    wire              w_net__AXI_Protocol_Converter_0__ds_axi_arvalid ; 

    wire [31:0]       w_port__AXI_Protocol_Converter_0__ds_axi_awaddr ;
    wire [32:0]       w_port__AXI_Matrix_0__us0_awaddr ;
    wire [31:0]       w_net__AXI_Protocol_Converter_0__ds_axi_awaddr ; 

    wire [2:0]        w_port__AXI_Protocol_Converter_0__ds_axi_awprot ;
    wire [2:0]        w_port__AXI_Matrix_0__us0_awprot ;
    wire [2:0]        w_net__AXI_Protocol_Converter_0__ds_axi_awprot ; 

    wire              w_port__AXI_Protocol_Converter_0__ds_axi_awvalid ;
    wire              w_port__AXI_Matrix_0__us0_awvalid ;
    wire              w_net__AXI_Protocol_Converter_0__ds_axi_awvalid ; 

    wire              w_port__AXI_Protocol_Converter_0__ds_axi_bready ;
    wire              w_port__AXI_Matrix_0__us0_bready ;
    wire              w_net__AXI_Protocol_Converter_0__ds_axi_bready ; 

    wire              w_port__AXI_Protocol_Converter_0__ds_axi_rready ;
    wire              w_port__AXI_Matrix_0__us0_rready ;
    wire              w_net__AXI_Protocol_Converter_0__ds_axi_rready ; 

    wire [31:0]       w_port__AXI_Protocol_Converter_0__ds_axi_wdata ;
    wire [31:0]       w_port__AXI_Matrix_0__us0_wdata ;
    wire [31:0]       w_net__AXI_Protocol_Converter_0__ds_axi_wdata ; 

    wire [3:0]        w_port__AXI_Protocol_Converter_0__ds_axi_wstrb ;
    wire [3:0]        w_port__AXI_Matrix_0__us0_wstrb ;
    wire [3:0]        w_net__AXI_Protocol_Converter_0__ds_axi_wstrb ; 

    wire              w_port__AXI_Protocol_Converter_0__ds_axi_wvalid ;
    wire              w_port__AXI_Matrix_0__us0_wvalid ;
    wire              w_net__AXI_Protocol_Converter_0__ds_axi_wvalid ; 

    wire              w_port__AXI_Protocol_Converter_0__us_axi_arready ;
    wire              w_port__ARM_Processor_System_0__master_gp0_axi_arready ;
    wire              w_net__AXI_Protocol_Converter_0__us_axi_arready ; 

    wire              w_port__AXI_Protocol_Converter_0__us_axi_awready ;
    wire              w_port__ARM_Processor_System_0__master_gp0_axi_awready ;
    wire              w_net__AXI_Protocol_Converter_0__us_axi_awready ; 

    wire [11:0]       w_port__AXI_Protocol_Converter_0__us_axi_bid ;
    wire [11:0]       w_port__ARM_Processor_System_0__master_gp0_axi_bid ;
    wire [11:0]       w_net__AXI_Protocol_Converter_0__us_axi_bid ; 

    wire [1:0]        w_port__AXI_Protocol_Converter_0__us_axi_bresp ;
    wire [1:0]        w_port__ARM_Processor_System_0__master_gp0_axi_bresp ;
    wire [1:0]        w_net__AXI_Protocol_Converter_0__us_axi_bresp ; 

    wire              w_port__AXI_Protocol_Converter_0__us_axi_bvalid ;
    wire              w_port__ARM_Processor_System_0__master_gp0_axi_bvalid ;
    wire              w_net__AXI_Protocol_Converter_0__us_axi_bvalid ; 

    wire [31:0]       w_port__AXI_Protocol_Converter_0__us_axi_rdata ;
    wire [31:0]       w_port__ARM_Processor_System_0__master_gp0_axi_rdata ;
    wire [31:0]       w_net__AXI_Protocol_Converter_0__us_axi_rdata ; 

    wire [11:0]       w_port__AXI_Protocol_Converter_0__us_axi_rid ;
    wire [11:0]       w_port__ARM_Processor_System_0__master_gp0_axi_rid ;
    wire [11:0]       w_net__AXI_Protocol_Converter_0__us_axi_rid ; 

    wire              w_port__AXI_Protocol_Converter_0__us_axi_rlast ;
    wire              w_port__ARM_Processor_System_0__master_gp0_axi_rlast ;
    wire              w_net__AXI_Protocol_Converter_0__us_axi_rlast ; 

    wire [1:0]        w_port__AXI_Protocol_Converter_0__us_axi_rresp ;
    wire [1:0]        w_port__ARM_Processor_System_0__master_gp0_axi_rresp ;
    wire [1:0]        w_net__AXI_Protocol_Converter_0__us_axi_rresp ; 

    wire              w_port__AXI_Protocol_Converter_0__us_axi_rvalid ;
    wire              w_port__ARM_Processor_System_0__master_gp0_axi_rvalid ;
    wire              w_net__AXI_Protocol_Converter_0__us_axi_rvalid ; 

    wire              w_port__AXI_Protocol_Converter_0__us_axi_wready ;
    wire              w_port__ARM_Processor_System_0__master_gp0_axi_wready ;
    wire              w_net__AXI_Protocol_Converter_0__us_axi_wready ; 

    wire [2:0]        w_port__Concat_0__Dout ;
    wire [15:0]       w_port__ARM_Processor_System_0__f2p_irq ;
    wire [2:0]        w_net__Concat_0__Dout ; 

    wire [0:0]        w_port__Constant_0__dout ;
    wire              w_port__Processor_System_Reset_0__pll_locked ;
    wire              w_port__Processor_System_Reset_0_200__pll_locked ;
    wire [0:0]        w_net__Constant_0__dout ; 

    wire [0:0]        w_port__Constant_1__dout ;
    wire              w_port__video_timing_generator_v01_0__vtg_ce ;
    wire [0:0]        w_port__ChipWatcher_0__probe4 ;
    wire [0:0]        w_net__Constant_1__dout ; 

    wire [0:0]        w_port__Constant_3__dout ;
    wire              w_port__Processor_System_Reset_0__system_rst ;
    wire              w_port__Processor_System_Reset_0_200__system_rst ;
    wire              w_port__Processor_System_Reset_0__aux_rst ;
    wire              w_port__Processor_System_Reset_0_200__aux_rst ;
    wire [0:0]        w_net__Constant_3__dout ; 

    wire [31:0]       w_port__uiFDMA_0__I_fdma_raddr ;
    wire [31:0]       w_net__I_fdma_raddr ; 

    wire              w_port__uiFDMA_0__I_fdma_rareq ;
    wire              w_net__I_fdma_rareq ; 

    wire              w_port__uiFDMA_0__I_fdma_rready ;
    wire              w_net__I_fdma_rready ; 

    wire [15:0]       w_port__uiFDMA_0__I_fdma_rsize ;
    wire [15:0]       w_net__I_fdma_rsize ; 

    wire [31:0]       w_port__uiFDMA_0__I_fdma_waddr ;
    wire [31:0]       w_net__I_fdma_waddr ; 

    wire              w_port__uiFDMA_0__I_fdma_wareq ;
    wire              w_net__I_fdma_wareq ; 

    wire [63:0]       w_port__uiFDMA_0__I_fdma_wdata ;
    wire [63:0]       w_net__I_fdma_wdata ; 

    wire              w_port__uiFDMA_0__I_fdma_wready ;
    wire              w_net__I_fdma_wready ; 

    wire [15:0]       w_port__uiFDMA_0__I_fdma_wsize ;
    wire [15:0]       w_net__I_fdma_wsize ; 

    wire [0:0]        w_port__Concat_0__In2 ;
    wire [0:0]        w_net__I_irq2 ; 

    wire [31:0]       w_port__AXI_ERAM_Controller_0__mem_dout ;
    wire [31:0]       w_net__I_mwdata ; 

    wire              w_port__uivtc_0__I_vtc_clk ;
    wire              w_port__uivbuf_0__I_R_rclk ;
    wire              w_port__uihdmi_tx_0__I_pixel_clk ;
    wire              w_net__I_pixel_clk ; 

    wire              w_port__uihdmi_tx_0__I_serial_clk ;
    wire              w_net__I_serial_clk ; 

    wire [0:0]        w_port__Processor_System_Reset_0_200__peripheral_aresetn ;
    wire              w_port__uiFDMA_0__M_AXI_ARESETN ;
    wire [0:0]        w_net__Processor_System_Reset_0_200__peripheral_aresetn ; 

    wire [0:0]        w_port__Processor_System_Reset_0__peripheral_aresetn ;
    wire              w_port__AXI_Matrix_0__aresetn ;
    wire              w_port__VDMA_0__resetn ;
    wire              w_port__AXI_ERAM_Controller_0__aresetn ;
    wire              w_port__video_timing_generator_v01_0__arst_n ;
    wire              w_port__AXI_Protocol_Converter_0__aresetn ;
    wire              w_port__uivbuf_0__I_ui_rstn ;
    wire [0:0]        w_net__Processor_System_Reset_0__peripheral_aresetn ; 

    wire [0:0]        w_port__Utility_Vector_Logic_0__result_vector ;
    wire              w_port__uihdmi_tx_0__I_rst ;
    wire [0:0]        w_net__Utility_Vector_Logic_0__result_vector ; 

    wire              w_port__VDMA_0__axi_lite_arready ;
    wire              w_port__AXI_Matrix_0__ds0_arready ;
    wire              w_net__VDMA_0__axi_lite_arready ; 

    wire              w_port__VDMA_0__axi_lite_awready ;
    wire              w_port__AXI_Matrix_0__ds0_awready ;
    wire              w_net__VDMA_0__axi_lite_awready ; 

    wire [1:0]        w_port__VDMA_0__axi_lite_bresp ;
    wire [1:0]        w_port__AXI_Matrix_0__ds0_bresp ;
    wire [1:0]        w_net__VDMA_0__axi_lite_bresp ; 

    wire              w_port__VDMA_0__axi_lite_bvalid ;
    wire              w_port__AXI_Matrix_0__ds0_bvalid ;
    wire              w_net__VDMA_0__axi_lite_bvalid ; 

    wire [31:0]       w_port__VDMA_0__axi_lite_rdata ;
    wire [31:0]       w_port__AXI_Matrix_0__ds0_rdata ;
    wire [31:0]       w_net__VDMA_0__axi_lite_rdata ; 

    wire [1:0]        w_port__VDMA_0__axi_lite_rresp ;
    wire [1:0]        w_port__AXI_Matrix_0__ds0_rresp ;
    wire [1:0]        w_net__VDMA_0__axi_lite_rresp ; 

    wire              w_port__VDMA_0__axi_lite_rvalid ;
    wire              w_port__AXI_Matrix_0__ds0_rvalid ;
    wire              w_net__VDMA_0__axi_lite_rvalid ; 

    wire              w_port__VDMA_0__axi_lite_wready ;
    wire              w_port__AXI_Matrix_0__ds0_wready ;
    wire              w_net__VDMA_0__axi_lite_wready ; 

    wire [31:0]       w_port__VDMA_0__m_axi_mm2s_araddr ;
    wire [32:0]       w_port__ARM_Processor_System_0__slave_hp1_axi_araddr ;
    wire [31:0]       w_net__VDMA_0__m_axi_mm2s_araddr ; 

    wire [1:0]        w_port__VDMA_0__m_axi_mm2s_arburst ;
    wire [1:0]        w_port__ARM_Processor_System_0__slave_hp1_axi_arburst ;
    wire [1:0]        w_net__VDMA_0__m_axi_mm2s_arburst ; 

    wire [3:0]        w_port__VDMA_0__m_axi_mm2s_arcache ;
    wire [3:0]        w_port__ARM_Processor_System_0__slave_hp1_axi_arcache ;
    wire [3:0]        w_net__VDMA_0__m_axi_mm2s_arcache ; 

    wire [7:0]        w_port__VDMA_0__m_axi_mm2s_arlen ;
    wire [3:0]        w_port__ARM_Processor_System_0__slave_hp1_axi_arlen ;
    wire [7:0]        w_net__VDMA_0__m_axi_mm2s_arlen ; 

    wire [2:0]        w_port__VDMA_0__m_axi_mm2s_arprot ;
    wire [2:0]        w_port__ARM_Processor_System_0__slave_hp1_axi_arprot ;
    wire [2:0]        w_net__VDMA_0__m_axi_mm2s_arprot ; 

    wire [2:0]        w_port__VDMA_0__m_axi_mm2s_arsize ;
    wire [1:0]        w_port__ARM_Processor_System_0__slave_hp1_axi_arsize ;
    wire [2:0]        w_net__VDMA_0__m_axi_mm2s_arsize ; 

    wire              w_port__VDMA_0__m_axi_mm2s_arvalid ;
    wire              w_port__ARM_Processor_System_0__slave_hp1_axi_arvalid ;
    wire              w_net__VDMA_0__m_axi_mm2s_arvalid ; 

    wire              w_port__VDMA_0__m_axi_mm2s_rready ;
    wire              w_port__ARM_Processor_System_0__slave_hp1_axi_rready ;
    wire              w_net__VDMA_0__m_axi_mm2s_rready ; 

    wire [63:0]       w_port__VDMA_0__m_axis_mm2s_tdata ;
    wire [63:0]       w_port__uivbuf_0__I_mm2s_tdata ;
    wire [63:0]       w_net__VDMA_0__m_axis_mm2s_tdata ; 

    wire              w_port__VDMA_0__m_axis_mm2s_tlast ;
    wire              w_port__uivbuf_0__I_mm2s_tlast ;
    wire              w_net__VDMA_0__m_axis_mm2s_tlast ; 

    wire [0:0]        w_port__VDMA_0__m_axis_mm2s_tuser ;
    wire              w_port__uivbuf_0__I_mm2s_tuser ;
    wire [0:0]        w_net__VDMA_0__m_axis_mm2s_tuser ; 

    wire              w_port__VDMA_0__m_axis_mm2s_tvalid ;
    wire              w_port__uivbuf_0__I_mm2s_tvalid ;
    wire              w_net__VDMA_0__m_axis_mm2s_tvalid ; 

    wire              w_port__VDMA_0__mm2s_introut ;
    wire [0:0]        w_port__Concat_0__In0 ;
    wire              w_net__VDMA_0__mm2s_introut ; 

    wire              w_port__VDMA_0__s2mm_introut ;
    wire [0:0]        w_port__Concat_0__In1 ;
    wire              w_net__VDMA_0__s2mm_introut ; 

    wire [31:0]       w_port__uiFDMA_0__M_AXI_ARADDR ;
    wire [32:0]       w_port__ARM_Processor_System_0__slave_hp0_axi_araddr ;
    wire [31:0]       w_net__uiFDMA_0__M_AXI_ARADDR ; 

    wire [1:0]        w_port__uiFDMA_0__M_AXI_ARBURST ;
    wire [1:0]        w_port__ARM_Processor_System_0__slave_hp0_axi_arburst ;
    wire [1:0]        w_net__uiFDMA_0__M_AXI_ARBURST ; 

    wire [3:0]        w_port__uiFDMA_0__M_AXI_ARCACHE ;
    wire [3:0]        w_port__ARM_Processor_System_0__slave_hp0_axi_arcache ;
    wire [3:0]        w_net__uiFDMA_0__M_AXI_ARCACHE ; 

    wire [5:0]        w_port__uiFDMA_0__M_AXI_ARID ;
    wire [5:0]        w_port__ARM_Processor_System_0__slave_hp0_axi_arid ;
    wire [5:0]        w_net__uiFDMA_0__M_AXI_ARID ; 

    wire [7:0]        w_port__uiFDMA_0__M_AXI_ARLEN ;
    wire [3:0]        w_port__ARM_Processor_System_0__slave_hp0_axi_arlen ;
    wire [7:0]        w_net__uiFDMA_0__M_AXI_ARLEN ; 

    wire              w_port__uiFDMA_0__M_AXI_ARLOCK ;
    wire              w_port__ARM_Processor_System_0__slave_hp0_axi_arlock ;
    wire              w_net__uiFDMA_0__M_AXI_ARLOCK ; 

    wire [2:0]        w_port__uiFDMA_0__M_AXI_ARPROT ;
    wire [2:0]        w_port__ARM_Processor_System_0__slave_hp0_axi_arprot ;
    wire [2:0]        w_net__uiFDMA_0__M_AXI_ARPROT ; 

    wire [3:0]        w_port__uiFDMA_0__M_AXI_ARQOS ;
    wire [3:0]        w_port__ARM_Processor_System_0__slave_hp0_axi_arqos ;
    wire [3:0]        w_net__uiFDMA_0__M_AXI_ARQOS ; 

    wire [2:0]        w_port__uiFDMA_0__M_AXI_ARSIZE ;
    wire [1:0]        w_port__ARM_Processor_System_0__slave_hp0_axi_arsize ;
    wire [2:0]        w_net__uiFDMA_0__M_AXI_ARSIZE ; 

    wire              w_port__uiFDMA_0__M_AXI_ARVALID ;
    wire              w_port__ARM_Processor_System_0__slave_hp0_axi_arvalid ;
    wire              w_net__uiFDMA_0__M_AXI_ARVALID ; 

    wire [31:0]       w_port__uiFDMA_0__M_AXI_AWADDR ;
    wire [32:0]       w_port__ARM_Processor_System_0__slave_hp0_axi_awaddr ;
    wire [31:0]       w_net__uiFDMA_0__M_AXI_AWADDR ; 

    wire [1:0]        w_port__uiFDMA_0__M_AXI_AWBURST ;
    wire [1:0]        w_port__ARM_Processor_System_0__slave_hp0_axi_awburst ;
    wire [1:0]        w_net__uiFDMA_0__M_AXI_AWBURST ; 

    wire [3:0]        w_port__uiFDMA_0__M_AXI_AWCACHE ;
    wire [3:0]        w_port__ARM_Processor_System_0__slave_hp0_axi_awcache ;
    wire [3:0]        w_net__uiFDMA_0__M_AXI_AWCACHE ; 

    wire [5:0]        w_port__uiFDMA_0__M_AXI_AWID ;
    wire [5:0]        w_port__ARM_Processor_System_0__slave_hp0_axi_awid ;
    wire [5:0]        w_net__uiFDMA_0__M_AXI_AWID ; 

    wire [7:0]        w_port__uiFDMA_0__M_AXI_AWLEN ;
    wire [3:0]        w_port__ARM_Processor_System_0__slave_hp0_axi_awlen ;
    wire [7:0]        w_net__uiFDMA_0__M_AXI_AWLEN ; 

    wire              w_port__uiFDMA_0__M_AXI_AWLOCK ;
    wire              w_port__ARM_Processor_System_0__slave_hp0_axi_awlock ;
    wire              w_net__uiFDMA_0__M_AXI_AWLOCK ; 

    wire [2:0]        w_port__uiFDMA_0__M_AXI_AWPROT ;
    wire [2:0]        w_port__ARM_Processor_System_0__slave_hp0_axi_awprot ;
    wire [2:0]        w_net__uiFDMA_0__M_AXI_AWPROT ; 

    wire [3:0]        w_port__uiFDMA_0__M_AXI_AWQOS ;
    wire [3:0]        w_port__ARM_Processor_System_0__slave_hp0_axi_awqos ;
    wire [3:0]        w_net__uiFDMA_0__M_AXI_AWQOS ; 

    wire [2:0]        w_port__uiFDMA_0__M_AXI_AWSIZE ;
    wire [1:0]        w_port__ARM_Processor_System_0__slave_hp0_axi_awsize ;
    wire [2:0]        w_net__uiFDMA_0__M_AXI_AWSIZE ; 

    wire              w_port__uiFDMA_0__M_AXI_AWVALID ;
    wire              w_port__ARM_Processor_System_0__slave_hp0_axi_awvalid ;
    wire              w_net__uiFDMA_0__M_AXI_AWVALID ; 

    wire              w_port__uiFDMA_0__M_AXI_BREADY ;
    wire              w_port__ARM_Processor_System_0__slave_hp0_axi_bready ;
    wire              w_net__uiFDMA_0__M_AXI_BREADY ; 

    wire              w_port__uiFDMA_0__M_AXI_RREADY ;
    wire              w_port__ARM_Processor_System_0__slave_hp0_axi_rready ;
    wire              w_net__uiFDMA_0__M_AXI_RREADY ; 

    wire [63:0]       w_port__uiFDMA_0__M_AXI_WDATA ;
    wire [63:0]       w_port__ARM_Processor_System_0__slave_hp0_axi_wdata ;
    wire [63:0]       w_net__uiFDMA_0__M_AXI_WDATA ; 

    wire              w_port__uiFDMA_0__M_AXI_WLAST ;
    wire              w_port__ARM_Processor_System_0__slave_hp0_axi_wlast ;
    wire              w_net__uiFDMA_0__M_AXI_WLAST ; 

    wire [7:0]        w_port__uiFDMA_0__M_AXI_WSTRB ;
    wire [7:0]        w_port__ARM_Processor_System_0__slave_hp0_axi_wstrb ;
    wire [7:0]        w_net__uiFDMA_0__M_AXI_WSTRB ; 

    wire              w_port__uiFDMA_0__M_AXI_WVALID ;
    wire              w_port__ARM_Processor_System_0__slave_hp0_axi_wvalid ;
    wire              w_net__uiFDMA_0__M_AXI_WVALID ; 

    wire              w_port__uiFDMA_0__O_fdma_rbusy ;
    wire              w_net__uiFDMA_0__O_fdma_rbusy ; 

    wire [63:0]       w_port__uiFDMA_0__O_fdma_rdata ;
    wire [63:0]       w_net__uiFDMA_0__O_fdma_rdata ; 

    wire              w_port__uiFDMA_0__O_fdma_rvalid ;
    wire              w_net__uiFDMA_0__O_fdma_rvalid ; 

    wire              w_port__uiFDMA_0__O_fdma_wbusy ;
    wire              w_net__uiFDMA_0__O_fdma_wbusy ; 

    wire              w_port__uiFDMA_0__O_fdma_wvalid ;
    wire              w_net__uiFDMA_0__O_fdma_wvalid ; 

    wire              w_port__uihdmi_tx_0__O_hdmi_clk_p ;
    wire              w_net__uihdmi_tx_0__O_hdmi_clk_p ; 

    wire [2:0]        w_port__uihdmi_tx_0__O_hdmi_tx_p ;
    wire [2:0]        w_net__uihdmi_tx_0__O_hdmi_tx_p ; 

    wire [31:0]       w_port__uivbuf_0__O_R_tdata ;
    wire [23:0]       w_port__uihdmi_tx_0__I_video_in_data ;
    wire [31:0]       w_net__uivbuf_0__O_R_tdata ; 

    wire              w_port__uivbuf_0__O_R_tlocked ;
    wire [0:0]        w_port__Utility_Vector_Logic_0__vector_a ;
    wire              w_port__uivtc_0__I_vtc_rstn ;
    wire              w_net__uivbuf_0__O_R_tlocked ; 

    wire              w_port__uivbuf_0__O_mm2s_tready ;
    wire              w_port__VDMA_0__m_axis_mm2s_tready ;
    wire              w_net__uivbuf_0__O_mm2s_tready ; 

    wire              w_port__uivtc_0__O_vtc_de_valid ;
    wire              w_port__uivbuf_0__I_R_tready ;
    wire              w_port__uihdmi_tx_0__I_video_in_de ;
    wire              w_net__uivtc_0__O_vtc_de_valid ; 

    wire              w_port__uivtc_0__O_vtc_hs ;
    wire              w_port__uihdmi_tx_0__I_video_in_hs ;
    wire              w_net__uivtc_0__O_vtc_hs ; 

    wire              w_port__uivtc_0__O_vtc_vs ;
    wire              w_port__uivbuf_0__I_R_sync ;
    wire              w_port__uihdmi_tx_0__I_video_in_vs ;
    wire              w_net__uivtc_0__O_vtc_vs ; 

    wire              w_port__video_timing_generator_v01_0__s_axi_arready ;
    wire              w_port__AXI_Matrix_0__ds1_arready ;
    wire              w_net__video_timing_generator_v01_0__s_axi_arready ; 

    wire              w_port__video_timing_generator_v01_0__s_axi_awready ;
    wire              w_port__AXI_Matrix_0__ds1_awready ;
    wire              w_net__video_timing_generator_v01_0__s_axi_awready ; 

    wire [1:0]        w_port__video_timing_generator_v01_0__s_axi_bresp ;
    wire [1:0]        w_port__AXI_Matrix_0__ds1_bresp ;
    wire [1:0]        w_net__video_timing_generator_v01_0__s_axi_bresp ; 

    wire              w_port__video_timing_generator_v01_0__s_axi_bvalid ;
    wire              w_port__AXI_Matrix_0__ds1_bvalid ;
    wire              w_net__video_timing_generator_v01_0__s_axi_bvalid ; 

    wire [31:0]       w_port__video_timing_generator_v01_0__s_axi_rdata ;
    wire [31:0]       w_port__AXI_Matrix_0__ds1_rdata ;
    wire [31:0]       w_net__video_timing_generator_v01_0__s_axi_rdata ; 

    wire [1:0]        w_port__video_timing_generator_v01_0__s_axi_rresp ;
    wire [1:0]        w_port__AXI_Matrix_0__ds1_rresp ;
    wire [1:0]        w_net__video_timing_generator_v01_0__s_axi_rresp ; 

    wire              w_port__video_timing_generator_v01_0__s_axi_rvalid ;
    wire              w_port__AXI_Matrix_0__ds1_rvalid ;
    wire              w_net__video_timing_generator_v01_0__s_axi_rvalid ; 

    wire              w_port__video_timing_generator_v01_0__s_axi_wready ;
    wire              w_port__AXI_Matrix_0__ds1_wready ;
    wire              w_net__video_timing_generator_v01_0__s_axi_wready ; 

    wire              w_port__video_timing_generator_v01_0__vtg_active_video ;
    wire [0:0]        w_port__ChipWatcher_0__probe1 ;
    wire              w_net__video_timing_generator_v01_0__vtg_active_video ; 

    wire              w_port__video_timing_generator_v01_0__vtg_pclk ;
    wire [0:0]        w_port__ChipWatcher_0__probe3 ;
    wire              w_net__video_timing_generator_v01_0__vtg_pclk ; 

    wire              w_port__video_timing_generator_v01_0__vtg_pclk_locked ;
    wire [0:0]        w_port__ChipWatcher_0__probe0 ;
    wire              w_net__video_timing_generator_v01_0__vtg_pclk_locked ; 

    wire              w_port__video_timing_generator_v01_0__vtg_vsync ;
    wire [0:0]        w_port__ChipWatcher_0__probe2 ;
    wire              w_net__video_timing_generator_v01_0__vtg_vsync ; 









    assign w_net__ARM_Processor_System_0__master_gp0_axi_araddr = w_port__ARM_Processor_System_0__master_gp0_axi_araddr ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_araddr = w_net__ARM_Processor_System_0__master_gp0_axi_araddr ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_arburst = w_port__ARM_Processor_System_0__master_gp0_axi_arburst ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_arburst = w_net__ARM_Processor_System_0__master_gp0_axi_arburst ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_arcache = w_port__ARM_Processor_System_0__master_gp0_axi_arcache ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_arcache = w_net__ARM_Processor_System_0__master_gp0_axi_arcache ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_arid = w_port__ARM_Processor_System_0__master_gp0_axi_arid ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_arid = w_net__ARM_Processor_System_0__master_gp0_axi_arid ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_arlen = w_port__ARM_Processor_System_0__master_gp0_axi_arlen ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_arlen = {4'b0,w_net__ARM_Processor_System_0__master_gp0_axi_arlen} ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_arlock = w_port__ARM_Processor_System_0__master_gp0_axi_arlock ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_arlock = w_net__ARM_Processor_System_0__master_gp0_axi_arlock ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_arprot = w_port__ARM_Processor_System_0__master_gp0_axi_arprot ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_arprot = w_net__ARM_Processor_System_0__master_gp0_axi_arprot ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_arsize = w_port__ARM_Processor_System_0__master_gp0_axi_arsize ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_arsize = {1'b0,w_net__ARM_Processor_System_0__master_gp0_axi_arsize} ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_arvalid = w_port__ARM_Processor_System_0__master_gp0_axi_arvalid ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_arvalid = w_net__ARM_Processor_System_0__master_gp0_axi_arvalid ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_awaddr = w_port__ARM_Processor_System_0__master_gp0_axi_awaddr ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_awaddr = w_net__ARM_Processor_System_0__master_gp0_axi_awaddr ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_awburst = w_port__ARM_Processor_System_0__master_gp0_axi_awburst ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_awburst = w_net__ARM_Processor_System_0__master_gp0_axi_awburst ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_awcache = w_port__ARM_Processor_System_0__master_gp0_axi_awcache ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_awcache = w_net__ARM_Processor_System_0__master_gp0_axi_awcache ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_awid = w_port__ARM_Processor_System_0__master_gp0_axi_awid ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_awid = w_net__ARM_Processor_System_0__master_gp0_axi_awid ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_awlen = w_port__ARM_Processor_System_0__master_gp0_axi_awlen ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_awlen = {4'b0,w_net__ARM_Processor_System_0__master_gp0_axi_awlen} ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_awlock = w_port__ARM_Processor_System_0__master_gp0_axi_awlock ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_awlock = w_net__ARM_Processor_System_0__master_gp0_axi_awlock ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_awprot = w_port__ARM_Processor_System_0__master_gp0_axi_awprot ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_awprot = w_net__ARM_Processor_System_0__master_gp0_axi_awprot ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_awsize = w_port__ARM_Processor_System_0__master_gp0_axi_awsize ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_awsize = {1'b0,w_net__ARM_Processor_System_0__master_gp0_axi_awsize} ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_awvalid = w_port__ARM_Processor_System_0__master_gp0_axi_awvalid ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_awvalid = w_net__ARM_Processor_System_0__master_gp0_axi_awvalid ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_bready = w_port__ARM_Processor_System_0__master_gp0_axi_bready ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_bready = w_net__ARM_Processor_System_0__master_gp0_axi_bready ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_rready = w_port__ARM_Processor_System_0__master_gp0_axi_rready ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_rready = w_net__ARM_Processor_System_0__master_gp0_axi_rready ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_wdata = w_port__ARM_Processor_System_0__master_gp0_axi_wdata ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_wdata = w_net__ARM_Processor_System_0__master_gp0_axi_wdata ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_wlast = w_port__ARM_Processor_System_0__master_gp0_axi_wlast ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_wlast = w_net__ARM_Processor_System_0__master_gp0_axi_wlast ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_wstrb = w_port__ARM_Processor_System_0__master_gp0_axi_wstrb ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_wstrb = w_net__ARM_Processor_System_0__master_gp0_axi_wstrb ;

    assign w_net__ARM_Processor_System_0__master_gp0_axi_wvalid = w_port__ARM_Processor_System_0__master_gp0_axi_wvalid ;
    assign w_port__AXI_Protocol_Converter_0__us_axi_wvalid = w_net__ARM_Processor_System_0__master_gp0_axi_wvalid ;

    assign w_net__ARM_Processor_System_0__master_gp1_axi_araddr = w_port__ARM_Processor_System_0__master_gp1_axi_araddr ;
    assign w_port__AXI_ERAM_Controller_0__araddr = w_net__ARM_Processor_System_0__master_gp1_axi_araddr ;

    assign w_net__ARM_Processor_System_0__master_gp1_axi_arburst = w_port__ARM_Processor_System_0__master_gp1_axi_arburst ;
    assign w_port__AXI_ERAM_Controller_0__arburst = w_net__ARM_Processor_System_0__master_gp1_axi_arburst ;

    assign w_net__ARM_Processor_System_0__master_gp1_axi_arid = w_port__ARM_Processor_System_0__master_gp1_axi_arid ;
    assign w_port__AXI_ERAM_Controller_0__arid = w_net__ARM_Processor_System_0__master_gp1_axi_arid ;

    assign w_net__ARM_Processor_System_0__master_gp1_axi_arlen = w_port__ARM_Processor_System_0__master_gp1_axi_arlen ;
    assign w_port__AXI_ERAM_Controller_0__arlen = {4'b0,w_net__ARM_Processor_System_0__master_gp1_axi_arlen} ;

    assign w_net__ARM_Processor_System_0__master_gp1_axi_arlock = w_port__ARM_Processor_System_0__master_gp1_axi_arlock ;
    assign w_port__AXI_ERAM_Controller_0__arlock = w_net__ARM_Processor_System_0__master_gp1_axi_arlock ;

    assign w_net__ARM_Processor_System_0__master_gp1_axi_arsize = w_port__ARM_Processor_System_0__master_gp1_axi_arsize ;
    assign w_port__AXI_ERAM_Controller_0__arsize = {1'b0,w_net__ARM_Processor_System_0__master_gp1_axi_arsize} ;

    assign w_net__ARM_Processor_System_0__master_gp1_axi_arvalid = w_port__ARM_Processor_System_0__master_gp1_axi_arvalid ;
    assign w_port__AXI_ERAM_Controller_0__arvalid = w_net__ARM_Processor_System_0__master_gp1_axi_arvalid ;

    assign w_net__ARM_Processor_System_0__master_gp1_axi_awaddr = w_port__ARM_Processor_System_0__master_gp1_axi_awaddr ;
    assign w_port__AXI_ERAM_Controller_0__awaddr = w_net__ARM_Processor_System_0__master_gp1_axi_awaddr ;

    assign w_net__ARM_Processor_System_0__master_gp1_axi_awburst = w_port__ARM_Processor_System_0__master_gp1_axi_awburst ;
    assign w_port__AXI_ERAM_Controller_0__awburst = w_net__ARM_Processor_System_0__master_gp1_axi_awburst ;

    assign w_net__ARM_Processor_System_0__master_gp1_axi_awid = w_port__ARM_Processor_System_0__master_gp1_axi_awid ;
    assign w_port__AXI_ERAM_Controller_0__awid = w_net__ARM_Processor_System_0__master_gp1_axi_awid ;

    assign w_net__ARM_Processor_System_0__master_gp1_axi_awlen = w_port__ARM_Processor_System_0__master_gp1_axi_awlen ;
    assign w_port__AXI_ERAM_Controller_0__awlen = {4'b0,w_net__ARM_Processor_System_0__master_gp1_axi_awlen} ;

    assign w_net__ARM_Processor_System_0__master_gp1_axi_awlock = w_port__ARM_Processor_System_0__master_gp1_axi_awlock ;
    assign w_port__AXI_ERAM_Controller_0__awlock = w_net__ARM_Processor_System_0__master_gp1_axi_awlock ;

    assign w_net__ARM_Processor_System_0__master_gp1_axi_awsize = w_port__ARM_Processor_System_0__master_gp1_axi_awsize ;
    assign w_port__AXI_ERAM_Controller_0__awsize = {1'b0,w_net__ARM_Processor_System_0__master_gp1_axi_awsize} ;

    assign w_net__ARM_Processor_System_0__master_gp1_axi_awvalid = w_port__ARM_Processor_System_0__master_gp1_axi_awvalid ;
    assign w_port__AXI_ERAM_Controller_0__awvalid = w_net__ARM_Processor_System_0__master_gp1_axi_awvalid ;

    assign w_net__ARM_Processor_System_0__master_gp1_axi_bready = w_port__ARM_Processor_System_0__master_gp1_axi_bready ;
    assign w_port__AXI_ERAM_Controller_0__bready = w_net__ARM_Processor_System_0__master_gp1_axi_bready ;

    assign w_net__ARM_Processor_System_0__master_gp1_axi_rready = w_port__ARM_Processor_System_0__master_gp1_axi_rready ;
    assign w_port__AXI_ERAM_Controller_0__rready = w_net__ARM_Processor_System_0__master_gp1_axi_rready ;

    assign w_net__ARM_Processor_System_0__master_gp1_axi_wdata = w_port__ARM_Processor_System_0__master_gp1_axi_wdata ;
    assign w_port__AXI_ERAM_Controller_0__wdata = w_net__ARM_Processor_System_0__master_gp1_axi_wdata ;

    assign w_net__ARM_Processor_System_0__master_gp1_axi_wstrb = w_port__ARM_Processor_System_0__master_gp1_axi_wstrb ;
    assign w_port__AXI_ERAM_Controller_0__wstrb = w_net__ARM_Processor_System_0__master_gp1_axi_wstrb ;

    assign w_net__ARM_Processor_System_0__master_gp1_axi_wvalid = w_port__ARM_Processor_System_0__master_gp1_axi_wvalid ;
    assign w_port__AXI_ERAM_Controller_0__wvalid = w_net__ARM_Processor_System_0__master_gp1_axi_wvalid ;

    assign w_net__ARM_Processor_System_0__p2f_clk0 = w_port__ARM_Processor_System_0__p2f_clk0 ;
    assign O_ui_clk = w_net__ARM_Processor_System_0__p2f_clk0 ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_aclk = w_net__ARM_Processor_System_0__p2f_clk0 ;
    assign w_port__VDMA_0__m_axis_mm2s_aclk = w_net__ARM_Processor_System_0__p2f_clk0 ;
    assign w_port__Processor_System_Reset_0_200__clk = w_net__ARM_Processor_System_0__p2f_clk0 ;
    assign w_port__ARM_Processor_System_0__slave_hp1_axi_aclk = w_net__ARM_Processor_System_0__p2f_clk0 ;
    assign w_port__VDMA_0__s_axis_s2mm_aclk = w_net__ARM_Processor_System_0__p2f_clk0 ;
    assign w_port__VDMA_0__m_axi_s2mm_aclk = w_net__ARM_Processor_System_0__p2f_clk0 ;
    assign w_port__VDMA_0__m_axi_mm2s_aclk = w_net__ARM_Processor_System_0__p2f_clk0 ;
    assign w_port__uiFDMA_0__M_AXI_ACLK = w_net__ARM_Processor_System_0__p2f_clk0 ;
    assign w_port__uivbuf_0__I_ui_clk = w_net__ARM_Processor_System_0__p2f_clk0 ;

    assign w_net__ARM_Processor_System_0__p2f_clk1 = w_port__ARM_Processor_System_0__p2f_clk1 ;
    assign w_port__Processor_System_Reset_0__clk = w_net__ARM_Processor_System_0__p2f_clk1 ;
    assign w_port__AXI_Matrix_0__aclk = w_net__ARM_Processor_System_0__p2f_clk1 ;
    assign w_port__VDMA_0__s_axi_lite_aclk = w_net__ARM_Processor_System_0__p2f_clk1 ;
    assign w_port__AXI_ERAM_Controller_0__aclk = w_net__ARM_Processor_System_0__p2f_clk1 ;
    assign w_port__ARM_Processor_System_0__master_gp0_axi_aclk = w_net__ARM_Processor_System_0__p2f_clk1 ;
    assign w_port__ARM_Processor_System_0__master_gp1_axi_aclk = w_net__ARM_Processor_System_0__p2f_clk1 ;
    assign O_mclk = w_net__ARM_Processor_System_0__p2f_clk1 ;
    assign w_port__video_timing_generator_v01_0__aclk = w_net__ARM_Processor_System_0__p2f_clk1 ;
    assign w_port__AXI_Protocol_Converter_0__aclk = w_net__ARM_Processor_System_0__p2f_clk1 ;

    assign w_net__ARM_Processor_System_0__p2f_clk2 = w_port__ARM_Processor_System_0__p2f_clk2 ;
    assign w_port__video_timing_generator_v01_0__ref_clk = w_net__ARM_Processor_System_0__p2f_clk2 ;
    assign w_port__ChipWatcher_0__clk = w_net__ARM_Processor_System_0__p2f_clk2 ;
    assign O_refclk = w_net__ARM_Processor_System_0__p2f_clk2 ;

    assign w_net__ARM_Processor_System_0__p2f_rst0_n = w_port__ARM_Processor_System_0__p2f_rst0_n ;
    assign w_port__Processor_System_Reset_0__external_reset = w_net__ARM_Processor_System_0__p2f_rst0_n ;

    assign w_net__ARM_Processor_System_0__pl_gpio_out = w_port__ARM_Processor_System_0__pl_gpio_out ;
    assign w_port__Processor_System_Reset_0_200__external_reset = w_net__ARM_Processor_System_0__pl_gpio_out ;

    assign w_net__ARM_Processor_System_0__slave_hp0_axi_arready = w_port__ARM_Processor_System_0__slave_hp0_axi_arready ;
    assign w_port__uiFDMA_0__M_AXI_ARREADY = w_net__ARM_Processor_System_0__slave_hp0_axi_arready ;

    assign w_net__ARM_Processor_System_0__slave_hp0_axi_awready = w_port__ARM_Processor_System_0__slave_hp0_axi_awready ;
    assign w_port__uiFDMA_0__M_AXI_AWREADY = w_net__ARM_Processor_System_0__slave_hp0_axi_awready ;

    assign w_net__ARM_Processor_System_0__slave_hp0_axi_bid = w_port__ARM_Processor_System_0__slave_hp0_axi_bid ;
    assign w_port__uiFDMA_0__M_AXI_BID = w_net__ARM_Processor_System_0__slave_hp0_axi_bid ;

    assign w_net__ARM_Processor_System_0__slave_hp0_axi_bresp = w_port__ARM_Processor_System_0__slave_hp0_axi_bresp ;
    assign w_port__uiFDMA_0__M_AXI_BRESP = w_net__ARM_Processor_System_0__slave_hp0_axi_bresp ;

    assign w_net__ARM_Processor_System_0__slave_hp0_axi_bvalid = w_port__ARM_Processor_System_0__slave_hp0_axi_bvalid ;
    assign w_port__uiFDMA_0__M_AXI_BVALID = w_net__ARM_Processor_System_0__slave_hp0_axi_bvalid ;

    assign w_net__ARM_Processor_System_0__slave_hp0_axi_rdata = w_port__ARM_Processor_System_0__slave_hp0_axi_rdata ;
    assign w_port__uiFDMA_0__M_AXI_RDATA = w_net__ARM_Processor_System_0__slave_hp0_axi_rdata ;

    assign w_net__ARM_Processor_System_0__slave_hp0_axi_rid = w_port__ARM_Processor_System_0__slave_hp0_axi_rid ;
    assign w_port__uiFDMA_0__M_AXI_RID = w_net__ARM_Processor_System_0__slave_hp0_axi_rid ;

    assign w_net__ARM_Processor_System_0__slave_hp0_axi_rlast = w_port__ARM_Processor_System_0__slave_hp0_axi_rlast ;
    assign w_port__uiFDMA_0__M_AXI_RLAST = w_net__ARM_Processor_System_0__slave_hp0_axi_rlast ;

    assign w_net__ARM_Processor_System_0__slave_hp0_axi_rresp = w_port__ARM_Processor_System_0__slave_hp0_axi_rresp ;
    assign w_port__uiFDMA_0__M_AXI_RRESP = w_net__ARM_Processor_System_0__slave_hp0_axi_rresp ;

    assign w_net__ARM_Processor_System_0__slave_hp0_axi_rvalid = w_port__ARM_Processor_System_0__slave_hp0_axi_rvalid ;
    assign w_port__uiFDMA_0__M_AXI_RVALID = w_net__ARM_Processor_System_0__slave_hp0_axi_rvalid ;

    assign w_net__ARM_Processor_System_0__slave_hp0_axi_wready = w_port__ARM_Processor_System_0__slave_hp0_axi_wready ;
    assign w_port__uiFDMA_0__M_AXI_WREADY = w_net__ARM_Processor_System_0__slave_hp0_axi_wready ;

    assign w_net__ARM_Processor_System_0__slave_hp1_axi_arready = w_port__ARM_Processor_System_0__slave_hp1_axi_arready ;
    assign w_port__VDMA_0__m_axi_mm2s_arready = w_net__ARM_Processor_System_0__slave_hp1_axi_arready ;

    assign w_net__ARM_Processor_System_0__slave_hp1_axi_rdata = w_port__ARM_Processor_System_0__slave_hp1_axi_rdata ;


    assign w_net__ARM_Processor_System_0__slave_hp1_axi_rlast = w_port__ARM_Processor_System_0__slave_hp1_axi_rlast ;


    assign w_net__ARM_Processor_System_0__slave_hp1_axi_rresp = w_port__ARM_Processor_System_0__slave_hp1_axi_rresp ;


    assign w_net__ARM_Processor_System_0__slave_hp1_axi_rvalid = w_port__ARM_Processor_System_0__slave_hp1_axi_rvalid ;


    assign w_net__AXI_ERAM_Controller_0__arready = w_port__AXI_ERAM_Controller_0__arready ;
    assign w_port__ARM_Processor_System_0__master_gp1_axi_arready = w_net__AXI_ERAM_Controller_0__arready ;

    assign w_net__AXI_ERAM_Controller_0__awready = w_port__AXI_ERAM_Controller_0__awready ;
    assign w_port__ARM_Processor_System_0__master_gp1_axi_awready = w_net__AXI_ERAM_Controller_0__awready ;

    assign w_net__AXI_ERAM_Controller_0__bid = w_port__AXI_ERAM_Controller_0__bid ;
    assign w_port__ARM_Processor_System_0__master_gp1_axi_bid = w_net__AXI_ERAM_Controller_0__bid ;

    assign w_net__AXI_ERAM_Controller_0__bresp = w_port__AXI_ERAM_Controller_0__bresp ;
    assign w_port__ARM_Processor_System_0__master_gp1_axi_bresp = w_net__AXI_ERAM_Controller_0__bresp ;

    assign w_net__AXI_ERAM_Controller_0__bvalid = w_port__AXI_ERAM_Controller_0__bvalid ;
    assign w_port__ARM_Processor_System_0__master_gp1_axi_bvalid = w_net__AXI_ERAM_Controller_0__bvalid ;

    assign w_net__AXI_ERAM_Controller_0__mem_addr = w_port__AXI_ERAM_Controller_0__mem_addr ;
    assign O_maddr = w_net__AXI_ERAM_Controller_0__mem_addr ;

    assign w_net__AXI_ERAM_Controller_0__mem_csb = w_port__AXI_ERAM_Controller_0__mem_csb ;
    assign O_mcsb = w_net__AXI_ERAM_Controller_0__mem_csb ;

    assign w_net__AXI_ERAM_Controller_0__mem_din = w_port__AXI_ERAM_Controller_0__mem_din ;
    assign O_mrdata = w_net__AXI_ERAM_Controller_0__mem_din ;

    assign w_net__AXI_ERAM_Controller_0__mem_web = w_port__AXI_ERAM_Controller_0__mem_web ;
    assign O_mweb = w_net__AXI_ERAM_Controller_0__mem_web ;

    assign w_net__AXI_ERAM_Controller_0__rdata = w_port__AXI_ERAM_Controller_0__rdata ;
    assign w_port__ARM_Processor_System_0__master_gp1_axi_rdata = w_net__AXI_ERAM_Controller_0__rdata ;

    assign w_net__AXI_ERAM_Controller_0__rid = w_port__AXI_ERAM_Controller_0__rid ;
    assign w_port__ARM_Processor_System_0__master_gp1_axi_rid = w_net__AXI_ERAM_Controller_0__rid ;

    assign w_net__AXI_ERAM_Controller_0__rlast = w_port__AXI_ERAM_Controller_0__rlast ;
    assign w_port__ARM_Processor_System_0__master_gp1_axi_rlast = w_net__AXI_ERAM_Controller_0__rlast ;

    assign w_net__AXI_ERAM_Controller_0__rresp = w_port__AXI_ERAM_Controller_0__rresp ;
    assign w_port__ARM_Processor_System_0__master_gp1_axi_rresp = w_net__AXI_ERAM_Controller_0__rresp ;

    assign w_net__AXI_ERAM_Controller_0__rvalid = w_port__AXI_ERAM_Controller_0__rvalid ;
    assign w_port__ARM_Processor_System_0__master_gp1_axi_rvalid = w_net__AXI_ERAM_Controller_0__rvalid ;

    assign w_net__AXI_ERAM_Controller_0__wready = w_port__AXI_ERAM_Controller_0__wready ;
    assign w_port__ARM_Processor_System_0__master_gp1_axi_wready = w_net__AXI_ERAM_Controller_0__wready ;

    assign w_net__AXI_Matrix_0__ds0_araddr = w_port__AXI_Matrix_0__ds0_araddr ;
    assign w_port__VDMA_0__axi_lite_araddr = w_net__AXI_Matrix_0__ds0_araddr ;

    assign w_net__AXI_Matrix_0__ds0_arvalid = w_port__AXI_Matrix_0__ds0_arvalid ;
    assign w_port__VDMA_0__axi_lite_arvalid = w_net__AXI_Matrix_0__ds0_arvalid ;

    assign w_net__AXI_Matrix_0__ds0_awaddr = w_port__AXI_Matrix_0__ds0_awaddr ;
    assign w_port__VDMA_0__axi_lite_awaddr = w_net__AXI_Matrix_0__ds0_awaddr ;

    assign w_net__AXI_Matrix_0__ds0_awvalid = w_port__AXI_Matrix_0__ds0_awvalid ;
    assign w_port__VDMA_0__axi_lite_awvalid = w_net__AXI_Matrix_0__ds0_awvalid ;

    assign w_net__AXI_Matrix_0__ds0_bready = w_port__AXI_Matrix_0__ds0_bready ;
    assign w_port__VDMA_0__axi_lite_bready = w_net__AXI_Matrix_0__ds0_bready ;

    assign w_net__AXI_Matrix_0__ds0_rready = w_port__AXI_Matrix_0__ds0_rready ;
    assign w_port__VDMA_0__axi_lite_rready = w_net__AXI_Matrix_0__ds0_rready ;

    assign w_net__AXI_Matrix_0__ds0_wdata = w_port__AXI_Matrix_0__ds0_wdata ;
    assign w_port__VDMA_0__axi_lite_wdata = w_net__AXI_Matrix_0__ds0_wdata ;

    assign w_net__AXI_Matrix_0__ds0_wvalid = w_port__AXI_Matrix_0__ds0_wvalid ;
    assign w_port__VDMA_0__axi_lite_wvalid = w_net__AXI_Matrix_0__ds0_wvalid ;

    assign w_net__AXI_Matrix_0__ds1_araddr = w_port__AXI_Matrix_0__ds1_araddr ;
    assign w_port__video_timing_generator_v01_0__s_axi_araddr = w_net__AXI_Matrix_0__ds1_araddr ;

    assign w_net__AXI_Matrix_0__ds1_arvalid = w_port__AXI_Matrix_0__ds1_arvalid ;
    assign w_port__video_timing_generator_v01_0__s_axi_arvalid = w_net__AXI_Matrix_0__ds1_arvalid ;

    assign w_net__AXI_Matrix_0__ds1_awaddr = w_port__AXI_Matrix_0__ds1_awaddr ;
    assign w_port__video_timing_generator_v01_0__s_axi_awaddr = w_net__AXI_Matrix_0__ds1_awaddr ;

    assign w_net__AXI_Matrix_0__ds1_awvalid = w_port__AXI_Matrix_0__ds1_awvalid ;
    assign w_port__video_timing_generator_v01_0__s_axi_awvalid = w_net__AXI_Matrix_0__ds1_awvalid ;

    assign w_net__AXI_Matrix_0__ds1_bready = w_port__AXI_Matrix_0__ds1_bready ;
    assign w_port__video_timing_generator_v01_0__s_axi_bready = w_net__AXI_Matrix_0__ds1_bready ;

    assign w_net__AXI_Matrix_0__ds1_rready = w_port__AXI_Matrix_0__ds1_rready ;
    assign w_port__video_timing_generator_v01_0__s_axi_rready = w_net__AXI_Matrix_0__ds1_rready ;

    assign w_net__AXI_Matrix_0__ds1_wdata = w_port__AXI_Matrix_0__ds1_wdata ;
    assign w_port__video_timing_generator_v01_0__s_axi_wdata = w_net__AXI_Matrix_0__ds1_wdata ;

    assign w_net__AXI_Matrix_0__ds1_wstrb = w_port__AXI_Matrix_0__ds1_wstrb ;
    assign w_port__video_timing_generator_v01_0__s_axi_wstrb = w_net__AXI_Matrix_0__ds1_wstrb ;

    assign w_net__AXI_Matrix_0__ds1_wvalid = w_port__AXI_Matrix_0__ds1_wvalid ;
    assign w_port__video_timing_generator_v01_0__s_axi_wvalid = w_net__AXI_Matrix_0__ds1_wvalid ;

    assign w_net__AXI_Matrix_0__us0_arready = w_port__AXI_Matrix_0__us0_arready ;
    assign w_port__AXI_Protocol_Converter_0__ds_axi_arready = w_net__AXI_Matrix_0__us0_arready ;

    assign w_net__AXI_Matrix_0__us0_awready = w_port__AXI_Matrix_0__us0_awready ;
    assign w_port__AXI_Protocol_Converter_0__ds_axi_awready = w_net__AXI_Matrix_0__us0_awready ;

    assign w_net__AXI_Matrix_0__us0_bresp = w_port__AXI_Matrix_0__us0_bresp ;
    assign w_port__AXI_Protocol_Converter_0__ds_axi_bresp = w_net__AXI_Matrix_0__us0_bresp ;

    assign w_net__AXI_Matrix_0__us0_bvalid = w_port__AXI_Matrix_0__us0_bvalid ;
    assign w_port__AXI_Protocol_Converter_0__ds_axi_bvalid = w_net__AXI_Matrix_0__us0_bvalid ;

    assign w_net__AXI_Matrix_0__us0_rdata = w_port__AXI_Matrix_0__us0_rdata ;
    assign w_port__AXI_Protocol_Converter_0__ds_axi_rdata = w_net__AXI_Matrix_0__us0_rdata ;

    assign w_net__AXI_Matrix_0__us0_rresp = w_port__AXI_Matrix_0__us0_rresp ;
    assign w_port__AXI_Protocol_Converter_0__ds_axi_rresp = w_net__AXI_Matrix_0__us0_rresp ;

    assign w_net__AXI_Matrix_0__us0_rvalid = w_port__AXI_Matrix_0__us0_rvalid ;
    assign w_port__AXI_Protocol_Converter_0__ds_axi_rvalid = w_net__AXI_Matrix_0__us0_rvalid ;

    assign w_net__AXI_Matrix_0__us0_wready = w_port__AXI_Matrix_0__us0_wready ;
    assign w_port__AXI_Protocol_Converter_0__ds_axi_wready = w_net__AXI_Matrix_0__us0_wready ;

    assign w_net__AXI_Protocol_Converter_0__ds_axi_araddr = w_port__AXI_Protocol_Converter_0__ds_axi_araddr ;
    assign w_port__AXI_Matrix_0__us0_araddr = {1'b0,w_net__AXI_Protocol_Converter_0__ds_axi_araddr} ;

    assign w_net__AXI_Protocol_Converter_0__ds_axi_arprot = w_port__AXI_Protocol_Converter_0__ds_axi_arprot ;
    assign w_port__AXI_Matrix_0__us0_arprot = w_net__AXI_Protocol_Converter_0__ds_axi_arprot ;

    assign w_net__AXI_Protocol_Converter_0__ds_axi_arvalid = w_port__AXI_Protocol_Converter_0__ds_axi_arvalid ;
    assign w_port__AXI_Matrix_0__us0_arvalid = w_net__AXI_Protocol_Converter_0__ds_axi_arvalid ;

    assign w_net__AXI_Protocol_Converter_0__ds_axi_awaddr = w_port__AXI_Protocol_Converter_0__ds_axi_awaddr ;
    assign w_port__AXI_Matrix_0__us0_awaddr = {1'b0,w_net__AXI_Protocol_Converter_0__ds_axi_awaddr} ;

    assign w_net__AXI_Protocol_Converter_0__ds_axi_awprot = w_port__AXI_Protocol_Converter_0__ds_axi_awprot ;
    assign w_port__AXI_Matrix_0__us0_awprot = w_net__AXI_Protocol_Converter_0__ds_axi_awprot ;

    assign w_net__AXI_Protocol_Converter_0__ds_axi_awvalid = w_port__AXI_Protocol_Converter_0__ds_axi_awvalid ;
    assign w_port__AXI_Matrix_0__us0_awvalid = w_net__AXI_Protocol_Converter_0__ds_axi_awvalid ;

    assign w_net__AXI_Protocol_Converter_0__ds_axi_bready = w_port__AXI_Protocol_Converter_0__ds_axi_bready ;
    assign w_port__AXI_Matrix_0__us0_bready = w_net__AXI_Protocol_Converter_0__ds_axi_bready ;

    assign w_net__AXI_Protocol_Converter_0__ds_axi_rready = w_port__AXI_Protocol_Converter_0__ds_axi_rready ;
    assign w_port__AXI_Matrix_0__us0_rready = w_net__AXI_Protocol_Converter_0__ds_axi_rready ;

    assign w_net__AXI_Protocol_Converter_0__ds_axi_wdata = w_port__AXI_Protocol_Converter_0__ds_axi_wdata ;
    assign w_port__AXI_Matrix_0__us0_wdata = w_net__AXI_Protocol_Converter_0__ds_axi_wdata ;

    assign w_net__AXI_Protocol_Converter_0__ds_axi_wstrb = w_port__AXI_Protocol_Converter_0__ds_axi_wstrb ;
    assign w_port__AXI_Matrix_0__us0_wstrb = w_net__AXI_Protocol_Converter_0__ds_axi_wstrb ;

    assign w_net__AXI_Protocol_Converter_0__ds_axi_wvalid = w_port__AXI_Protocol_Converter_0__ds_axi_wvalid ;
    assign w_port__AXI_Matrix_0__us0_wvalid = w_net__AXI_Protocol_Converter_0__ds_axi_wvalid ;

    assign w_net__AXI_Protocol_Converter_0__us_axi_arready = w_port__AXI_Protocol_Converter_0__us_axi_arready ;
    assign w_port__ARM_Processor_System_0__master_gp0_axi_arready = w_net__AXI_Protocol_Converter_0__us_axi_arready ;

    assign w_net__AXI_Protocol_Converter_0__us_axi_awready = w_port__AXI_Protocol_Converter_0__us_axi_awready ;
    assign w_port__ARM_Processor_System_0__master_gp0_axi_awready = w_net__AXI_Protocol_Converter_0__us_axi_awready ;

    assign w_net__AXI_Protocol_Converter_0__us_axi_bid = w_port__AXI_Protocol_Converter_0__us_axi_bid ;
    assign w_port__ARM_Processor_System_0__master_gp0_axi_bid = w_net__AXI_Protocol_Converter_0__us_axi_bid ;

    assign w_net__AXI_Protocol_Converter_0__us_axi_bresp = w_port__AXI_Protocol_Converter_0__us_axi_bresp ;
    assign w_port__ARM_Processor_System_0__master_gp0_axi_bresp = w_net__AXI_Protocol_Converter_0__us_axi_bresp ;

    assign w_net__AXI_Protocol_Converter_0__us_axi_bvalid = w_port__AXI_Protocol_Converter_0__us_axi_bvalid ;
    assign w_port__ARM_Processor_System_0__master_gp0_axi_bvalid = w_net__AXI_Protocol_Converter_0__us_axi_bvalid ;

    assign w_net__AXI_Protocol_Converter_0__us_axi_rdata = w_port__AXI_Protocol_Converter_0__us_axi_rdata ;
    assign w_port__ARM_Processor_System_0__master_gp0_axi_rdata = w_net__AXI_Protocol_Converter_0__us_axi_rdata ;

    assign w_net__AXI_Protocol_Converter_0__us_axi_rid = w_port__AXI_Protocol_Converter_0__us_axi_rid ;
    assign w_port__ARM_Processor_System_0__master_gp0_axi_rid = w_net__AXI_Protocol_Converter_0__us_axi_rid ;

    assign w_net__AXI_Protocol_Converter_0__us_axi_rlast = w_port__AXI_Protocol_Converter_0__us_axi_rlast ;
    assign w_port__ARM_Processor_System_0__master_gp0_axi_rlast = w_net__AXI_Protocol_Converter_0__us_axi_rlast ;

    assign w_net__AXI_Protocol_Converter_0__us_axi_rresp = w_port__AXI_Protocol_Converter_0__us_axi_rresp ;
    assign w_port__ARM_Processor_System_0__master_gp0_axi_rresp = w_net__AXI_Protocol_Converter_0__us_axi_rresp ;

    assign w_net__AXI_Protocol_Converter_0__us_axi_rvalid = w_port__AXI_Protocol_Converter_0__us_axi_rvalid ;
    assign w_port__ARM_Processor_System_0__master_gp0_axi_rvalid = w_net__AXI_Protocol_Converter_0__us_axi_rvalid ;

    assign w_net__AXI_Protocol_Converter_0__us_axi_wready = w_port__AXI_Protocol_Converter_0__us_axi_wready ;
    assign w_port__ARM_Processor_System_0__master_gp0_axi_wready = w_net__AXI_Protocol_Converter_0__us_axi_wready ;

    assign w_net__Concat_0__Dout = w_port__Concat_0__Dout ;
    assign w_port__ARM_Processor_System_0__f2p_irq = {13'b0,w_net__Concat_0__Dout} ;

    assign w_net__Constant_0__dout = w_port__Constant_0__dout ;
    assign w_port__Processor_System_Reset_0__pll_locked = w_net__Constant_0__dout ;
    assign w_port__Processor_System_Reset_0_200__pll_locked = w_net__Constant_0__dout ;

    assign w_net__Constant_1__dout = w_port__Constant_1__dout ;
    assign w_port__video_timing_generator_v01_0__vtg_ce = w_net__Constant_1__dout ;
    assign w_port__ChipWatcher_0__probe4 = w_net__Constant_1__dout ;

    assign w_net__Constant_3__dout = w_port__Constant_3__dout ;
    assign w_port__Processor_System_Reset_0__system_rst = w_net__Constant_3__dout ;
    assign w_port__Processor_System_Reset_0_200__system_rst = w_net__Constant_3__dout ;
    assign w_port__Processor_System_Reset_0__aux_rst = w_net__Constant_3__dout ;
    assign w_port__Processor_System_Reset_0_200__aux_rst = w_net__Constant_3__dout ;

    assign w_net__I_fdma_raddr = I_fdma_raddr ;
    assign w_port__uiFDMA_0__I_fdma_raddr = w_net__I_fdma_raddr ;

    assign w_net__I_fdma_rareq = I_fdma_rareq ;
    assign w_port__uiFDMA_0__I_fdma_rareq = w_net__I_fdma_rareq ;

    assign w_net__I_fdma_rready = I_fdma_rready ;
    assign w_port__uiFDMA_0__I_fdma_rready = w_net__I_fdma_rready ;

    assign w_net__I_fdma_rsize = I_fdma_rsize ;
    assign w_port__uiFDMA_0__I_fdma_rsize = w_net__I_fdma_rsize ;

    assign w_net__I_fdma_waddr = I_fdma_waddr ;
    assign w_port__uiFDMA_0__I_fdma_waddr = w_net__I_fdma_waddr ;

    assign w_net__I_fdma_wareq = I_fdma_wareq ;
    assign w_port__uiFDMA_0__I_fdma_wareq = w_net__I_fdma_wareq ;

    assign w_net__I_fdma_wdata = I_fdma_wdata ;
    assign w_port__uiFDMA_0__I_fdma_wdata = w_net__I_fdma_wdata ;

    assign w_net__I_fdma_wready = I_fdma_wready ;
    assign w_port__uiFDMA_0__I_fdma_wready = w_net__I_fdma_wready ;

    assign w_net__I_fdma_wsize = I_fdma_wsize ;
    assign w_port__uiFDMA_0__I_fdma_wsize = w_net__I_fdma_wsize ;

    assign w_net__I_irq2 = I_irq2 | f3p_coco_irq ;
    assign w_port__Concat_0__In2 = w_net__I_irq2 ;

    assign w_net__I_mwdata = I_mwdata ;
    assign w_port__AXI_ERAM_Controller_0__mem_dout = w_net__I_mwdata ;

    assign w_net__I_pixel_clk = I_pixel_clk ;
    assign w_port__uivtc_0__I_vtc_clk = w_net__I_pixel_clk ;
    assign w_port__uivbuf_0__I_R_rclk = w_net__I_pixel_clk ;
    assign w_port__uihdmi_tx_0__I_pixel_clk = w_net__I_pixel_clk ;

    assign w_net__I_serial_clk = I_serial_clk ;
    assign w_port__uihdmi_tx_0__I_serial_clk = w_net__I_serial_clk ;

    assign w_net__Processor_System_Reset_0_200__peripheral_aresetn = w_port__Processor_System_Reset_0_200__peripheral_aresetn ;
    assign O_ui_rstn = w_net__Processor_System_Reset_0_200__peripheral_aresetn ;
    assign w_port__uiFDMA_0__M_AXI_ARESETN = w_net__Processor_System_Reset_0_200__peripheral_aresetn ;

    assign w_net__Processor_System_Reset_0__peripheral_aresetn = w_port__Processor_System_Reset_0__peripheral_aresetn ;
    assign O_mrstn = w_net__Processor_System_Reset_0__peripheral_aresetn ;
    assign w_port__AXI_Matrix_0__aresetn = w_net__Processor_System_Reset_0__peripheral_aresetn ;
    assign w_port__VDMA_0__resetn = w_net__Processor_System_Reset_0__peripheral_aresetn ;
    assign w_port__AXI_ERAM_Controller_0__aresetn = w_net__Processor_System_Reset_0__peripheral_aresetn ;
    assign w_port__video_timing_generator_v01_0__arst_n = w_net__Processor_System_Reset_0__peripheral_aresetn ;
    assign w_port__AXI_Protocol_Converter_0__aresetn = w_net__Processor_System_Reset_0__peripheral_aresetn ;
    assign w_port__uivbuf_0__I_ui_rstn = w_net__Processor_System_Reset_0__peripheral_aresetn ;

    assign w_net__Utility_Vector_Logic_0__result_vector = w_port__Utility_Vector_Logic_0__result_vector ;
    assign w_port__uihdmi_tx_0__I_rst = w_net__Utility_Vector_Logic_0__result_vector ;

    assign w_net__VDMA_0__axi_lite_arready = w_port__VDMA_0__axi_lite_arready ;
    assign w_port__AXI_Matrix_0__ds0_arready = w_net__VDMA_0__axi_lite_arready ;

    assign w_net__VDMA_0__axi_lite_awready = w_port__VDMA_0__axi_lite_awready ;
    assign w_port__AXI_Matrix_0__ds0_awready = w_net__VDMA_0__axi_lite_awready ;

    assign w_net__VDMA_0__axi_lite_bresp = w_port__VDMA_0__axi_lite_bresp ;
    assign w_port__AXI_Matrix_0__ds0_bresp = w_net__VDMA_0__axi_lite_bresp ;

    assign w_net__VDMA_0__axi_lite_bvalid = w_port__VDMA_0__axi_lite_bvalid ;
    assign w_port__AXI_Matrix_0__ds0_bvalid = w_net__VDMA_0__axi_lite_bvalid ;

    assign w_net__VDMA_0__axi_lite_rdata = w_port__VDMA_0__axi_lite_rdata ;
    assign w_port__AXI_Matrix_0__ds0_rdata = w_net__VDMA_0__axi_lite_rdata ;

    assign w_net__VDMA_0__axi_lite_rresp = w_port__VDMA_0__axi_lite_rresp ;
    assign w_port__AXI_Matrix_0__ds0_rresp = w_net__VDMA_0__axi_lite_rresp ;

    assign w_net__VDMA_0__axi_lite_rvalid = w_port__VDMA_0__axi_lite_rvalid ;
    assign w_port__AXI_Matrix_0__ds0_rvalid = w_net__VDMA_0__axi_lite_rvalid ;

    assign w_net__VDMA_0__axi_lite_wready = w_port__VDMA_0__axi_lite_wready ;
    assign w_port__AXI_Matrix_0__ds0_wready = w_net__VDMA_0__axi_lite_wready ;

    assign w_net__VDMA_0__m_axi_mm2s_araddr = w_port__VDMA_0__m_axi_mm2s_araddr ;
    assign w_port__ARM_Processor_System_0__slave_hp1_axi_araddr = {1'b0,w_net__VDMA_0__m_axi_mm2s_araddr} ;

    assign w_net__VDMA_0__m_axi_mm2s_arburst = w_port__VDMA_0__m_axi_mm2s_arburst ;
    assign w_port__ARM_Processor_System_0__slave_hp1_axi_arburst = w_net__VDMA_0__m_axi_mm2s_arburst ;

    assign w_net__VDMA_0__m_axi_mm2s_arcache = w_port__VDMA_0__m_axi_mm2s_arcache ;
    assign w_port__ARM_Processor_System_0__slave_hp1_axi_arcache = w_net__VDMA_0__m_axi_mm2s_arcache ;

    assign w_net__VDMA_0__m_axi_mm2s_arlen = w_port__VDMA_0__m_axi_mm2s_arlen ;
    assign w_port__ARM_Processor_System_0__slave_hp1_axi_arlen = w_net__VDMA_0__m_axi_mm2s_arlen ;

    assign w_net__VDMA_0__m_axi_mm2s_arprot = w_port__VDMA_0__m_axi_mm2s_arprot ;
    assign w_port__ARM_Processor_System_0__slave_hp1_axi_arprot = w_net__VDMA_0__m_axi_mm2s_arprot ;

    assign w_net__VDMA_0__m_axi_mm2s_arsize = w_port__VDMA_0__m_axi_mm2s_arsize ;
    assign w_port__ARM_Processor_System_0__slave_hp1_axi_arsize = w_net__VDMA_0__m_axi_mm2s_arsize ;

    assign w_net__VDMA_0__m_axi_mm2s_arvalid = w_port__VDMA_0__m_axi_mm2s_arvalid ;
    assign w_port__ARM_Processor_System_0__slave_hp1_axi_arvalid = w_net__VDMA_0__m_axi_mm2s_arvalid ;

    assign w_net__VDMA_0__m_axi_mm2s_rready = w_port__VDMA_0__m_axi_mm2s_rready ;
    camera_axi_read_skid #(.WIDTH(67)) camera_linux_r_skid(
      .clk(w_port__VDMA_0__m_axi_mm2s_aclk),.rst_n(w_port__VDMA_0__resetn),
      .s_valid(w_net__ARM_Processor_System_0__slave_hp1_axi_rvalid),
      .s_ready(w_port__ARM_Processor_System_0__slave_hp1_axi_rready),
      .s_data({w_net__ARM_Processor_System_0__slave_hp1_axi_rresp,w_net__ARM_Processor_System_0__slave_hp1_axi_rlast,w_net__ARM_Processor_System_0__slave_hp1_axi_rdata}),
      .m_valid(w_port__VDMA_0__m_axi_mm2s_rvalid),.m_ready(w_net__VDMA_0__m_axi_mm2s_rready),
      .m_data({w_port__VDMA_0__m_axi_mm2s_rresp,w_port__VDMA_0__m_axi_mm2s_rlast,w_port__VDMA_0__m_axi_mm2s_rdata}));

    assign w_net__VDMA_0__m_axis_mm2s_tdata = w_port__VDMA_0__m_axis_mm2s_tdata ;
    assign w_port__uivbuf_0__I_mm2s_tdata = w_net__VDMA_0__m_axis_mm2s_tdata ;

    assign w_net__VDMA_0__m_axis_mm2s_tlast = w_port__VDMA_0__m_axis_mm2s_tlast ;
    assign w_port__uivbuf_0__I_mm2s_tlast = w_net__VDMA_0__m_axis_mm2s_tlast ;

    assign w_net__VDMA_0__m_axis_mm2s_tuser = w_port__VDMA_0__m_axis_mm2s_tuser ;
    assign w_port__uivbuf_0__I_mm2s_tuser = w_net__VDMA_0__m_axis_mm2s_tuser ;

    assign w_net__VDMA_0__m_axis_mm2s_tvalid = w_port__VDMA_0__m_axis_mm2s_tvalid ;
    assign w_port__uivbuf_0__I_mm2s_tvalid = w_net__VDMA_0__m_axis_mm2s_tvalid ;

    assign w_net__VDMA_0__mm2s_introut = w_port__VDMA_0__mm2s_introut ;
    assign w_port__Concat_0__In0 = w_net__VDMA_0__mm2s_introut ;

    assign w_net__VDMA_0__s2mm_introut = w_port__VDMA_0__s2mm_introut ;
    assign w_port__Concat_0__In1 = w_net__VDMA_0__s2mm_introut ;

    assign w_net__uiFDMA_0__M_AXI_ARADDR = w_port__uiFDMA_0__M_AXI_ARADDR ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_araddr = {1'b0,w_net__uiFDMA_0__M_AXI_ARADDR} ;

    assign w_net__uiFDMA_0__M_AXI_ARBURST = w_port__uiFDMA_0__M_AXI_ARBURST ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_arburst = w_net__uiFDMA_0__M_AXI_ARBURST ;

    assign w_net__uiFDMA_0__M_AXI_ARCACHE = w_port__uiFDMA_0__M_AXI_ARCACHE ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_arcache = w_net__uiFDMA_0__M_AXI_ARCACHE ;

    assign w_net__uiFDMA_0__M_AXI_ARID = w_port__uiFDMA_0__M_AXI_ARID ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_arid = w_net__uiFDMA_0__M_AXI_ARID ;

    assign w_net__uiFDMA_0__M_AXI_ARLEN = w_port__uiFDMA_0__M_AXI_ARLEN ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_arlen = w_net__uiFDMA_0__M_AXI_ARLEN ;

    assign w_net__uiFDMA_0__M_AXI_ARLOCK = w_port__uiFDMA_0__M_AXI_ARLOCK ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_arlock = w_net__uiFDMA_0__M_AXI_ARLOCK ;

    assign w_net__uiFDMA_0__M_AXI_ARPROT = w_port__uiFDMA_0__M_AXI_ARPROT ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_arprot = w_net__uiFDMA_0__M_AXI_ARPROT ;

    assign w_net__uiFDMA_0__M_AXI_ARQOS = w_port__uiFDMA_0__M_AXI_ARQOS ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_arqos = w_net__uiFDMA_0__M_AXI_ARQOS ;

    assign w_net__uiFDMA_0__M_AXI_ARSIZE = w_port__uiFDMA_0__M_AXI_ARSIZE ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_arsize = w_net__uiFDMA_0__M_AXI_ARSIZE ;

    assign w_net__uiFDMA_0__M_AXI_ARVALID = w_port__uiFDMA_0__M_AXI_ARVALID ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_arvalid = w_net__uiFDMA_0__M_AXI_ARVALID ;

    assign w_net__uiFDMA_0__M_AXI_AWADDR = w_port__uiFDMA_0__M_AXI_AWADDR ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_awaddr = {1'b0,w_net__uiFDMA_0__M_AXI_AWADDR} ;

    assign w_net__uiFDMA_0__M_AXI_AWBURST = w_port__uiFDMA_0__M_AXI_AWBURST ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_awburst = w_net__uiFDMA_0__M_AXI_AWBURST ;

    assign w_net__uiFDMA_0__M_AXI_AWCACHE = w_port__uiFDMA_0__M_AXI_AWCACHE ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_awcache = w_net__uiFDMA_0__M_AXI_AWCACHE ;

    assign w_net__uiFDMA_0__M_AXI_AWID = w_port__uiFDMA_0__M_AXI_AWID ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_awid = w_net__uiFDMA_0__M_AXI_AWID ;

    assign w_net__uiFDMA_0__M_AXI_AWLEN = w_port__uiFDMA_0__M_AXI_AWLEN ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_awlen = w_net__uiFDMA_0__M_AXI_AWLEN ;

    assign w_net__uiFDMA_0__M_AXI_AWLOCK = w_port__uiFDMA_0__M_AXI_AWLOCK ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_awlock = w_net__uiFDMA_0__M_AXI_AWLOCK ;

    assign w_net__uiFDMA_0__M_AXI_AWPROT = w_port__uiFDMA_0__M_AXI_AWPROT ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_awprot = w_net__uiFDMA_0__M_AXI_AWPROT ;

    assign w_net__uiFDMA_0__M_AXI_AWQOS = w_port__uiFDMA_0__M_AXI_AWQOS ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_awqos = w_net__uiFDMA_0__M_AXI_AWQOS ;

    assign w_net__uiFDMA_0__M_AXI_AWSIZE = w_port__uiFDMA_0__M_AXI_AWSIZE ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_awsize = w_net__uiFDMA_0__M_AXI_AWSIZE ;

    assign w_net__uiFDMA_0__M_AXI_AWVALID = w_port__uiFDMA_0__M_AXI_AWVALID ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_awvalid = w_net__uiFDMA_0__M_AXI_AWVALID ;

    assign w_net__uiFDMA_0__M_AXI_BREADY = w_port__uiFDMA_0__M_AXI_BREADY ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_bready = w_net__uiFDMA_0__M_AXI_BREADY ;

    assign w_net__uiFDMA_0__M_AXI_RREADY = w_port__uiFDMA_0__M_AXI_RREADY ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_rready = w_net__uiFDMA_0__M_AXI_RREADY ;

    assign w_net__uiFDMA_0__M_AXI_WDATA = w_port__uiFDMA_0__M_AXI_WDATA ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_wdata = w_net__uiFDMA_0__M_AXI_WDATA ;

    assign w_net__uiFDMA_0__M_AXI_WLAST = w_port__uiFDMA_0__M_AXI_WLAST ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_wlast = w_net__uiFDMA_0__M_AXI_WLAST ;

    assign w_net__uiFDMA_0__M_AXI_WSTRB = w_port__uiFDMA_0__M_AXI_WSTRB ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_wstrb = w_net__uiFDMA_0__M_AXI_WSTRB ;

    assign w_net__uiFDMA_0__M_AXI_WVALID = w_port__uiFDMA_0__M_AXI_WVALID ;
    assign w_port__ARM_Processor_System_0__slave_hp0_axi_wvalid = w_net__uiFDMA_0__M_AXI_WVALID ;

    assign w_net__uiFDMA_0__O_fdma_rbusy = w_port__uiFDMA_0__O_fdma_rbusy ;
    assign O_fdma_rbusy = w_net__uiFDMA_0__O_fdma_rbusy ;

    assign w_net__uiFDMA_0__O_fdma_rdata = w_port__uiFDMA_0__O_fdma_rdata ;
    assign O_fdma_rdata = w_net__uiFDMA_0__O_fdma_rdata ;

    assign w_net__uiFDMA_0__O_fdma_rvalid = w_port__uiFDMA_0__O_fdma_rvalid ;
    assign O_fdma_rvalid = w_net__uiFDMA_0__O_fdma_rvalid ;

    assign w_net__uiFDMA_0__O_fdma_wbusy = w_port__uiFDMA_0__O_fdma_wbusy ;
    assign O_dma_debug = {1'b0,w_port__uiFDMA_0__M_AXI_RRESP,w_port__uiFDMA_0__M_AXI_BRESP,w_port__uiFDMA_0__M_AXI_RLAST,w_port__uiFDMA_0__M_AXI_RREADY,w_port__uiFDMA_0__M_AXI_RVALID,w_port__uiFDMA_0__M_AXI_ARREADY,w_port__uiFDMA_0__M_AXI_ARVALID,w_port__uiFDMA_0__M_AXI_BREADY,w_port__uiFDMA_0__M_AXI_BVALID,w_port__uiFDMA_0__M_AXI_WREADY,w_port__uiFDMA_0__M_AXI_WVALID,w_port__uiFDMA_0__M_AXI_AWREADY,w_port__uiFDMA_0__M_AXI_AWVALID};
    assign O_fdma_wbusy = w_net__uiFDMA_0__O_fdma_wbusy ;

    assign w_net__uiFDMA_0__O_fdma_wvalid = w_port__uiFDMA_0__O_fdma_wvalid ;
    assign O_fdma_wvalid = w_net__uiFDMA_0__O_fdma_wvalid ;

    assign w_net__uihdmi_tx_0__O_hdmi_clk_p = w_port__uihdmi_tx_0__O_hdmi_clk_p ;
    assign O_hdmi_clk_p = w_net__uihdmi_tx_0__O_hdmi_clk_p ;

    assign w_net__uihdmi_tx_0__O_hdmi_tx_p = w_port__uihdmi_tx_0__O_hdmi_tx_p ;
    assign O_hdmi_tx_p = w_net__uihdmi_tx_0__O_hdmi_tx_p ;

    assign w_net__uivbuf_0__O_R_tdata = w_port__uivbuf_0__O_R_tdata ;
    wire camera_linux_consume;
    camera_display_mux camera_presentation(
      .pixel_clk(I_pixel_clk),.rst_n(O_mrstn),.window_ink(I_cam_window_ink),.request(I_cam_display),
      .vs(w_net__uivtc_0__O_vtc_vs),.de(w_net__uivtc_0__O_vtc_de_valid),
      .linux_pixel(w_net__uivbuf_0__O_R_tdata),.camera_pixel(I_cam_pixel),
      .pixel(w_port__uihdmi_tx_0__I_video_in_data),.linux_consume(camera_linux_consume));
    reg[16:0] linux_lines,linux_lines_gray;
    always @(posedge w_net__ARM_Processor_System_0__p2f_clk0 or negedge O_mrstn)begin
      if(!O_mrstn)begin linux_lines<=0;linux_lines_gray<=0;end
      else begin
       if(w_net__VDMA_0__m_axis_mm2s_tvalid&&w_net__uivbuf_0__O_mm2s_tready&&w_net__VDMA_0__m_axis_mm2s_tlast)linux_lines<=linux_lines+1;
       linux_lines_gray<=(linux_lines>>1)^linux_lines;
      end
    end
    assign O_linux_line_gray=linux_lines_gray;
    assign O_camera_de=w_net__uivtc_0__O_vtc_de_valid;
    assign O_camera_vs=w_net__uivtc_0__O_vtc_vs;

    assign w_net__uivbuf_0__O_R_tlocked = w_port__uivbuf_0__O_R_tlocked ;
    assign w_port__Utility_Vector_Logic_0__vector_a = w_net__uivbuf_0__O_R_tlocked ;
    assign w_port__uivtc_0__I_vtc_rstn = w_net__uivbuf_0__O_R_tlocked ;

    assign w_net__uivbuf_0__O_mm2s_tready = w_port__uivbuf_0__O_mm2s_tready ;
    assign w_port__VDMA_0__m_axis_mm2s_tready = w_net__uivbuf_0__O_mm2s_tready ;

    assign w_net__uivtc_0__O_vtc_de_valid = w_port__uivtc_0__O_vtc_de_valid ;
    assign w_port__uivbuf_0__I_R_tready = camera_linux_consume ;
    assign w_port__uihdmi_tx_0__I_video_in_de = w_net__uivtc_0__O_vtc_de_valid ;

    assign w_net__uivtc_0__O_vtc_hs = w_port__uivtc_0__O_vtc_hs ;
    assign w_port__uihdmi_tx_0__I_video_in_hs = w_net__uivtc_0__O_vtc_hs ;

    assign w_net__uivtc_0__O_vtc_vs = w_port__uivtc_0__O_vtc_vs ;
    assign w_port__uivbuf_0__I_R_sync = w_net__uivtc_0__O_vtc_vs ;
    assign w_port__uihdmi_tx_0__I_video_in_vs = w_net__uivtc_0__O_vtc_vs ;

    assign w_net__video_timing_generator_v01_0__s_axi_arready = w_port__video_timing_generator_v01_0__s_axi_arready ;
    assign w_port__AXI_Matrix_0__ds1_arready = w_net__video_timing_generator_v01_0__s_axi_arready ;

    assign w_net__video_timing_generator_v01_0__s_axi_awready = w_port__video_timing_generator_v01_0__s_axi_awready ;
    assign w_port__AXI_Matrix_0__ds1_awready = w_net__video_timing_generator_v01_0__s_axi_awready ;

    assign w_net__video_timing_generator_v01_0__s_axi_bresp = w_port__video_timing_generator_v01_0__s_axi_bresp ;
    assign w_port__AXI_Matrix_0__ds1_bresp = w_net__video_timing_generator_v01_0__s_axi_bresp ;

    assign w_net__video_timing_generator_v01_0__s_axi_bvalid = w_port__video_timing_generator_v01_0__s_axi_bvalid ;
    assign w_port__AXI_Matrix_0__ds1_bvalid = w_net__video_timing_generator_v01_0__s_axi_bvalid ;

    assign w_net__video_timing_generator_v01_0__s_axi_rdata = w_port__video_timing_generator_v01_0__s_axi_rdata ;
    assign w_port__AXI_Matrix_0__ds1_rdata = w_net__video_timing_generator_v01_0__s_axi_rdata ;

    assign w_net__video_timing_generator_v01_0__s_axi_rresp = w_port__video_timing_generator_v01_0__s_axi_rresp ;
    assign w_port__AXI_Matrix_0__ds1_rresp = w_net__video_timing_generator_v01_0__s_axi_rresp ;

    assign w_net__video_timing_generator_v01_0__s_axi_rvalid = w_port__video_timing_generator_v01_0__s_axi_rvalid ;
    assign w_port__AXI_Matrix_0__ds1_rvalid = w_net__video_timing_generator_v01_0__s_axi_rvalid ;

    assign w_net__video_timing_generator_v01_0__s_axi_wready = w_port__video_timing_generator_v01_0__s_axi_wready ;
    assign w_port__AXI_Matrix_0__ds1_wready = w_net__video_timing_generator_v01_0__s_axi_wready ;

    assign w_net__video_timing_generator_v01_0__vtg_active_video = w_port__video_timing_generator_v01_0__vtg_active_video ;
    assign w_port__ChipWatcher_0__probe1 = w_net__video_timing_generator_v01_0__vtg_active_video ;

    assign w_net__video_timing_generator_v01_0__vtg_pclk = w_port__video_timing_generator_v01_0__vtg_pclk ;
    assign w_port__ChipWatcher_0__probe3 = w_net__video_timing_generator_v01_0__vtg_pclk ;

    assign w_net__video_timing_generator_v01_0__vtg_pclk_locked = w_port__video_timing_generator_v01_0__vtg_pclk_locked ;
    assign w_port__ChipWatcher_0__probe0 = w_net__video_timing_generator_v01_0__vtg_pclk_locked ;

    assign w_net__video_timing_generator_v01_0__vtg_vsync = w_port__video_timing_generator_v01_0__vtg_vsync ;
    assign w_port__ChipWatcher_0__probe2 = w_net__video_timing_generator_v01_0__vtg_vsync ;










// Isolated COCO candidate integration.
wire [11:0] f3p_gp_awid;
wire [11:0] f3p_gp_arid;
wire [32:0] f3p_gp_awaddr;
wire [32:0] f3p_gp_araddr;
wire [3:0] f3p_gp_awlen;
wire [3:0] f3p_gp_arlen;
wire [1:0] f3p_gp_awsize;
wire [1:0] f3p_gp_arsize;
wire [1:0] f3p_gp_awburst;
wire [1:0] f3p_gp_arburst;
wire f3p_gp_awlock;
wire f3p_gp_arlock;
wire [2:0] f3p_gp_awprot;
wire [2:0] f3p_gp_arprot;
wire f3p_gp_awvalid;
wire f3p_gp_arvalid;
wire f3p_gp_awready;
wire f3p_gp_arready;
wire [31:0] f3p_gp_wdata;
wire [3:0] f3p_gp_wstrb;
wire f3p_gp_wvalid;
wire f3p_gp_wready;
wire [11:0] f3p_gp_bid;
wire [11:0] f3p_gp_rid;
wire [1:0] f3p_gp_bresp;
wire [1:0] f3p_gp_rresp;
wire f3p_gp_bvalid;
wire f3p_gp_rvalid;
wire f3p_gp_rlast;
wire f3p_gp_bready;
wire f3p_gp_rready;
wire [31:0] f3p_gp_rdata;
wire [5:0] f3p_hp_awid;
wire [5:0] f3p_hp_arid;
wire [32:0] f3p_hp_awaddr;
wire [32:0] f3p_hp_araddr;
wire [3:0] f3p_hp_awlen;
wire [3:0] f3p_hp_arlen;
wire [1:0] f3p_hp_awsize;
wire [1:0] f3p_hp_arsize;
wire [1:0] f3p_hp_awburst;
wire [1:0] f3p_hp_arburst;
wire f3p_hp_awlock;
wire f3p_hp_arlock;
wire [2:0] f3p_hp_awprot;
wire [2:0] f3p_hp_arprot;
wire f3p_hp_awvalid;
wire f3p_hp_arvalid;
wire f3p_hp_awready;
wire f3p_hp_arready;
wire [63:0] f3p_hp_wdata;
wire [7:0] f3p_hp_wstrb;
wire f3p_hp_wvalid;
wire f3p_hp_wready;
wire [5:0] f3p_hp_bid;
wire [5:0] f3p_hp_rid;
wire [1:0] f3p_hp_bresp;
wire [1:0] f3p_hp_rresp;
wire f3p_hp_bvalid;
wire f3p_hp_rvalid;
wire f3p_hp_rlast;
wire f3p_hp_bready;
wire f3p_hp_rready;
wire [63:0] f3p_hp_rdata;
wire [3:0] f3p_hp_awcache;
wire [3:0] f3p_hp_arcache;
wire f3p_hp_wlast;
wire [32:0] f3p_cfg_awaddr;
wire [32:0] f3p_cfg_araddr;
wire [2:0] f3p_cfg_awprot;
wire [2:0] f3p_cfg_arprot;
wire f3p_cfg_awvalid;
wire f3p_cfg_arvalid;
wire f3p_cfg_awready;
wire f3p_cfg_arready;
wire [31:0] f3p_cfg_wdata;
wire [3:0] f3p_cfg_wstrb;
wire f3p_cfg_wvalid;
wire f3p_cfg_wready;
wire [1:0] f3p_cfg_bresp;
wire [1:0] f3p_cfg_rresp;
wire f3p_cfg_bvalid;
wire f3p_cfg_rvalid;
wire f3p_cfg_bready;
wire f3p_cfg_rready;
wire [31:0] f3p_cfg_rdata;
wire [5:0] f3p_nn_awid;
wire [5:0] f3p_nn_arid;
wire [32:0] f3p_nn_awaddr;
wire [32:0] f3p_nn_araddr;
wire [3:0] f3p_nn_awlen;
wire [3:0] f3p_nn_arlen;
wire [1:0] f3p_nn_awsize;
wire [1:0] f3p_nn_arsize;
wire [1:0] f3p_nn_awburst;
wire [1:0] f3p_nn_arburst;
wire f3p_nn_awlock;
wire f3p_nn_arlock;
wire [2:0] f3p_nn_awprot;
wire [2:0] f3p_nn_arprot;
wire f3p_nn_awvalid;
wire f3p_nn_arvalid;
wire f3p_nn_awready;
wire f3p_nn_arready;
wire [63:0] f3p_nn_wdata;
wire [7:0] f3p_nn_wstrb;
wire f3p_nn_wvalid;
wire f3p_nn_wready;
wire [5:0] f3p_nn_bid;
wire [5:0] f3p_nn_rid;
wire [1:0] f3p_nn_bresp;
wire [1:0] f3p_nn_rresp;
wire f3p_nn_bvalid;
wire f3p_nn_rvalid;
wire f3p_nn_rlast;
wire f3p_nn_bready;
wire f3p_nn_rready;
wire [63:0] f3p_nn_rdata;
wire [3:0] f3p_nn_awcache;
wire [3:0] f3p_nn_arcache;
wire f3p_nn_wlast;
wire [5:0] f3p_nn_hp_awid;
wire [5:0] f3p_nn_hp_arid;
wire [32:0] f3p_nn_hp_awaddr;
wire [32:0] f3p_nn_hp_araddr;
wire [3:0] f3p_nn_hp_awlen;
wire [3:0] f3p_nn_hp_arlen;
wire [1:0] f3p_nn_hp_awsize;
wire [1:0] f3p_nn_hp_arsize;
wire [1:0] f3p_nn_hp_awburst;
wire [1:0] f3p_nn_hp_arburst;
wire f3p_nn_hp_awlock;
wire f3p_nn_hp_arlock;
wire [2:0] f3p_nn_hp_awprot;
wire [2:0] f3p_nn_hp_arprot;
wire f3p_nn_hp_awvalid;
wire f3p_nn_hp_arvalid;
wire f3p_nn_hp_awready;
wire f3p_nn_hp_arready;
wire [63:0] f3p_nn_hp_wdata;
wire [7:0] f3p_nn_hp_wstrb;
wire f3p_nn_hp_wvalid;
wire f3p_nn_hp_wready;
wire [5:0] f3p_nn_hp_bid;
wire [5:0] f3p_nn_hp_rid;
wire [1:0] f3p_nn_hp_bresp;
wire [1:0] f3p_nn_hp_rresp;
wire f3p_nn_hp_bvalid;
wire f3p_nn_hp_rvalid;
wire f3p_nn_hp_rlast;
wire f3p_nn_hp_bready;
wire f3p_nn_hp_rready;
wire [63:0] f3p_nn_hp_rdata;
wire [3:0] f3p_nn_hp_awcache;
wire [3:0] f3p_nn_hp_arcache;
wire f3p_nn_hp_wlast;
reg [1:0] f3p_coco_hp_reset_sync;
wire f3p_coco_hp_rst_n;
wire f3p_coco_irq;
wire [7:0] f3p_nn_cdc_awlen;
wire [7:0] f3p_nn_cdc_arlen;
wire [2:0] f3p_nn_cdc_awsize;
wire [2:0] f3p_nn_cdc_arsize;
f3p_gp1_softnpu_bridge u_coco_gp1 (
 .clk(O_mclk),
 .rst_n(O_mrstn),
 .s_awid(f3p_gp_awid),
 .s_arid(f3p_gp_arid),
 .s_awaddr(f3p_gp_awaddr),
 .s_araddr(f3p_gp_araddr),
 .s_awlen(f3p_gp_awlen),
 .s_arlen(f3p_gp_arlen),
 .s_awsize(f3p_gp_awsize),
 .s_arsize(f3p_gp_arsize),
 .s_awburst(f3p_gp_awburst),
 .s_arburst(f3p_gp_arburst),
 .s_awlock(f3p_gp_awlock),
 .s_arlock(f3p_gp_arlock),
 .s_awprot(f3p_gp_awprot),
 .s_arprot(f3p_gp_arprot),
 .s_awvalid(f3p_gp_awvalid),
 .s_arvalid(f3p_gp_arvalid),
 .s_awready(f3p_gp_awready),
 .s_arready(f3p_gp_arready),
 .s_wdata(f3p_gp_wdata),
 .s_wstrb(f3p_gp_wstrb),
 .s_wvalid(f3p_gp_wvalid),
 .s_wready(f3p_gp_wready),
 .s_bid(f3p_gp_bid),
 .s_rid(f3p_gp_rid),
 .s_bresp(f3p_gp_bresp),
 .s_rresp(f3p_gp_rresp),
 .s_bvalid(f3p_gp_bvalid),
 .s_rvalid(f3p_gp_rvalid),
 .s_rlast(f3p_gp_rlast),
 .s_bready(f3p_gp_bready),
 .s_rready(f3p_gp_rready),
 .s_rdata(f3p_gp_rdata),
 .m0_awid(w_port__ARM_Processor_System_0__master_gp1_axi_awid),
 .m0_arid(w_port__ARM_Processor_System_0__master_gp1_axi_arid),
 .m0_awaddr(w_port__ARM_Processor_System_0__master_gp1_axi_awaddr),
 .m0_araddr(w_port__ARM_Processor_System_0__master_gp1_axi_araddr),
 .m0_awlen(w_port__ARM_Processor_System_0__master_gp1_axi_awlen),
 .m0_arlen(w_port__ARM_Processor_System_0__master_gp1_axi_arlen),
 .m0_awsize(w_port__ARM_Processor_System_0__master_gp1_axi_awsize),
 .m0_arsize(w_port__ARM_Processor_System_0__master_gp1_axi_arsize),
 .m0_awburst(w_port__ARM_Processor_System_0__master_gp1_axi_awburst),
 .m0_arburst(w_port__ARM_Processor_System_0__master_gp1_axi_arburst),
 .m0_awlock(w_port__ARM_Processor_System_0__master_gp1_axi_awlock),
 .m0_arlock(w_port__ARM_Processor_System_0__master_gp1_axi_arlock),
 .m0_awvalid(w_port__ARM_Processor_System_0__master_gp1_axi_awvalid),
 .m0_arvalid(w_port__ARM_Processor_System_0__master_gp1_axi_arvalid),
 .m0_awready(w_port__ARM_Processor_System_0__master_gp1_axi_awready),
 .m0_arready(w_port__ARM_Processor_System_0__master_gp1_axi_arready),
 .m0_wdata(w_port__ARM_Processor_System_0__master_gp1_axi_wdata),
 .m0_wstrb(w_port__ARM_Processor_System_0__master_gp1_axi_wstrb),
 .m0_wvalid(w_port__ARM_Processor_System_0__master_gp1_axi_wvalid),
 .m0_wready(w_port__ARM_Processor_System_0__master_gp1_axi_wready),
 .m0_bid(w_port__ARM_Processor_System_0__master_gp1_axi_bid),
 .m0_rid(w_port__ARM_Processor_System_0__master_gp1_axi_rid),
 .m0_bresp(w_port__ARM_Processor_System_0__master_gp1_axi_bresp),
 .m0_rresp(w_port__ARM_Processor_System_0__master_gp1_axi_rresp),
 .m0_bvalid(w_port__ARM_Processor_System_0__master_gp1_axi_bvalid),
 .m0_rvalid(w_port__ARM_Processor_System_0__master_gp1_axi_rvalid),
 .m0_rlast(w_port__ARM_Processor_System_0__master_gp1_axi_rlast),
 .m0_bready(w_port__ARM_Processor_System_0__master_gp1_axi_bready),
 .m0_rready(w_port__ARM_Processor_System_0__master_gp1_axi_rready),
 .m0_rdata(w_port__ARM_Processor_System_0__master_gp1_axi_rdata),
 .m1_awaddr(f3p_cfg_awaddr),
 .m1_araddr(f3p_cfg_araddr),
 .m1_awprot(f3p_cfg_awprot),
 .m1_arprot(f3p_cfg_arprot),
 .m1_awvalid(f3p_cfg_awvalid),
 .m1_arvalid(f3p_cfg_arvalid),
 .m1_awready(f3p_cfg_awready),
 .m1_arready(f3p_cfg_arready),
 .m1_wdata(f3p_cfg_wdata),
 .m1_wstrb(f3p_cfg_wstrb),
 .m1_wvalid(f3p_cfg_wvalid),
 .m1_wready(f3p_cfg_wready),
 .m1_bresp(f3p_cfg_bresp),
 .m1_rresp(f3p_cfg_rresp),
 .m1_bvalid(f3p_cfg_bvalid),
 .m1_rvalid(f3p_cfg_rvalid),
 .m1_bready(f3p_cfg_bready),
 .m1_rready(f3p_cfg_rready),
 .m1_rdata(f3p_cfg_rdata)
);
f3p_axi_arbiter #(.SIZE_W(2)) u_coco_ddr (
 .clk(O_ui_clk),
 .rst_n(f3p_coco_hp_rst_n),
 .s_awid({f3p_nn_hp_awid,w_port__ARM_Processor_System_0__slave_hp0_axi_awid}),
 .s_arid({f3p_nn_hp_arid,w_port__ARM_Processor_System_0__slave_hp0_axi_arid}),
 .s_awaddr({f3p_nn_hp_awaddr,w_port__ARM_Processor_System_0__slave_hp0_axi_awaddr}),
 .s_araddr({f3p_nn_hp_araddr,w_port__ARM_Processor_System_0__slave_hp0_axi_araddr}),
 .s_awlen({f3p_nn_hp_awlen,w_port__ARM_Processor_System_0__slave_hp0_axi_awlen}),
 .s_arlen({f3p_nn_hp_arlen,w_port__ARM_Processor_System_0__slave_hp0_axi_arlen}),
 .s_awsize({f3p_nn_hp_awsize,w_port__ARM_Processor_System_0__slave_hp0_axi_awsize}),
 .s_arsize({f3p_nn_hp_arsize,w_port__ARM_Processor_System_0__slave_hp0_axi_arsize}),
 .s_awburst({f3p_nn_hp_awburst,w_port__ARM_Processor_System_0__slave_hp0_axi_awburst}),
 .s_arburst({f3p_nn_hp_arburst,w_port__ARM_Processor_System_0__slave_hp0_axi_arburst}),
 .s_awlock({f3p_nn_hp_awlock,w_port__ARM_Processor_System_0__slave_hp0_axi_awlock}),
 .s_arlock({f3p_nn_hp_arlock,w_port__ARM_Processor_System_0__slave_hp0_axi_arlock}),
 .s_awprot({f3p_nn_hp_awprot,w_port__ARM_Processor_System_0__slave_hp0_axi_awprot}),
 .s_arprot({f3p_nn_hp_arprot,w_port__ARM_Processor_System_0__slave_hp0_axi_arprot}),
 .s_awvalid({f3p_nn_hp_awvalid,w_port__ARM_Processor_System_0__slave_hp0_axi_awvalid}),
 .s_arvalid({f3p_nn_hp_arvalid,w_port__ARM_Processor_System_0__slave_hp0_axi_arvalid}),
 .s_awready({f3p_nn_hp_awready,w_port__ARM_Processor_System_0__slave_hp0_axi_awready}),
 .s_arready({f3p_nn_hp_arready,w_port__ARM_Processor_System_0__slave_hp0_axi_arready}),
 .s_wdata({f3p_nn_hp_wdata,w_port__ARM_Processor_System_0__slave_hp0_axi_wdata}),
 .s_wstrb({f3p_nn_hp_wstrb,w_port__ARM_Processor_System_0__slave_hp0_axi_wstrb}),
 .s_wvalid({f3p_nn_hp_wvalid,w_port__ARM_Processor_System_0__slave_hp0_axi_wvalid}),
 .s_wready({f3p_nn_hp_wready,w_port__ARM_Processor_System_0__slave_hp0_axi_wready}),
 .s_bid({f3p_nn_hp_bid,w_port__ARM_Processor_System_0__slave_hp0_axi_bid}),
 .s_rid({f3p_nn_hp_rid,w_port__ARM_Processor_System_0__slave_hp0_axi_rid}),
 .s_bresp({f3p_nn_hp_bresp,w_port__ARM_Processor_System_0__slave_hp0_axi_bresp}),
 .s_rresp({f3p_nn_hp_rresp,w_port__ARM_Processor_System_0__slave_hp0_axi_rresp}),
 .s_bvalid({f3p_nn_hp_bvalid,w_port__ARM_Processor_System_0__slave_hp0_axi_bvalid}),
 .s_rvalid({f3p_nn_hp_rvalid,w_port__ARM_Processor_System_0__slave_hp0_axi_rvalid}),
 .s_rlast({f3p_nn_hp_rlast,w_port__ARM_Processor_System_0__slave_hp0_axi_rlast}),
 .s_bready({f3p_nn_hp_bready,w_port__ARM_Processor_System_0__slave_hp0_axi_bready}),
 .s_rready({f3p_nn_hp_rready,w_port__ARM_Processor_System_0__slave_hp0_axi_rready}),
 .s_rdata({f3p_nn_hp_rdata,w_port__ARM_Processor_System_0__slave_hp0_axi_rdata}),
 .s_awcache({f3p_nn_hp_awcache,w_port__ARM_Processor_System_0__slave_hp0_axi_awcache}),
 .s_arcache({f3p_nn_hp_arcache,w_port__ARM_Processor_System_0__slave_hp0_axi_arcache}),
 .s_wlast({f3p_nn_hp_wlast,w_port__ARM_Processor_System_0__slave_hp0_axi_wlast}),
 .m_awid(f3p_hp_awid),
 .m_arid(f3p_hp_arid),
 .m_awaddr(f3p_hp_awaddr),
 .m_araddr(f3p_hp_araddr),
 .m_awlen(f3p_hp_awlen),
 .m_arlen(f3p_hp_arlen),
 .m_awsize(f3p_hp_awsize),
 .m_arsize(f3p_hp_arsize),
 .m_awburst(f3p_hp_awburst),
 .m_arburst(f3p_hp_arburst),
 .m_awlock(f3p_hp_awlock),
 .m_arlock(f3p_hp_arlock),
 .m_awprot(f3p_hp_awprot),
 .m_arprot(f3p_hp_arprot),
 .m_awvalid(f3p_hp_awvalid),
 .m_arvalid(f3p_hp_arvalid),
 .m_awready(f3p_hp_awready),
 .m_arready(f3p_hp_arready),
 .m_wdata(f3p_hp_wdata),
 .m_wstrb(f3p_hp_wstrb),
 .m_wvalid(f3p_hp_wvalid),
 .m_wready(f3p_hp_wready),
 .m_bid(f3p_hp_bid),
 .m_rid(f3p_hp_rid),
 .m_bresp(f3p_hp_bresp),
 .m_rresp(f3p_hp_rresp),
 .m_bvalid(f3p_hp_bvalid),
 .m_rvalid(f3p_hp_rvalid),
 .m_rlast(f3p_hp_rlast),
 .m_bready(f3p_hp_bready),
 .m_rready(f3p_hp_rready),
 .m_rdata(f3p_hp_rdata),
 .m_awcache(f3p_hp_awcache),
 .m_arcache(f3p_hp_arcache),
 .m_wlast(f3p_hp_wlast)
);
// Independent of camera PL_GPIO reset. Async assertion, HP-clock release.
always @(posedge O_ui_clk or negedge O_mrstn)
 if(!O_mrstn)f3p_coco_hp_reset_sync<=2'b00;
 else f3p_coco_hp_reset_sync<={f3p_coco_hp_reset_sync[0],1'b1};
assign f3p_coco_hp_rst_n=f3p_coco_hp_reset_sync[1];
al_axi_clock_converter #(.AXI_PROTOCOL(0),.AXI_ID_WIDTH(6),.AXI_ADDR_WIDTH(33),.AXI_DATA_WIDTH(64),.IS_ACLK_ASYNC(1),.AXI_SUPPORTS_USER_SIGNALS(0),.AW_FIFO_DEPTH(4),.AR_FIFO_DEPTH(4),.W_FIFO_DEPTH(4),.R_FIFO_DEPTH(4),.B_FIFO_DEPTH(4)) u_coco_clock_crossing (
 .us_aclk(O_mclk),
 .us_aresetn(O_mrstn),
 .ds_aclk(O_ui_clk),
 .ds_aresetn(f3p_coco_hp_rst_n),
 .us_awid(f3p_nn_awid),
 .ds_awid(f3p_nn_hp_awid),
 .us_arid(f3p_nn_arid),
 .ds_arid(f3p_nn_hp_arid),
 .us_awaddr(f3p_nn_awaddr),
 .ds_awaddr(f3p_nn_hp_awaddr),
 .us_araddr(f3p_nn_araddr),
 .ds_araddr(f3p_nn_hp_araddr),
 .us_awlen({4'b0,f3p_nn_awlen}),
 .ds_awlen(f3p_nn_cdc_awlen),
 .us_arlen({4'b0,f3p_nn_arlen}),
 .ds_arlen(f3p_nn_cdc_arlen),
 .us_awsize({1'b0,f3p_nn_awsize}),
 .ds_awsize(f3p_nn_cdc_awsize),
 .us_arsize({1'b0,f3p_nn_arsize}),
 .ds_arsize(f3p_nn_cdc_arsize),
 .us_awburst(f3p_nn_awburst),
 .ds_awburst(f3p_nn_hp_awburst),
 .us_arburst(f3p_nn_arburst),
 .ds_arburst(f3p_nn_hp_arburst),
 .us_awlock(f3p_nn_awlock),
 .ds_awlock(f3p_nn_hp_awlock),
 .us_arlock(f3p_nn_arlock),
 .ds_arlock(f3p_nn_hp_arlock),
 .us_awprot(f3p_nn_awprot),
 .ds_awprot(f3p_nn_hp_awprot),
 .us_arprot(f3p_nn_arprot),
 .ds_arprot(f3p_nn_hp_arprot),
 .us_awvalid(f3p_nn_awvalid),
 .ds_awvalid(f3p_nn_hp_awvalid),
 .us_arvalid(f3p_nn_arvalid),
 .ds_arvalid(f3p_nn_hp_arvalid),
 .us_awready(f3p_nn_awready),
 .ds_awready(f3p_nn_hp_awready),
 .us_arready(f3p_nn_arready),
 .ds_arready(f3p_nn_hp_arready),
 .us_wdata(f3p_nn_wdata),
 .ds_wdata(f3p_nn_hp_wdata),
 .us_wstrb(f3p_nn_wstrb),
 .ds_wstrb(f3p_nn_hp_wstrb),
 .us_wvalid(f3p_nn_wvalid),
 .ds_wvalid(f3p_nn_hp_wvalid),
 .us_wready(f3p_nn_wready),
 .ds_wready(f3p_nn_hp_wready),
 .us_bid(f3p_nn_bid),
 .ds_bid(f3p_nn_hp_bid),
 .us_rid(f3p_nn_rid),
 .ds_rid(f3p_nn_hp_rid),
 .us_bresp(f3p_nn_bresp),
 .ds_bresp(f3p_nn_hp_bresp),
 .us_rresp(f3p_nn_rresp),
 .ds_rresp(f3p_nn_hp_rresp),
 .us_bvalid(f3p_nn_bvalid),
 .ds_bvalid(f3p_nn_hp_bvalid),
 .us_rvalid(f3p_nn_rvalid),
 .ds_rvalid(f3p_nn_hp_rvalid),
 .us_rlast(f3p_nn_rlast),
 .ds_rlast(f3p_nn_hp_rlast),
 .us_bready(f3p_nn_bready),
 .ds_bready(f3p_nn_hp_bready),
 .us_rready(f3p_nn_rready),
 .ds_rready(f3p_nn_hp_rready),
 .us_rdata(f3p_nn_rdata),
 .ds_rdata(f3p_nn_hp_rdata),
 .us_awcache(f3p_nn_awcache),
 .ds_awcache(f3p_nn_hp_awcache),
 .us_arcache(f3p_nn_arcache),
 .ds_arcache(f3p_nn_hp_arcache),
 .us_wlast(f3p_nn_wlast),
 .ds_wlast(f3p_nn_hp_wlast),
 .us_awregion(4'b0),
 .us_arregion(4'b0),
 .us_awqos(4'b0),
 .us_arqos(4'b0),
 .us_awuser(1'b0),
 .us_aruser(1'b0),
 .us_wuser(1'b0),
 .us_buser(),
 .us_ruser(),
 .us_wid(6'b0),
 .ds_awregion(),
 .ds_arregion(),
 .ds_awqos(),
 .ds_arqos(),
 .ds_awuser(),
 .ds_aruser(),
 .ds_wuser(),
 .ds_buser(1'b0),
 .ds_ruser(1'b0),
 .ds_wid()
);
assign f3p_nn_hp_awlen=f3p_nn_cdc_awlen[3:0];
assign f3p_nn_hp_arlen=f3p_nn_cdc_arlen[3:0];
assign f3p_nn_hp_awsize=f3p_nn_cdc_awsize[1:0];
assign f3p_nn_hp_arsize=f3p_nn_cdc_arsize[1:0];
video_npu_top u_coco_softnpu (
 .M_AXI_ACLK(O_mclk),
 .M_AXI_AResetn(O_mrstn),
 .S_AXILite_ACLK(O_mclk),
 .S_AXILite_AResetn(O_mrstn),
 .s_axilite_awaddr_i(f3p_cfg_awaddr),
 .s_axilite_awprot_i(f3p_cfg_awprot),
 .s_axilite_awvalid_i(f3p_cfg_awvalid),
 .s_axilite_awready_o(f3p_cfg_awready),
 .s_axilite_wdata_i(f3p_cfg_wdata),
 .s_axilite_wstrb_i(f3p_cfg_wstrb),
 .s_axilite_wvalid_i(f3p_cfg_wvalid),
 .s_axilite_wready_o(f3p_cfg_wready),
 .s_axilite_bvalid_o(f3p_cfg_bvalid),
 .s_axilite_bresp_o(f3p_cfg_bresp),
 .s_axilite_bready_i(f3p_cfg_bready),
 .s_axilite_araddr_i(f3p_cfg_araddr),
 .s_axilite_arprot_i(f3p_cfg_arprot),
 .s_axilite_arvalid_i(f3p_cfg_arvalid),
 .s_axilite_arready_o(f3p_cfg_arready),
 .s_axilite_rdata_o(f3p_cfg_rdata),
 .s_axilite_rresp_o(f3p_cfg_rresp),
 .s_axilite_rvalid_o(f3p_cfg_rvalid),
 .s_axilite_rready_i(f3p_cfg_rready),
 .m_axi_awready_soft_i(f3p_nn_awready),
 .m_axi_awid_soft_o(f3p_nn_awid),
 .m_axi_awaddr_soft_o(f3p_nn_awaddr),
 .m_axi_awlen_soft_o(f3p_nn_awlen),
 .m_axi_awsize_soft_o(f3p_nn_awsize),
 .m_axi_awburst_soft_o(f3p_nn_awburst),
 .m_axi_awprot_soft_o(f3p_nn_awprot),
 .m_axi_awvalid_soft_o(f3p_nn_awvalid),
 .m_axi_awlock_soft_o(f3p_nn_awlock),
 .m_axi_awcache_soft_o(f3p_nn_awcache),
 .m_axi_wdata_soft_o(f3p_nn_wdata),
 .m_axi_wstrb_soft_o(f3p_nn_wstrb),
 .m_axi_wready_soft_i(f3p_nn_wready),
 .m_axi_wlast_soft_o(f3p_nn_wlast),
 .m_axi_wvalid_soft_o(f3p_nn_wvalid),
 .m_axi_bid_soft_i(f3p_nn_bid),
 .m_axi_bresp_soft_i(f3p_nn_bresp),
 .m_axi_bvalid_soft_i(f3p_nn_bvalid),
 .m_axi_bready_soft_o(f3p_nn_bready),
 .m_axi_arready_soft_i(f3p_nn_arready),
 .m_axi_arid_soft_o(f3p_nn_arid),
 .m_axi_araddr_soft_o(f3p_nn_araddr),
 .m_axi_arlen_soft_o(f3p_nn_arlen),
 .m_axi_arsize_soft_o(f3p_nn_arsize),
 .m_axi_arburst_soft_o(f3p_nn_arburst),
 .m_axi_arprot_soft_o(f3p_nn_arprot),
 .m_axi_arvalid_soft_o(f3p_nn_arvalid),
 .m_axi_arlock_soft_o(f3p_nn_arlock),
 .m_axi_arcache_soft_o(f3p_nn_arcache),
 .m_axi_rid_soft_i(f3p_nn_rid),
 .m_axi_rdata_soft_i(f3p_nn_rdata),
 .m_axi_rresp_soft_i(f3p_nn_rresp),
 .m_axi_rlast_soft_i(f3p_nn_rlast),
 .m_axi_rvalid_soft_i(f3p_nn_rvalid),
 .m_axi_rready_soft_o(f3p_nn_rready),
 .npu_soft_intr(f3p_coco_irq)
);
    system_ARM_Processor_System_0 system_ARM_Processor_System_0_Inst ( 
                                                                        .slave_hp0_axi_araddr(f3p_hp_araddr)
                                                                      , .slave_hp0_axi_arburst(f3p_hp_arburst)
                                                                      , .slave_hp0_axi_arcache(f3p_hp_arcache)
                                                                      , .slave_hp0_axi_arid(f3p_hp_arid)
                                                                      , .slave_hp0_axi_arlen(f3p_hp_arlen)
                                                                      , .slave_hp0_axi_arlock(f3p_hp_arlock)
                                                                      , .slave_hp0_axi_arprot(f3p_hp_arprot)
                                                                      , .slave_hp0_axi_arqos(w_port__ARM_Processor_System_0__slave_hp0_axi_arqos)
                                                                      , .slave_hp0_axi_arready(f3p_hp_arready)
                                                                      , .slave_hp0_axi_arsize(f3p_hp_arsize)
                                                                      , .slave_hp0_axi_arvalid(f3p_hp_arvalid)
                                                                      , .slave_hp0_axi_awaddr(f3p_hp_awaddr)
                                                                      , .slave_hp0_axi_awburst(f3p_hp_awburst)
                                                                      , .slave_hp0_axi_awcache(f3p_hp_awcache)
                                                                      , .slave_hp0_axi_awid(f3p_hp_awid)
                                                                      , .slave_hp0_axi_awlen(f3p_hp_awlen)
                                                                      , .slave_hp0_axi_awlock(f3p_hp_awlock)
                                                                      , .slave_hp0_axi_awprot(f3p_hp_awprot)
                                                                      , .slave_hp0_axi_awqos(w_port__ARM_Processor_System_0__slave_hp0_axi_awqos)
                                                                      , .slave_hp0_axi_awready(f3p_hp_awready)
                                                                      , .slave_hp0_axi_awsize(f3p_hp_awsize)
                                                                      , .slave_hp0_axi_awvalid(f3p_hp_awvalid)
                                                                      , .slave_hp0_axi_bid(f3p_hp_bid)
                                                                      , .slave_hp0_axi_bready(f3p_hp_bready)
                                                                      , .slave_hp0_axi_bresp(f3p_hp_bresp)
                                                                      , .slave_hp0_axi_bvalid(f3p_hp_bvalid)
                                                                      , .slave_hp0_axi_rdata(f3p_hp_rdata)
                                                                      , .slave_hp0_axi_rid(f3p_hp_rid)
                                                                      , .slave_hp0_axi_rlast(f3p_hp_rlast)
                                                                      , .slave_hp0_axi_rready(f3p_hp_rready)
                                                                      , .slave_hp0_axi_rresp(f3p_hp_rresp)
                                                                      , .slave_hp0_axi_rvalid(f3p_hp_rvalid)
                                                                      , .slave_hp0_axi_wdata(f3p_hp_wdata)
                                                                      , .slave_hp0_axi_wlast(f3p_hp_wlast)
                                                                      , .slave_hp0_axi_wready(f3p_hp_wready)
                                                                      , .slave_hp0_axi_wstrb(f3p_hp_wstrb)
                                                                      , .slave_hp0_axi_wvalid(f3p_hp_wvalid)
                                                                      , .slave_hp1_axi_araddr(w_port__ARM_Processor_System_0__slave_hp1_axi_araddr)
                                                                      , .slave_hp1_axi_arburst(w_port__ARM_Processor_System_0__slave_hp1_axi_arburst)
                                                                      , .slave_hp1_axi_arcache(w_port__ARM_Processor_System_0__slave_hp1_axi_arcache)
                                                                      , .slave_hp1_axi_arid(6'b0)
                                                                      , .slave_hp1_axi_arlen(w_port__ARM_Processor_System_0__slave_hp1_axi_arlen)
                                                                      , .slave_hp1_axi_arlock(1'b0)
                                                                      , .slave_hp1_axi_arprot(w_port__ARM_Processor_System_0__slave_hp1_axi_arprot)
                                                                      , .slave_hp1_axi_arqos(4'b0)
                                                                      , .slave_hp1_axi_arready(w_port__ARM_Processor_System_0__slave_hp1_axi_arready)
                                                                      , .slave_hp1_axi_arsize(w_port__ARM_Processor_System_0__slave_hp1_axi_arsize)
                                                                      , .slave_hp1_axi_arvalid(w_port__ARM_Processor_System_0__slave_hp1_axi_arvalid)
                                                                      , .slave_hp1_axi_awaddr(33'b0)
                                                                      , .slave_hp1_axi_awburst(2'b0)
                                                                      , .slave_hp1_axi_awcache(4'b0)
                                                                      , .slave_hp1_axi_awid(6'b0)
                                                                      , .slave_hp1_axi_awlen(4'b0)
                                                                      , .slave_hp1_axi_awlock(1'b0)
                                                                      , .slave_hp1_axi_awprot(3'b0)
                                                                      , .slave_hp1_axi_awqos(4'b0)
                                                                      , .slave_hp1_axi_awready()
                                                                      , .slave_hp1_axi_awsize(2'b0)
                                                                      , .slave_hp1_axi_awvalid(1'b0)
                                                                      , .slave_hp1_axi_bid()
                                                                      , .slave_hp1_axi_bready(1'b0)
                                                                      , .slave_hp1_axi_bresp()
                                                                      , .slave_hp1_axi_bvalid()
                                                                      , .slave_hp1_axi_rdata(w_port__ARM_Processor_System_0__slave_hp1_axi_rdata)
                                                                      , .slave_hp1_axi_rid()
                                                                      , .slave_hp1_axi_rlast(w_port__ARM_Processor_System_0__slave_hp1_axi_rlast)
                                                                      , .slave_hp1_axi_rready(w_port__ARM_Processor_System_0__slave_hp1_axi_rready)
                                                                      , .slave_hp1_axi_rresp(w_port__ARM_Processor_System_0__slave_hp1_axi_rresp)
                                                                      , .slave_hp1_axi_rvalid(w_port__ARM_Processor_System_0__slave_hp1_axi_rvalid)
                                                                      , .slave_hp1_axi_wdata(64'b0)
                                                                      , .slave_hp1_axi_wlast(1'b0)
                                                                      , .slave_hp1_axi_wready()
                                                                      , .slave_hp1_axi_wstrb(8'b0)
                                                                      , .slave_hp1_axi_wvalid(1'b0)
                                                                      , .slave_hp0_axi_aclk(w_port__ARM_Processor_System_0__slave_hp0_axi_aclk)
                                                                      , .slave_hp1_axi_aclk(w_port__ARM_Processor_System_0__slave_hp1_axi_aclk)
                                                                      , .master_gp0_axi_aclk(w_port__ARM_Processor_System_0__master_gp0_axi_aclk)
                                                                      , .master_gp1_axi_aclk(w_port__ARM_Processor_System_0__master_gp1_axi_aclk)
                                                                      , .f2p_irq(w_port__ARM_Processor_System_0__f2p_irq)
                                                                      , .master_gp0_axi_araddr(w_port__ARM_Processor_System_0__master_gp0_axi_araddr)
                                                                      , .master_gp0_axi_arburst(w_port__ARM_Processor_System_0__master_gp0_axi_arburst)
                                                                      , .master_gp0_axi_arcache(w_port__ARM_Processor_System_0__master_gp0_axi_arcache)
                                                                      , .master_gp0_axi_arid(w_port__ARM_Processor_System_0__master_gp0_axi_arid)
                                                                      , .master_gp0_axi_arlen(w_port__ARM_Processor_System_0__master_gp0_axi_arlen)
                                                                      , .master_gp0_axi_arlock(w_port__ARM_Processor_System_0__master_gp0_axi_arlock)
                                                                      , .master_gp0_axi_arprot(w_port__ARM_Processor_System_0__master_gp0_axi_arprot)
                                                                      , .master_gp0_axi_arready(w_port__ARM_Processor_System_0__master_gp0_axi_arready)
                                                                      , .master_gp0_axi_arsize(w_port__ARM_Processor_System_0__master_gp0_axi_arsize)
                                                                      , .master_gp0_axi_arvalid(w_port__ARM_Processor_System_0__master_gp0_axi_arvalid)
                                                                      , .master_gp0_axi_awaddr(w_port__ARM_Processor_System_0__master_gp0_axi_awaddr)
                                                                      , .master_gp0_axi_awburst(w_port__ARM_Processor_System_0__master_gp0_axi_awburst)
                                                                      , .master_gp0_axi_awcache(w_port__ARM_Processor_System_0__master_gp0_axi_awcache)
                                                                      , .master_gp0_axi_awid(w_port__ARM_Processor_System_0__master_gp0_axi_awid)
                                                                      , .master_gp0_axi_awlen(w_port__ARM_Processor_System_0__master_gp0_axi_awlen)
                                                                      , .master_gp0_axi_awlock(w_port__ARM_Processor_System_0__master_gp0_axi_awlock)
                                                                      , .master_gp0_axi_awprot(w_port__ARM_Processor_System_0__master_gp0_axi_awprot)
                                                                      , .master_gp0_axi_awready(w_port__ARM_Processor_System_0__master_gp0_axi_awready)
                                                                      , .master_gp0_axi_awsize(w_port__ARM_Processor_System_0__master_gp0_axi_awsize)
                                                                      , .master_gp0_axi_awvalid(w_port__ARM_Processor_System_0__master_gp0_axi_awvalid)
                                                                      , .master_gp0_axi_bid(w_port__ARM_Processor_System_0__master_gp0_axi_bid)
                                                                      , .master_gp0_axi_bready(w_port__ARM_Processor_System_0__master_gp0_axi_bready)
                                                                      , .master_gp0_axi_bresp(w_port__ARM_Processor_System_0__master_gp0_axi_bresp)
                                                                      , .master_gp0_axi_bvalid(w_port__ARM_Processor_System_0__master_gp0_axi_bvalid)
                                                                      , .master_gp0_axi_rdata(w_port__ARM_Processor_System_0__master_gp0_axi_rdata)
                                                                      , .master_gp0_axi_rid(w_port__ARM_Processor_System_0__master_gp0_axi_rid)
                                                                      , .master_gp0_axi_rlast(w_port__ARM_Processor_System_0__master_gp0_axi_rlast)
                                                                      , .master_gp0_axi_rready(w_port__ARM_Processor_System_0__master_gp0_axi_rready)
                                                                      , .master_gp0_axi_rresp(w_port__ARM_Processor_System_0__master_gp0_axi_rresp)
                                                                      , .master_gp0_axi_rvalid(w_port__ARM_Processor_System_0__master_gp0_axi_rvalid)
                                                                      , .master_gp0_axi_wdata(w_port__ARM_Processor_System_0__master_gp0_axi_wdata)
                                                                      , .master_gp0_axi_wlast(w_port__ARM_Processor_System_0__master_gp0_axi_wlast)
                                                                      , .master_gp0_axi_wready(w_port__ARM_Processor_System_0__master_gp0_axi_wready)
                                                                      , .master_gp0_axi_wstrb(w_port__ARM_Processor_System_0__master_gp0_axi_wstrb)
                                                                      , .master_gp0_axi_wvalid(w_port__ARM_Processor_System_0__master_gp0_axi_wvalid)
                                                                      , .master_gp1_axi_araddr(f3p_gp_araddr)
                                                                      , .master_gp1_axi_arburst(f3p_gp_arburst)
                                                                      , .master_gp1_axi_arcache()
                                                                      , .master_gp1_axi_arid(f3p_gp_arid)
                                                                      , .master_gp1_axi_arlen(f3p_gp_arlen)
                                                                      , .master_gp1_axi_arlock(f3p_gp_arlock)
                                                                      , .master_gp1_axi_arprot(f3p_gp_arprot)
                                                                      , .master_gp1_axi_arready(f3p_gp_arready)
                                                                      , .master_gp1_axi_arsize(f3p_gp_arsize)
                                                                      , .master_gp1_axi_arvalid(f3p_gp_arvalid)
                                                                      , .master_gp1_axi_awaddr(f3p_gp_awaddr)
                                                                      , .master_gp1_axi_awburst(f3p_gp_awburst)
                                                                      , .master_gp1_axi_awcache()
                                                                      , .master_gp1_axi_awid(f3p_gp_awid)
                                                                      , .master_gp1_axi_awlen(f3p_gp_awlen)
                                                                      , .master_gp1_axi_awlock(f3p_gp_awlock)
                                                                      , .master_gp1_axi_awprot(f3p_gp_awprot)
                                                                      , .master_gp1_axi_awready(f3p_gp_awready)
                                                                      , .master_gp1_axi_awsize(f3p_gp_awsize)
                                                                      , .master_gp1_axi_awvalid(f3p_gp_awvalid)
                                                                      , .master_gp1_axi_bid(f3p_gp_bid)
                                                                      , .master_gp1_axi_bready(f3p_gp_bready)
                                                                      , .master_gp1_axi_bresp(f3p_gp_bresp)
                                                                      , .master_gp1_axi_bvalid(f3p_gp_bvalid)
                                                                      , .master_gp1_axi_rdata(f3p_gp_rdata)
                                                                      , .master_gp1_axi_rid(f3p_gp_rid)
                                                                      , .master_gp1_axi_rlast(f3p_gp_rlast)
                                                                      , .master_gp1_axi_rready(f3p_gp_rready)
                                                                      , .master_gp1_axi_rresp(f3p_gp_rresp)
                                                                      , .master_gp1_axi_rvalid(f3p_gp_rvalid)
                                                                      , .master_gp1_axi_wdata(f3p_gp_wdata)
                                                                      , .master_gp1_axi_wlast()
                                                                      , .master_gp1_axi_wready(f3p_gp_wready)
                                                                      , .master_gp1_axi_wstrb(f3p_gp_wstrb)
                                                                      , .master_gp1_axi_wvalid(f3p_gp_wvalid)
                                                                      , .pl_gpio_in(1'b0)
                                                                      , .pl_gpio_oe()
                                                                      , .pl_gpio_out(w_port__ARM_Processor_System_0__pl_gpio_out)
                                                                      , .p2f_rst0_n(w_port__ARM_Processor_System_0__p2f_rst0_n)
                                                                      , .p2f_clk2(w_port__ARM_Processor_System_0__p2f_clk2)
                                                                      , .p2f_clk1(w_port__ARM_Processor_System_0__p2f_clk1)
                                                                      , .p2f_clk0(w_port__ARM_Processor_System_0__p2f_clk0) );

    system_Processor_System_Reset_0 system_Processor_System_Reset_0_Inst ( 
                                                                            .clk(w_port__Processor_System_Reset_0__clk)
                                                                          , .external_reset(w_port__Processor_System_Reset_0__external_reset)
                                                                          , .aux_rst(w_port__Processor_System_Reset_0__aux_rst)
                                                                          , .system_rst(w_port__Processor_System_Reset_0__system_rst)
                                                                          , .pll_locked(w_port__Processor_System_Reset_0__pll_locked)
                                                                          , .soc_reset()
                                                                          , .bus_reset()
                                                                          , .peripheral_reset()
                                                                          , .interconnect_aresetn()
                                                                          , .peripheral_aresetn(w_port__Processor_System_Reset_0__peripheral_aresetn) );

    system_Constant_0 system_Constant_0_Inst ( 
                                                .dout(w_port__Constant_0__dout) );

    system_VDMA_0 system_VDMA_0_Inst ( 
                                        .axi_lite_awvalid(w_port__VDMA_0__axi_lite_awvalid)
                                      , .axi_lite_awready(w_port__VDMA_0__axi_lite_awready)
                                      , .axi_lite_awaddr(w_port__VDMA_0__axi_lite_awaddr)
                                      , .axi_lite_wvalid(w_port__VDMA_0__axi_lite_wvalid)
                                      , .axi_lite_wready(w_port__VDMA_0__axi_lite_wready)
                                      , .axi_lite_wdata(w_port__VDMA_0__axi_lite_wdata)
                                      , .axi_lite_bresp(w_port__VDMA_0__axi_lite_bresp)
                                      , .axi_lite_bvalid(w_port__VDMA_0__axi_lite_bvalid)
                                      , .axi_lite_bready(w_port__VDMA_0__axi_lite_bready)
                                      , .axi_lite_arvalid(w_port__VDMA_0__axi_lite_arvalid)
                                      , .axi_lite_arready(w_port__VDMA_0__axi_lite_arready)
                                      , .axi_lite_araddr(w_port__VDMA_0__axi_lite_araddr)
                                      , .axi_lite_rvalid(w_port__VDMA_0__axi_lite_rvalid)
                                      , .axi_lite_rready(w_port__VDMA_0__axi_lite_rready)
                                      , .axi_lite_rdata(w_port__VDMA_0__axi_lite_rdata)
                                      , .axi_lite_rresp(w_port__VDMA_0__axi_lite_rresp)
                                      , .s_axis_s2mm_tdata(32'b0)
                                      , .s_axis_s2mm_tkeep(4'b1111)
                                      , .s_axis_s2mm_tuser(1'b0)
                                      , .s_axis_s2mm_tvalid(1'b0)
                                      , .s_axis_s2mm_tready()
                                      , .s_axis_s2mm_tlast(1'b0)
                                      , .s_axi_lite_aclk(w_port__VDMA_0__s_axi_lite_aclk)
                                      , .m_axi_mm2s_aclk(w_port__VDMA_0__m_axi_mm2s_aclk)
                                      , .m_axis_mm2s_aclk(w_port__VDMA_0__m_axis_mm2s_aclk)
                                      , .m_axi_s2mm_aclk(w_port__VDMA_0__m_axi_s2mm_aclk)
                                      , .s_axis_s2mm_aclk(w_port__VDMA_0__s_axis_s2mm_aclk)
                                      , .resetn(w_port__VDMA_0__resetn)
                                      , .mm2s_fsync(1'b0)
                                      , .s2mm_fsync(1'b0)
                                      , .m_axi_mm2s_araddr(w_port__VDMA_0__m_axi_mm2s_araddr)
                                      , .m_axi_mm2s_arlen(w_port__VDMA_0__m_axi_mm2s_arlen)
                                      , .m_axi_mm2s_arsize(w_port__VDMA_0__m_axi_mm2s_arsize)
                                      , .m_axi_mm2s_arburst(w_port__VDMA_0__m_axi_mm2s_arburst)
                                      , .m_axi_mm2s_arprot(w_port__VDMA_0__m_axi_mm2s_arprot)
                                      , .m_axi_mm2s_arcache(w_port__VDMA_0__m_axi_mm2s_arcache)
                                      , .m_axi_mm2s_arvalid(w_port__VDMA_0__m_axi_mm2s_arvalid)
                                      , .m_axi_mm2s_arready(w_port__VDMA_0__m_axi_mm2s_arready)
                                      , .m_axi_mm2s_rdata(w_port__VDMA_0__m_axi_mm2s_rdata)
                                      , .m_axi_mm2s_rresp(w_port__VDMA_0__m_axi_mm2s_rresp)
                                      , .m_axi_mm2s_rlast(w_port__VDMA_0__m_axi_mm2s_rlast)
                                      , .m_axi_mm2s_rvalid(w_port__VDMA_0__m_axi_mm2s_rvalid)
                                      , .m_axi_mm2s_rready(w_port__VDMA_0__m_axi_mm2s_rready)
                                      , .m_axi_s2mm_awaddr()
                                      , .m_axi_s2mm_awlen()
                                      , .m_axi_s2mm_awsize()
                                      , .m_axi_s2mm_awburst()
                                      , .m_axi_s2mm_awprot()
                                      , .m_axi_s2mm_awcache()
                                      , .m_axi_s2mm_awvalid()
                                      , .m_axi_s2mm_awready(1'b0)
                                      , .m_axi_s2mm_wdata()
                                      , .m_axi_s2mm_wstrb()
                                      , .m_axi_s2mm_wlast()
                                      , .m_axi_s2mm_wvalid()
                                      , .m_axi_s2mm_wready(1'b0)
                                      , .m_axi_s2mm_bresp(2'b0)
                                      , .m_axi_s2mm_bvalid(1'b0)
                                      , .m_axi_s2mm_bready()
                                      , .m_axis_mm2s_tdata(w_port__VDMA_0__m_axis_mm2s_tdata)
                                      , .m_axis_mm2s_tkeep()
                                      , .m_axis_mm2s_tuser(w_port__VDMA_0__m_axis_mm2s_tuser)
                                      , .m_axis_mm2s_tvalid(w_port__VDMA_0__m_axis_mm2s_tvalid)
                                      , .m_axis_mm2s_tready(w_port__VDMA_0__m_axis_mm2s_tready)
                                      , .m_axis_mm2s_tlast(w_port__VDMA_0__m_axis_mm2s_tlast)
                                      , .mm2s_frame_ptr_out()
                                      , .s2mm_frame_ptr_out()
                                      , .mm2s_introut(w_port__VDMA_0__mm2s_introut)
                                      , .s2mm_introut(w_port__VDMA_0__s2mm_introut) );

    system_AXI_Matrix_0 system_AXI_Matrix_0_Inst ( 
                                                    .us0_araddr(w_port__AXI_Matrix_0__us0_araddr)
                                                  , .us0_arprot(w_port__AXI_Matrix_0__us0_arprot)
                                                  , .us0_arready(w_port__AXI_Matrix_0__us0_arready)
                                                  , .us0_arvalid(w_port__AXI_Matrix_0__us0_arvalid)
                                                  , .us0_awaddr(w_port__AXI_Matrix_0__us0_awaddr)
                                                  , .us0_awprot(w_port__AXI_Matrix_0__us0_awprot)
                                                  , .us0_awready(w_port__AXI_Matrix_0__us0_awready)
                                                  , .us0_awvalid(w_port__AXI_Matrix_0__us0_awvalid)
                                                  , .us0_bready(w_port__AXI_Matrix_0__us0_bready)
                                                  , .us0_bresp(w_port__AXI_Matrix_0__us0_bresp)
                                                  , .us0_bvalid(w_port__AXI_Matrix_0__us0_bvalid)
                                                  , .us0_rdata(w_port__AXI_Matrix_0__us0_rdata)
                                                  , .us0_rready(w_port__AXI_Matrix_0__us0_rready)
                                                  , .us0_rresp(w_port__AXI_Matrix_0__us0_rresp)
                                                  , .us0_rvalid(w_port__AXI_Matrix_0__us0_rvalid)
                                                  , .us0_wdata(w_port__AXI_Matrix_0__us0_wdata)
                                                  , .us0_wready(w_port__AXI_Matrix_0__us0_wready)
                                                  , .us0_wstrb(w_port__AXI_Matrix_0__us0_wstrb)
                                                  , .us0_wvalid(w_port__AXI_Matrix_0__us0_wvalid)
                                                  , .aclk(w_port__AXI_Matrix_0__aclk)
                                                  , .aresetn(w_port__AXI_Matrix_0__aresetn)
                                                  , .ds0_araddr(w_port__AXI_Matrix_0__ds0_araddr)
                                                  , .ds0_arprot()
                                                  , .ds0_arready(w_port__AXI_Matrix_0__ds0_arready)
                                                  , .ds0_arvalid(w_port__AXI_Matrix_0__ds0_arvalid)
                                                  , .ds0_awaddr(w_port__AXI_Matrix_0__ds0_awaddr)
                                                  , .ds0_awprot()
                                                  , .ds0_awready(w_port__AXI_Matrix_0__ds0_awready)
                                                  , .ds0_awvalid(w_port__AXI_Matrix_0__ds0_awvalid)
                                                  , .ds0_bready(w_port__AXI_Matrix_0__ds0_bready)
                                                  , .ds0_bresp(w_port__AXI_Matrix_0__ds0_bresp)
                                                  , .ds0_bvalid(w_port__AXI_Matrix_0__ds0_bvalid)
                                                  , .ds0_rdata(w_port__AXI_Matrix_0__ds0_rdata)
                                                  , .ds0_rready(w_port__AXI_Matrix_0__ds0_rready)
                                                  , .ds0_rresp(w_port__AXI_Matrix_0__ds0_rresp)
                                                  , .ds0_rvalid(w_port__AXI_Matrix_0__ds0_rvalid)
                                                  , .ds0_wdata(w_port__AXI_Matrix_0__ds0_wdata)
                                                  , .ds0_wready(w_port__AXI_Matrix_0__ds0_wready)
                                                  , .ds0_wstrb()
                                                  , .ds0_wvalid(w_port__AXI_Matrix_0__ds0_wvalid)
                                                  , .ds1_araddr(w_port__AXI_Matrix_0__ds1_araddr)
                                                  , .ds1_arprot()
                                                  , .ds1_arready(w_port__AXI_Matrix_0__ds1_arready)
                                                  , .ds1_arvalid(w_port__AXI_Matrix_0__ds1_arvalid)
                                                  , .ds1_awaddr(w_port__AXI_Matrix_0__ds1_awaddr)
                                                  , .ds1_awprot()
                                                  , .ds1_awready(w_port__AXI_Matrix_0__ds1_awready)
                                                  , .ds1_awvalid(w_port__AXI_Matrix_0__ds1_awvalid)
                                                  , .ds1_bready(w_port__AXI_Matrix_0__ds1_bready)
                                                  , .ds1_bresp(w_port__AXI_Matrix_0__ds1_bresp)
                                                  , .ds1_bvalid(w_port__AXI_Matrix_0__ds1_bvalid)
                                                  , .ds1_rdata(w_port__AXI_Matrix_0__ds1_rdata)
                                                  , .ds1_rready(w_port__AXI_Matrix_0__ds1_rready)
                                                  , .ds1_rresp(w_port__AXI_Matrix_0__ds1_rresp)
                                                  , .ds1_rvalid(w_port__AXI_Matrix_0__ds1_rvalid)
                                                  , .ds1_wdata(w_port__AXI_Matrix_0__ds1_wdata)
                                                  , .ds1_wready(w_port__AXI_Matrix_0__ds1_wready)
                                                  , .ds1_wstrb(w_port__AXI_Matrix_0__ds1_wstrb)
                                                  , .ds1_wvalid(w_port__AXI_Matrix_0__ds1_wvalid) );

    system_Processor_System_Reset_0_0 system_Processor_System_Reset_0_200_Inst ( 
                                                                                  .clk(w_port__Processor_System_Reset_0_200__clk)
                                                                                , .external_reset(w_port__Processor_System_Reset_0_200__external_reset)
                                                                                , .aux_rst(w_port__Processor_System_Reset_0_200__aux_rst)
                                                                                , .system_rst(w_port__Processor_System_Reset_0_200__system_rst)
                                                                                , .pll_locked(w_port__Processor_System_Reset_0_200__pll_locked)
                                                                                , .soc_reset()
                                                                                , .bus_reset()
                                                                                , .peripheral_reset()
                                                                                , .interconnect_aresetn()
                                                                                , .peripheral_aresetn(w_port__Processor_System_Reset_0_200__peripheral_aresetn) );

    system_AXI_ERAM_Controller_0 system_AXI_ERAM_Controller_0_Inst ( 
                                                                      .awid(w_port__AXI_ERAM_Controller_0__awid)
                                                                    , .awaddr(w_port__AXI_ERAM_Controller_0__awaddr)
                                                                    , .awlen(w_port__AXI_ERAM_Controller_0__awlen)
                                                                    , .awsize(w_port__AXI_ERAM_Controller_0__awsize)
                                                                    , .awburst(w_port__AXI_ERAM_Controller_0__awburst)
                                                                    , .awlock(w_port__AXI_ERAM_Controller_0__awlock)
                                                                    , .awvalid(w_port__AXI_ERAM_Controller_0__awvalid)
                                                                    , .awready(w_port__AXI_ERAM_Controller_0__awready)
                                                                    , .wdata(w_port__AXI_ERAM_Controller_0__wdata)
                                                                    , .wstrb(w_port__AXI_ERAM_Controller_0__wstrb)
                                                                    , .wvalid(w_port__AXI_ERAM_Controller_0__wvalid)
                                                                    , .wready(w_port__AXI_ERAM_Controller_0__wready)
                                                                    , .bid(w_port__AXI_ERAM_Controller_0__bid)
                                                                    , .bresp(w_port__AXI_ERAM_Controller_0__bresp)
                                                                    , .bvalid(w_port__AXI_ERAM_Controller_0__bvalid)
                                                                    , .bready(w_port__AXI_ERAM_Controller_0__bready)
                                                                    , .arid(w_port__AXI_ERAM_Controller_0__arid)
                                                                    , .araddr(w_port__AXI_ERAM_Controller_0__araddr)
                                                                    , .arlen(w_port__AXI_ERAM_Controller_0__arlen)
                                                                    , .arsize(w_port__AXI_ERAM_Controller_0__arsize)
                                                                    , .arburst(w_port__AXI_ERAM_Controller_0__arburst)
                                                                    , .arlock(w_port__AXI_ERAM_Controller_0__arlock)
                                                                    , .arvalid(w_port__AXI_ERAM_Controller_0__arvalid)
                                                                    , .arready(w_port__AXI_ERAM_Controller_0__arready)
                                                                    , .rid(w_port__AXI_ERAM_Controller_0__rid)
                                                                    , .rdata(w_port__AXI_ERAM_Controller_0__rdata)
                                                                    , .rresp(w_port__AXI_ERAM_Controller_0__rresp)
                                                                    , .rlast(w_port__AXI_ERAM_Controller_0__rlast)
                                                                    , .rvalid(w_port__AXI_ERAM_Controller_0__rvalid)
                                                                    , .rready(w_port__AXI_ERAM_Controller_0__rready)
                                                                    , .mem_dout(w_port__AXI_ERAM_Controller_0__mem_dout)
                                                                    , .aclk(w_port__AXI_ERAM_Controller_0__aclk)
                                                                    , .aresetn(w_port__AXI_ERAM_Controller_0__aresetn)
                                                                    , .mem_addr(w_port__AXI_ERAM_Controller_0__mem_addr)
                                                                    , .mem_web(w_port__AXI_ERAM_Controller_0__mem_web)
                                                                    , .mem_csb(w_port__AXI_ERAM_Controller_0__mem_csb)
                                                                    , .mem_din(w_port__AXI_ERAM_Controller_0__mem_din) );

    system_Concat_0 system_Concat_0_Inst ( 
                                            .In0(w_port__Concat_0__In0)
                                          , .In1(w_port__Concat_0__In1)
                                          , .In2(w_port__Concat_0__In2)
                                          , .Dout(w_port__Concat_0__Dout) );

    system_uiFDMA_1 system_uiFDMA_0_Inst ( 
                                            .I_fdma_waddr(w_port__uiFDMA_0__I_fdma_waddr)
                                          , .I_fdma_wareq(w_port__uiFDMA_0__I_fdma_wareq)
                                          , .I_fdma_wsize(w_port__uiFDMA_0__I_fdma_wsize)
                                          , .I_fdma_wdata(w_port__uiFDMA_0__I_fdma_wdata)
                                          , .I_fdma_wready(w_port__uiFDMA_0__I_fdma_wready)
                                          , .I_fdma_raddr(w_port__uiFDMA_0__I_fdma_raddr)
                                          , .I_fdma_rareq(w_port__uiFDMA_0__I_fdma_rareq)
                                          , .I_fdma_rsize(w_port__uiFDMA_0__I_fdma_rsize)
                                          , .I_fdma_rready(w_port__uiFDMA_0__I_fdma_rready)
                                          , .M_AXI_ACLK(w_port__uiFDMA_0__M_AXI_ACLK)
                                          , .M_AXI_ARESETN(w_port__uiFDMA_0__M_AXI_ARESETN)
                                          , .M_AXI_AWID(w_port__uiFDMA_0__M_AXI_AWID)
                                          , .M_AXI_AWADDR(w_port__uiFDMA_0__M_AXI_AWADDR)
                                          , .M_AXI_AWLEN(w_port__uiFDMA_0__M_AXI_AWLEN)
                                          , .M_AXI_AWSIZE(w_port__uiFDMA_0__M_AXI_AWSIZE)
                                          , .M_AXI_AWBURST(w_port__uiFDMA_0__M_AXI_AWBURST)
                                          , .M_AXI_AWLOCK(w_port__uiFDMA_0__M_AXI_AWLOCK)
                                          , .M_AXI_AWCACHE(w_port__uiFDMA_0__M_AXI_AWCACHE)
                                          , .M_AXI_AWPROT(w_port__uiFDMA_0__M_AXI_AWPROT)
                                          , .M_AXI_AWQOS(w_port__uiFDMA_0__M_AXI_AWQOS)
                                          , .M_AXI_AWVALID(w_port__uiFDMA_0__M_AXI_AWVALID)
                                          , .M_AXI_AWREADY(w_port__uiFDMA_0__M_AXI_AWREADY)
                                          , .M_AXI_WID()
                                          , .M_AXI_WDATA(w_port__uiFDMA_0__M_AXI_WDATA)
                                          , .M_AXI_WSTRB(w_port__uiFDMA_0__M_AXI_WSTRB)
                                          , .M_AXI_WLAST(w_port__uiFDMA_0__M_AXI_WLAST)
                                          , .M_AXI_WVALID(w_port__uiFDMA_0__M_AXI_WVALID)
                                          , .M_AXI_WREADY(w_port__uiFDMA_0__M_AXI_WREADY)
                                          , .M_AXI_BID(w_port__uiFDMA_0__M_AXI_BID)
                                          , .M_AXI_BRESP(w_port__uiFDMA_0__M_AXI_BRESP)
                                          , .M_AXI_BVALID(w_port__uiFDMA_0__M_AXI_BVALID)
                                          , .M_AXI_BREADY(w_port__uiFDMA_0__M_AXI_BREADY)
                                          , .M_AXI_ARID(w_port__uiFDMA_0__M_AXI_ARID)
                                          , .M_AXI_ARADDR(w_port__uiFDMA_0__M_AXI_ARADDR)
                                          , .M_AXI_ARLEN(w_port__uiFDMA_0__M_AXI_ARLEN)
                                          , .M_AXI_ARSIZE(w_port__uiFDMA_0__M_AXI_ARSIZE)
                                          , .M_AXI_ARBURST(w_port__uiFDMA_0__M_AXI_ARBURST)
                                          , .M_AXI_ARLOCK(w_port__uiFDMA_0__M_AXI_ARLOCK)
                                          , .M_AXI_ARCACHE(w_port__uiFDMA_0__M_AXI_ARCACHE)
                                          , .M_AXI_ARPROT(w_port__uiFDMA_0__M_AXI_ARPROT)
                                          , .M_AXI_ARQOS(w_port__uiFDMA_0__M_AXI_ARQOS)
                                          , .M_AXI_ARVALID(w_port__uiFDMA_0__M_AXI_ARVALID)
                                          , .M_AXI_ARREADY(w_port__uiFDMA_0__M_AXI_ARREADY)
                                          , .M_AXI_RID(w_port__uiFDMA_0__M_AXI_RID)
                                          , .M_AXI_RDATA(w_port__uiFDMA_0__M_AXI_RDATA)
                                          , .M_AXI_RRESP(w_port__uiFDMA_0__M_AXI_RRESP)
                                          , .M_AXI_RLAST(w_port__uiFDMA_0__M_AXI_RLAST)
                                          , .M_AXI_RVALID(w_port__uiFDMA_0__M_AXI_RVALID)
                                          , .M_AXI_RREADY(w_port__uiFDMA_0__M_AXI_RREADY)
                                          , .O_fdma_wbusy(w_port__uiFDMA_0__O_fdma_wbusy)
                                          , .O_fdma_wvalid(w_port__uiFDMA_0__O_fdma_wvalid)
                                          , .O_fdma_rbusy(w_port__uiFDMA_0__O_fdma_rbusy)
                                          , .O_fdma_rdata(w_port__uiFDMA_0__O_fdma_rdata)
                                          , .O_fdma_rvalid(w_port__uiFDMA_0__O_fdma_rvalid) );

    system_video_timing_generator_v01_0 system_video_timing_generator_v01_0_Inst ( 
                                                                                    .s_axi_awaddr(w_port__video_timing_generator_v01_0__s_axi_awaddr)
                                                                                  , .s_axi_awvalid(w_port__video_timing_generator_v01_0__s_axi_awvalid)
                                                                                  , .s_axi_awready(w_port__video_timing_generator_v01_0__s_axi_awready)
                                                                                  , .s_axi_wdata(w_port__video_timing_generator_v01_0__s_axi_wdata)
                                                                                  , .s_axi_wstrb(w_port__video_timing_generator_v01_0__s_axi_wstrb)
                                                                                  , .s_axi_wvalid(w_port__video_timing_generator_v01_0__s_axi_wvalid)
                                                                                  , .s_axi_wready(w_port__video_timing_generator_v01_0__s_axi_wready)
                                                                                  , .s_axi_bresp(w_port__video_timing_generator_v01_0__s_axi_bresp)
                                                                                  , .s_axi_bvalid(w_port__video_timing_generator_v01_0__s_axi_bvalid)
                                                                                  , .s_axi_bready(w_port__video_timing_generator_v01_0__s_axi_bready)
                                                                                  , .s_axi_araddr(w_port__video_timing_generator_v01_0__s_axi_araddr)
                                                                                  , .s_axi_arvalid(w_port__video_timing_generator_v01_0__s_axi_arvalid)
                                                                                  , .s_axi_arready(w_port__video_timing_generator_v01_0__s_axi_arready)
                                                                                  , .s_axi_rdata(w_port__video_timing_generator_v01_0__s_axi_rdata)
                                                                                  , .s_axi_rresp(w_port__video_timing_generator_v01_0__s_axi_rresp)
                                                                                  , .s_axi_rvalid(w_port__video_timing_generator_v01_0__s_axi_rvalid)
                                                                                  , .s_axi_rready(w_port__video_timing_generator_v01_0__s_axi_rready)
                                                                                  , .aclk(w_port__video_timing_generator_v01_0__aclk)
                                                                                  , .arst_n(w_port__video_timing_generator_v01_0__arst_n)
                                                                                  , .ref_clk(w_port__video_timing_generator_v01_0__ref_clk)
                                                                                  , .vtg_ce(w_port__video_timing_generator_v01_0__vtg_ce)
                                                                                  , .vtg_pclk_locked(w_port__video_timing_generator_v01_0__vtg_pclk_locked)
                                                                                  , .vtg_pclk(w_port__video_timing_generator_v01_0__vtg_pclk)
                                                                                  , .vtg_hsync()
                                                                                  , .vtg_vsync(w_port__video_timing_generator_v01_0__vtg_vsync)
                                                                                  , .vtg_hblank()
                                                                                  , .vtg_vblank()
                                                                                  , .vtg_active_video(w_port__video_timing_generator_v01_0__vtg_active_video) );

    system_Constant_1 system_Constant_1_Inst ( 
                                                .dout(w_port__Constant_1__dout) );

    system_ChipWatcher_0 system_ChipWatcher_0_Inst ( 
                                                      .probe0(w_port__ChipWatcher_0__probe0)
                                                    , .probe1(w_port__ChipWatcher_0__probe1)
                                                    , .probe2(w_port__ChipWatcher_0__probe2)
                                                    , .probe3(w_port__ChipWatcher_0__probe3)
                                                    , .probe4(w_port__ChipWatcher_0__probe4)
                                                    , .clk(w_port__ChipWatcher_0__clk) );

    system_AXI_Protocol_Converter_1 system_AXI_Protocol_Converter_0_Inst ( 
                                                                            .us_axi_awid(w_port__AXI_Protocol_Converter_0__us_axi_awid)
                                                                          , .us_axi_awaddr(w_port__AXI_Protocol_Converter_0__us_axi_awaddr)
                                                                          , .us_axi_awlen(w_port__AXI_Protocol_Converter_0__us_axi_awlen)
                                                                          , .us_axi_awsize(w_port__AXI_Protocol_Converter_0__us_axi_awsize)
                                                                          , .us_axi_awburst(w_port__AXI_Protocol_Converter_0__us_axi_awburst)
                                                                          , .us_axi_awlock(w_port__AXI_Protocol_Converter_0__us_axi_awlock)
                                                                          , .us_axi_awcache(w_port__AXI_Protocol_Converter_0__us_axi_awcache)
                                                                          , .us_axi_awprot(w_port__AXI_Protocol_Converter_0__us_axi_awprot)
                                                                          , .us_axi_awqos(4'b0)
                                                                          , .us_axi_awvalid(w_port__AXI_Protocol_Converter_0__us_axi_awvalid)
                                                                          , .us_axi_awready(w_port__AXI_Protocol_Converter_0__us_axi_awready)
                                                                          , .us_axi_wdata(w_port__AXI_Protocol_Converter_0__us_axi_wdata)
                                                                          , .us_axi_wstrb(w_port__AXI_Protocol_Converter_0__us_axi_wstrb)
                                                                          , .us_axi_wlast(w_port__AXI_Protocol_Converter_0__us_axi_wlast)
                                                                          , .us_axi_wvalid(w_port__AXI_Protocol_Converter_0__us_axi_wvalid)
                                                                          , .us_axi_wready(w_port__AXI_Protocol_Converter_0__us_axi_wready)
                                                                          , .us_axi_bid(w_port__AXI_Protocol_Converter_0__us_axi_bid)
                                                                          , .us_axi_bresp(w_port__AXI_Protocol_Converter_0__us_axi_bresp)
                                                                          , .us_axi_bvalid(w_port__AXI_Protocol_Converter_0__us_axi_bvalid)
                                                                          , .us_axi_bready(w_port__AXI_Protocol_Converter_0__us_axi_bready)
                                                                          , .us_axi_arid(w_port__AXI_Protocol_Converter_0__us_axi_arid)
                                                                          , .us_axi_araddr(w_port__AXI_Protocol_Converter_0__us_axi_araddr)
                                                                          , .us_axi_arlen(w_port__AXI_Protocol_Converter_0__us_axi_arlen)
                                                                          , .us_axi_arsize(w_port__AXI_Protocol_Converter_0__us_axi_arsize)
                                                                          , .us_axi_arburst(w_port__AXI_Protocol_Converter_0__us_axi_arburst)
                                                                          , .us_axi_arlock(w_port__AXI_Protocol_Converter_0__us_axi_arlock)
                                                                          , .us_axi_arcache(w_port__AXI_Protocol_Converter_0__us_axi_arcache)
                                                                          , .us_axi_arprot(w_port__AXI_Protocol_Converter_0__us_axi_arprot)
                                                                          , .us_axi_arqos(4'b0)
                                                                          , .us_axi_arvalid(w_port__AXI_Protocol_Converter_0__us_axi_arvalid)
                                                                          , .us_axi_arready(w_port__AXI_Protocol_Converter_0__us_axi_arready)
                                                                          , .us_axi_rid(w_port__AXI_Protocol_Converter_0__us_axi_rid)
                                                                          , .us_axi_rdata(w_port__AXI_Protocol_Converter_0__us_axi_rdata)
                                                                          , .us_axi_rresp(w_port__AXI_Protocol_Converter_0__us_axi_rresp)
                                                                          , .us_axi_rlast(w_port__AXI_Protocol_Converter_0__us_axi_rlast)
                                                                          , .us_axi_rvalid(w_port__AXI_Protocol_Converter_0__us_axi_rvalid)
                                                                          , .us_axi_rready(w_port__AXI_Protocol_Converter_0__us_axi_rready)
                                                                          , .aclk(w_port__AXI_Protocol_Converter_0__aclk)
                                                                          , .aresetn(w_port__AXI_Protocol_Converter_0__aresetn)
                                                                          , .ds_axi_awaddr(w_port__AXI_Protocol_Converter_0__ds_axi_awaddr)
                                                                          , .ds_axi_awprot(w_port__AXI_Protocol_Converter_0__ds_axi_awprot)
                                                                          , .ds_axi_awvalid(w_port__AXI_Protocol_Converter_0__ds_axi_awvalid)
                                                                          , .ds_axi_awready(w_port__AXI_Protocol_Converter_0__ds_axi_awready)
                                                                          , .ds_axi_wdata(w_port__AXI_Protocol_Converter_0__ds_axi_wdata)
                                                                          , .ds_axi_wstrb(w_port__AXI_Protocol_Converter_0__ds_axi_wstrb)
                                                                          , .ds_axi_wvalid(w_port__AXI_Protocol_Converter_0__ds_axi_wvalid)
                                                                          , .ds_axi_wready(w_port__AXI_Protocol_Converter_0__ds_axi_wready)
                                                                          , .ds_axi_bresp(w_port__AXI_Protocol_Converter_0__ds_axi_bresp)
                                                                          , .ds_axi_bvalid(w_port__AXI_Protocol_Converter_0__ds_axi_bvalid)
                                                                          , .ds_axi_bready(w_port__AXI_Protocol_Converter_0__ds_axi_bready)
                                                                          , .ds_axi_araddr(w_port__AXI_Protocol_Converter_0__ds_axi_araddr)
                                                                          , .ds_axi_arprot(w_port__AXI_Protocol_Converter_0__ds_axi_arprot)
                                                                          , .ds_axi_arvalid(w_port__AXI_Protocol_Converter_0__ds_axi_arvalid)
                                                                          , .ds_axi_arready(w_port__AXI_Protocol_Converter_0__ds_axi_arready)
                                                                          , .ds_axi_rdata(w_port__AXI_Protocol_Converter_0__ds_axi_rdata)
                                                                          , .ds_axi_rresp(w_port__AXI_Protocol_Converter_0__ds_axi_rresp)
                                                                          , .ds_axi_rvalid(w_port__AXI_Protocol_Converter_0__ds_axi_rvalid)
                                                                          , .ds_axi_rready(w_port__AXI_Protocol_Converter_0__ds_axi_rready) );

    system_Utility_Vector_Logic_0 system_Utility_Vector_Logic_0_Inst ( 
                                                                        .vector_a(w_port__Utility_Vector_Logic_0__vector_a)
                                                                      , .result_vector(w_port__Utility_Vector_Logic_0__result_vector) );

    system_Constant_3 system_Constant_3_Inst ( 
                                                .dout(w_port__Constant_3__dout) );

    system_uivtc_0 system_uivtc_0_Inst ( 
                                          .I_vtc_clk(w_port__uivtc_0__I_vtc_clk)
                                        , .I_vtc_rstn(w_port__uivtc_0__I_vtc_rstn)
                                        , .O_vtc_vs(w_port__uivtc_0__O_vtc_vs)
                                        , .O_vtc_hs(w_port__uivtc_0__O_vtc_hs)
                                        , .O_vtc_de_valid(w_port__uivtc_0__O_vtc_de_valid)
                                        , .O_vtc_user()
                                        , .O_vtc_last() );

    system_uihdmi_tx_0 system_uihdmi_tx_0_Inst ( 
                                                  .I_pixel_clk(w_port__uihdmi_tx_0__I_pixel_clk)
                                                , .I_serial_clk(w_port__uihdmi_tx_0__I_serial_clk)
                                                , .I_rst(w_port__uihdmi_tx_0__I_rst)
                                                , .I_video_in_data(w_port__uihdmi_tx_0__I_video_in_data)
                                                , .I_video_in_de(w_port__uihdmi_tx_0__I_video_in_de)
                                                , .I_video_in_vs(w_port__uihdmi_tx_0__I_video_in_vs)
                                                , .I_video_in_hs(w_port__uihdmi_tx_0__I_video_in_hs)
                                                , .O_hdmi_clk_p(w_port__uihdmi_tx_0__O_hdmi_clk_p)
                                                , .O_hdmi_tx_p(w_port__uihdmi_tx_0__O_hdmi_tx_p) );

    system_uivbuf_0 system_uivbuf_0_Inst ( 
                                            .I_mm2s_tuser(w_port__uivbuf_0__I_mm2s_tuser)
                                          , .I_mm2s_tvalid(w_port__uivbuf_0__I_mm2s_tvalid)
                                          , .I_mm2s_tdata(w_port__uivbuf_0__I_mm2s_tdata)
                                          , .O_mm2s_tready(w_port__uivbuf_0__O_mm2s_tready)
                                          , .I_mm2s_tlast(w_port__uivbuf_0__I_mm2s_tlast)
                                          , .I_W_tuser(1'b0)
                                          , .I_W_tvalid(1'b0)
                                          , .I_W_tdata(32'b0)
                                          , .I_W_tlast(1'b0)
                                          , .O_W_tready()
                                          , .I_W_sync(1'b0)
                                          , .I_W_wclk(1'b0)
                                          , .I_ui_clk(w_port__uivbuf_0__I_ui_clk)
                                          , .I_ui_rstn(w_port__uivbuf_0__I_ui_rstn)
                                          , .I_R_sync(w_port__uivbuf_0__I_R_sync)
                                          , .I_R_rclk(w_port__uivbuf_0__I_R_rclk)
                                          , .O_s2mm_tuser()
                                          , .O_s2mm_tvalid()
                                          , .O_s2mm_tdata()
                                          , .I_s2mm_tready(1'b1)
                                          , .O_s2mm_tlast()
                                          , .I_R_tready(w_port__uivbuf_0__I_R_tready)
                                          , .O_R_tuser()
                                          , .O_R_tvalid()
                                          , .O_R_tdata(w_port__uivbuf_0__O_R_tdata)
                                          , .O_R_tlast()
                                          , .O_W_tlocked()
                                          , .O_R_tlocked(w_port__uivbuf_0__O_R_tlocked) );

endmodule

// Select the camera at a frame boundary; keep the Linux stream draining.
// Display switching must not indefinitely backpressure the existing VDMA.
module camera_display_mux(
 input wire window_ink,input wire pixel_clk,rst_n,request,vs,de,
 input wire[31:0]linux_pixel,camera_pixel,
 output wire[31:0]pixel,output wire linux_consume
);
 reg select1,select2,selected,previous_vs;
 always @(posedge pixel_clk or negedge rst_n)begin
  if(!rst_n)begin select1<=0;select2<=0;selected<=0;previous_vs<=0;end
  else begin
   select1<=request;select2<=select1;previous_vs<=vs;
   if(vs&&!previous_vs)selected<=select2;
  end
 end
 assign pixel=(selected||window_ink)?camera_pixel:linux_pixel;
 assign linux_consume=de;
endmodule

// Two response beats isolate the VDMA FIFO occupancy logic from PS RREADY.
// Ready depends only on local registered occupancy, not downstream ready.
module camera_axi_read_skid #(parameter integer WIDTH=67)(
 input wire clk,rst_n,s_valid,output wire s_ready,input wire[WIDTH-1:0]s_data,
 output wire m_valid,input wire m_ready,output wire[WIDTH-1:0]m_data
);
 reg[WIDTH-1:0] head,tail;
 reg[1:0] used;
 wire push=s_valid&&s_ready,pop=m_valid&&m_ready;
 // The asynchronously reset occupancy already forces VALID low in reset.
 // READY may be high during AXI reset; avoid a cross-clock reset data path.
 assign s_ready=used<2;
 assign m_valid=used!=0;
 assign m_data=head;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin used<=0;head<=0;tail<=0;end
  else case({push,pop})
   2'b10:begin if(used==0)head<=s_data;else tail<=s_data;used<=used+1;end
   2'b01:begin head<=tail;used<=used-1;end
   2'b11:head<=s_data;
  endcase
 end
endmodule
