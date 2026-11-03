# F3P 六轴机械臂工程

基于安路飞龙 SoC 的六轴视觉分拣与移动底盘系统。仓库按最后一次有据可查的板端安装回执及 FPGA 工程引用，离线整理当前版本。

## 代码分类

| 目录 | 内容 |
|---|---|
| 01_FPGA | TD 工程、Verilog RTL、约束、IP 描述及启动产物 |
| 02_ARM机械臂主控 | GTK 界面、零位、运动学、轨迹规划、抓取和绘图 |
| 03_底盘与夹爪 | 小车与夹爪 C 源码、头文件及服务配置 |
| 04_相机与YOLO视觉 | 相机采集、六类模型、YOLO 推理与结果解码 |
| 05_语音与NPU共享运行时 | 语音识别、模型及板端 NPU 依赖 |
| 06_电脑同屏 | noVNC、视频显示、SSH 转发及重连程序 |
| 07_板端显示与启动 | 板端桌面服务及启动配置 |

同一内容只保存一份，原路径通过 index.json 映射到对应文件。本次整理覆盖 563 个原路径、557 份独立文件。

## 阅读入口

- FPGA 从 01_FPGA/工程/vision60.prj 和 RTL/robot_arm_system_top.v 开始。
- ARM 从 02_ARM机械臂主控/robot_arm_gui/gtk_app.py 开始。
- 抓取、绘图和回零分别见 grasp_motion.py、drawing_motion.py 和 zero_home.py。
- 小车任务见 03_底盘与夹爪/Source 中的 mission、parking 和 console 模块。
- 目录说明和版本边界见 [先读我](先读我.md)。

## 还原目录

使用 Python 3 在仓库根目录运行下列命令。目标目录应尚不存在。

```shell
python restore.py D:/F3P-restored
```

脚本逐文件校验 SHA256 后还原 project、rootfs 和 build-source 目录。更换电脑时，需要调整 TD 工程中的绝对路径并安装对应开发工具。

## 版本与验收范围

六轴使用 ARM 规划与 PL 轨迹队列执行的心跳修复版本，并含程序二 200 cm＋Z、50 cm 路线和视觉缓冲过期修复。整理工作未重新读取板卡。index.json 提供文件来源、依据与缺项。

当前缺少与安装记录散列一致的 f3p_drive174 可执行文件，对应 C 源码与头文件已经收录。源码一致性和目录还原已核验，整机实物性能以对应工况测试为准。

## 第三方组件

noVNC、websockify、NPU 运行库和厂商 FPGA IP 保留各自的权利与许可。使用这些组件时遵守相应原始许可证及开发工具要求。
