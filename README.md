# ESP32-S3 二号板：彩屏桌面信息台

MicroPython 桌面屏：128×160 ST7735 彩屏显示时间、徐州天气、出门提示与 25 分钟专注计时。可选接 SHT3x 显示室内温湿度。项目还保留了 MAX98357A 喇叭与 I²S 麦克风的独立测试代码；它们不是桌面信息主程序的必需器件。

## 接线

以下是经彩屏实物测试的引脚。`ST7735.TFT(spi, A0, RESET, CS)` 的参数顺序很容易接错；本项目使用 `TFT(spi, 10, 8, 9)`。接线前先断开 USB，核对模块丝印和供电排针，确认没有短接后再通电。

| 模块 | 模块引脚 | ESP32-S3 GPIO / 电源 |
| --- | --- | --- |
| ST7735 彩屏 | LED, SCK, SDA/MOSI | 7, 12, 11 |
| ST7735 彩屏 | A0/DC, RESET, CS | 10, 8, 9 |
| SHT3x（可选） | SCL, SDA, VCC, GND | 17, 18, 3V3, GND |
| MAX98357A（独立音频实验） | BCLK, LRC/WS, DIN, SD | 4, 5, 6, 14 |
| I²S 麦克风（独立实验） | SCK, WS, SD | 15, 16, 21 |

功放供电以你手中模块和板卡丝印核对；先前二号板实测使用板上 5Vin。喇叭接在 MAX98357A 的两路扬声器输出之间，**喇叭负端不接 ESP32 GND**。麦克风的 VDD 使用 3V3、GND 共地，L/R 接地以选左声道。旧接线图有未验证的 5V 和屏幕脚位版本，因此这里以表格和当前源代码为准。

## 部署

刷入 ESP32-S3 版 MicroPython，并确保固件具备 `requests` 与 `ntptime` 模块。复制 `wifi_config.example.py` 为 `wifi_config.py`，填入自己的 2.4 GHz Wi-Fi；该私有文件已列入 `.gitignore`。把 `ST7735.py`、`desk_info.py`、`sht3x.py`、`font_data.py`、`desk_bg.bin`、`wifi_config.py` 上传到板上文件系统根目录，最后上传 `main.py` 并重启。`main.py` 调用 `desk_info.run()`。

在电脑已装 `mpremote` 时，可以逐个执行 `mpremote connect COMx resume fs cp 本地文件 :板上文件名`；`COMx` 应使用本次设备管理器实际列出的端口。二号板曾使用带 `COM` 标记的 USB-C 口，历史 COM 号不能直接照搬。

短按 BOOT 切换页面；长按约 1 秒启动/暂停专注计时，长按约 3 秒重置。天气与空气质量来自 Open-Meteo 的区域预报，**不是室内传感器实测**。断网时可能保留上次成功的天气数据；SHT3x 未连接时室内读数显示占位符。

## 音频与其他实验

- `voice.py` 播放 16 kHz、16 位、双声道原始 PCM。为了避免公开个人录音，仓库不含原先的 `hello_2.pcm`；可运行 `python examples/generate_test_tone.py` 生成无语音的测试音，再把 `test_tone.pcm` 上传到板上，调用 `voice.play('test_tone.pcm')`。
- `examples/mic_test.py`、`examples/screen_pin_order_test.py` 为独立硬件检查程序，不作开机入口。
- `desk_bg.bin` 是已经生成好的彩屏背景资源。`ST7735.py` 的文件头保留原驱动作者归属信息。

此前的实物验证包括彩屏 RGB 测试、页面自动切换、扬声器发声以及麦克风有非零采样；不据此推断当前所有外设同时接在二号板上。SHT3x 后来被移到一号板，二号板上是否安装需按实物确认。
