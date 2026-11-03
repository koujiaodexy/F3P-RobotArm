//==============================================================================
// 视频时序生成器模块 (Video Timing Generator - VTG)
// 功能：生成标准视频时序信号，支持可配置的分辨率和时序参数
// 作者：anlogic
// 日期：2025年9月14日
//==============================================================================

module vtg_v01_727902e0178c
#(
    parameter COUNTER_WIDTH = 12                // 计数器位宽，支持最大4095像素/行
)(
    // 时钟和复位接口
    input  wire                     clk,        // 像素时钟输入
    input  wire                     rst_n,      // 异步复位信号，低电平有效
    input  wire                     vtg_ce,     // 时序生成使能信号，高电平有效
    
    // 水平时序参数配置接口
    input  wire [COUNTER_WIDTH-1:0] h_active,   // 水平有效像素数
    input  wire [COUNTER_WIDTH-1:0] h_front,    // 水平前肩时间
    input  wire [COUNTER_WIDTH-1:0] h_sync,     // 水平同步脉冲宽度
    input  wire [COUNTER_WIDTH-1:0] h_back,     // 水平后肩时间
    
    // 垂直时序参数配置接口  
    input  wire [COUNTER_WIDTH-1:0] v_active,   // 垂直有效行数
    input  wire [COUNTER_WIDTH-1:0] v_front,    // 垂直前肩时间
    input  wire [COUNTER_WIDTH-1:0] v_sync,     // 垂直同步脉冲宽度
    input  wire [COUNTER_WIDTH-1:0] v_back,     // 垂直后肩时间
    
    // 时序信号输出接口
    output reg                      vtg_hsync,   // 水平同步信号
    output reg                      vtg_vsync,   // 垂直同步信号
    output reg                      vtg_hblank,  // 水平消隐信号
    output reg                      vtg_vblank,  // 垂直消隐信号
    output reg                      vtg_de,      // 数据使能信号
    
    // 位置信息输出接口
    output wire [COUNTER_WIDTH-1:0] vtg_h_count, // 当前水平位置计数
    output wire [COUNTER_WIDTH-1:0] vtg_v_count, // 当前垂直位置计数
    
    // 状态指示输出接口
    output reg                      vtg_frame_start, // 帧起始脉冲
    output reg                      vtg_line_start,  // 行起始脉冲
    output wire                     vtg_active_video // 有效视频区域标志
);

/* 
时序图说明：

水平时序 (一行):
|<----------------------- H_TOTAL ------------------------->|
|<-Sync->|<-Back->|<-----Active Video---->|<-Front->|
|        |        |                       |         |
|________|________|_______________________|_________|
0      H_SYNC  H_SYNC+   H_SYNC+H_BACK+    H_TOTAL
              H_BACK    H_BACK+H_ACTIVE

垂直时序 (一帧):
|<----------------------- V_TOTAL ------------------------->|
|<-Sync->|<-Back->|<-----Active Video---->|<-Front->|
|        |        |                       |         |
|________|________|_______________________|_________|
0      V_SYNC  V_SYNC+   V_SYNC+V_BACK+    V_TOTAL
              V_BACK    V_BACK+V_ACTIVE

信号含义：
- Sync: 同步脉冲期间，HSYNC/VSYNC为低电平
- Back: 同步脉冲后的后肩时间
- Active Video: 有效视频数据传输期间
- Front: 前肩时间，准备下一个同步脉冲
*/

//==============================================================================
// 内部信号定义
//==============================================================================
reg  [COUNTER_WIDTH-1:0] h_counter;            // 水平扫描计数器
reg  [COUNTER_WIDTH-1:0] v_counter;            // 垂直扫描计数器

wire [COUNTER_WIDTH-1:0] h_total;              // 水平总周期
wire [COUNTER_WIDTH-1:0] v_total;              // 垂直总周期

wire [COUNTER_WIDTH-1:0] h_sync_end;           // 水平同步结束位置
wire [COUNTER_WIDTH-1:0] h_back_end;           // 水平后肩结束位置  
wire [COUNTER_WIDTH-1:0] h_active_end;         // 水平有效区结束位置

wire [COUNTER_WIDTH-1:0] v_sync_end;           // 垂直同步结束位置
wire [COUNTER_WIDTH-1:0] v_back_end;           // 垂直后肩结束位置
wire [COUNTER_WIDTH-1:0] v_active_end;         // 垂直有效区结束位置

wire h_counter_max;                            // 水平计数器到达最大值
wire v_counter_max;                            // 垂直计数器到达最大值

`pragma protect begin_protected
`pragma protect version = 1
`pragma protect encrypt_agent = "Anlogic"
`pragma protect encrypt_agent_info = "Anlogic Encryption Tool anlogic_2019"
`pragma protect key_keyowner = "Cadence Design Systems.", key_keyname = "CDS_RSA_KEY_VER_1"
`pragma protect key_method = "rsa"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 256)
`pragma protect key_block
iGDe174QOvlGg6aywFQXo7uWAhN4/9k0obvYWOWGusqCpX9dMpkOLvV7wn9pURJJ
SVc/k6ZrdDNN54sV3nhuoebBnew1pJT7xrjeSzcFzxk5klM/XPFpyB0LuSobaLEt
AH29AJGazQi9huI94TG7Uid9Arrcpb8c8zYWSAU51rNwORcwx6yzeWBNnYzBaEIW
3Pdv72fMiZwPyCaHLc6l4VLbXh7eqhvCUUDZ6vVDVPZdRmqR04y3M3R8e1LIzaqU
WT1w8/ICWtGI1T1T5KAUprM9gvKBqTlxa/shvKs5Iou0UTuWvWaWHONuz5HY/E/i
WjSC4J10hdZZX/ROXMGQ9g==
`pragma protect key_keyowner = "Mentor Graphics Corporation", key_keyname = "MGC-VERIF-SIM-RSA-1"
`pragma protect key_method = "rsa"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 128)
`pragma protect key_block
l0h7NRg/On5Dx1GbkkoiNzM4bC+6eT9ViAio4lpYNxma0uN6wih4hhZ6FxApwRvD
/2z+8eIPycdOWy0UQi8jO7G1vIsxHrh/drjoKGuNW/afFzmuH6+W8erpvHj6o1vc
P6gVW6u0emiyfnga4TCrq4yZyriMaa8UdwM5pNVqnog=
`pragma protect key_keyowner = "Mentor Graphics Corporation", key_keyname = "MGC-VERIF-SIM-RSA-2"
`pragma protect key_method = "rsa"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 256)
`pragma protect key_block
pz7npZw50nuSMdaeJCryzai6+SiicxpMF1Qh+kW4+9sOm2ud1QLskWgZuzOP3Zld
eDRuqoVvyHOrKEnNLe/UOn47reHUx9Yko7viXaJ3jVCCclgNCvPfR1XXCt9SX9pW
TCYnseV/NK2Hc9FTVJXaGNS1uzzpZu38P0xSq4q91NJ610RD/y544HU7C6MVDl2G
ZCMhdFsoCkzX9kbgj+iDM/UVbXpbDQNmBsYjF7MPr4c2LFDBfE4jIGcS+jPPOnbY
O/cTt3YySriwPCkHTrl/pbxcveVfetL15rgrUhbGnmCaiRIoykVRdxAr/DtrmB37
JaEHfnO18/zyeqy0WB9XVw==
`pragma protect key_keyowner = "Synopsys", key_keyname = "SNPS-VCS-RSA-1"
`pragma protect key_method = "rsa"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 128)
`pragma protect key_block
1uCh/WCyGsSf/cIm05faD9XOK4wtO53xOv7TPpCsbJehpJAk+BM2vlto80OkCl+g
30rCL4ZAUisOCxASlNIX1GApgHFDx2eA47XkjmaX6gxjAIw1OFxTfX1MLmEhqZ8a
plbMWGsLxzRQWtzXt6aj0cAlDiHsN0t+w4H/qDZnpCA=
`pragma protect key_keyowner = "Synopsys", key_keyname = "SNPS-VCS-RSA-2"
`pragma protect key_method = "rsa"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 128)
`pragma protect key_block
mVQwPFmqTyJ2Oii57G06nfEQmH03W2WbdlFr608tBLW3BrwGiZwaHyWMGX6kaUae
Kcc9fIH4x+HLZoFxEf65kWfFxrod45JDOd86Y/vNIq3anZ4smHca5j+E7DtqOfzu
mufzbJLWYC+i8+moWMoXRW9Lx7YtLkO/ne/dy5PEG4M=
`pragma protect key_keyowner = "Anlogic", key_keyname = "anlogic-rsa-009"
`pragma protect key_method = "rsa"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 128)
`pragma protect key_block
m9qcOt5lHUz/F+lrpf6AiPTCWKXE3qqNfJG/HFNRiZ0nckVPx97nc4RMEMTbPAlf
9JGllIgoMFJ7ZH7Ezb7aOPNJkSQm4Bk5XljwMlN4C3xCMI0ALM9VstD55LiHiPF+
RlscFeoorMmSjhfzHHXPzK4LuaUOKjgOInTrRS6PuTI=
`pragma protect data_method = "AES128-CBC"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 5440)
`pragma protect data_block
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
nf3tkRZWdvHq6JdAMJpXrg==
`pragma protect end_protected
//==============================================================================
// 时序参数有效性检查 (仿真用)
//==============================================================================
`ifdef SIMULATION_727902e0178c
initial begin
    // 检查时序参数是否合理
    if (h_active == 0 || h_sync == 0) begin
        $error("VTG: Invalid horizontal timing parameters!");
    end
    if (v_active == 0 || v_sync == 0) begin
        $error("VTG: Invalid vertical timing parameters!");
    end
    
    // 显示配置信息
    $display("VTG Configuration:");
    $display("  H: Active=%0d, Front=%0d, Sync=%0d, Back=%0d, Total=%0d", 
             h_active, h_front, h_sync, h_back, h_total);
    $display("  V: Active=%0d, Front=%0d, Sync=%0d, Back=%0d, Total=%0d",
             v_active, v_front, v_sync, v_back, v_total);
end
`endif

endmodule
