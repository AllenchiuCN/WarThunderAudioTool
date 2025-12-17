---

# War Thunder Audio Tool  
一个用于 **War Thunder 音频资源解包、提取、还原与目录重建** 的自动化工具。

---

## ✨ 功能特点

- 🎵 **调用 QuickBMS 解包 `.assets.bank` 文件**  
- 🔊 **提取 `.assets.bank` 中的音频资源（FSB/RAW/WAV/OGG 等）**
- 📁 **自动匹配并恢复 FMOD Studio 所需的目录结构**  
- 🧩 **完整修复Audio Table**
- 🚀 **后台线程执行，不阻塞 UI**


---

## 🖥️ 系统要求

- Windows 10 / 11（64 位）
- Python 3.10+
- ≥ 1GB 可用内存

---

## 📦 安装方法

### 方法一：使用可执行文件（推荐）

1. 从 **发布页面** 下载最新版本  
2. 解压到任意目录  
3. 运行 `WarThunderAudioTool.exe`

### 方法二：从源代码运行

```bash
# 克隆项目后安装依赖
uv pip install -r requirements.txt

# 运行主程序
cd src
python main.py
```

---

## 🛠️ 使用说明

1. **游戏目录**：选择 War Thunder 安装目录 
2. **扫描游戏目录**：扫描游戏目录下的所有 `.assets.bank` 文件
2. **选择参考目录**：如：fmod_studio_warthunder_for_modders/Assets/dialogs_wt_tanks_2023/russian_new/ 
3. **选择输出目录**：选择处理后文件的输出位置  

    - 修补 `_crew_dialogs_ground_zh`：  
    - 输出目录：`Assets/dialogs_wt_tanks_2023/chinese`  
    - 参考目录 `_crew_dialogs_ground_ru` `Assets/dialogs_wt_tanks_2023/russian_new`的结构  
    - 提取`_crew_dialogs_ground_zh.assets.bank`中的音频文件
    - 按文件名（忽略扩展名）进行严格匹配并复制到`chinese`目录
    - 最终`chinese`目录文件结构和`russian_new`保持一致，提取的音频文件也会保持一致

4. **勾选防呆设计择操作模式**：  
   - ✔ 解包 Bank 文件  
   - ✘ 注意覆盖输出目录  
5. **开始执行**：点击“开始执行”  
6. **查看日志**：实时显示处理进度与结果

---

## 🧱 项目结构

```
WarThunderAudioTool/
├── src/
│   ├── main.py            # 主程序
│   ├── build.py           # 打包脚本
│   ├── Script.bms         # QuickBMS 脚本
│   ├── quickbms.exe       # QuickBMS 工具
│   └── fsb_aud_extr.exe   # FSB 提取工具
├── ui/
│   └── favicon.ico        # 图标
├── requirements.txt
└── README.md
```

---

## 🔧 依赖工具

- **QuickBMS**：解包 `.bank` 文件  
  https://aluigi.altervista.org/quickbms.htm  
- **FSB Extractor（fsbext）**：提取 FSB 音频  
  https://aluigi.altervista.org/papers.htm  
- **FMOD Studio & FMOD Libraries**：音频处理  
  https://www.fmod.com  

>⚠️本程序需同一目录下包含以下工具⚠️：
      quickbms.exe
      Script.bms
      fsb_aud_extr.exe
      fmodex.dll
      fmodL.dll
      fmod_extr.exe。

---

## 🔨 构建可执行文件

```bash
cd src
python build.py
```

构建完成后，EXE 位于 `src/dist/`。

---

## 📜 许可证

MIT License

---

## ⚠️ 注意事项

- 本工具仅用于学习与研究  
- 请遵守 War Thunder 用户协议  
- 操作前建议备份原始文件  

---

## 📝 更新日志

### v1.0
- 初始版本发布  
- 支持 `.bank` / `.assets` 解包  
- 支持音频提取与目录结构恢复  
- 优化 UI 与日志输出  
- 修复路径处理问题  

