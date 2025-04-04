# PF-MCDR-WebUI
为 MCDR 开发的在线 WebUI 插件

[![页面浏览量计数](https://badges.toozhao.com/badges/01JC0ZMB6718E924N6H2FEZRC5/green.svg)](/) 
[![查看次数起始时间](https://img.shields.io/badge/查看次数统计起始于-2024%2F11%2F06-2?style=flat-square)](/)
[![仓库大小](https://img.shields.io/github/repo-size/LoosePrince/PF-MCDR-WebUI?style=flat-square&label=仓库占用)](/) 
[![最新版](https://img.shields.io/github/v/release/LoosePrince/PF-MCDR-WebUI?style=flat-square&label=最新版)](https://github.com/LoosePrince/PF-MCDR-WebUI/releases/latest/)
[![议题](https://img.shields.io/github/issues/LoosePrince/PF-MCDR-WebUI?style=flat-square&label=Issues)](https://github.com/LoosePrince/PF-MCDR-WebUI/issues) 
[![已关闭issues](https://img.shields.io/github/issues-closed/LoosePrince/PF-MCDR-WebUI?style=flat-square&label=已关闭%20Issues)](https://github.com/LoosePrince/PF-MCDR-WebUI/issues?q=is%3Aissue+is%3Aclosed)
[![下载量](https://img.shields.io/github/downloads/LoosePrince/PF-MCDR-WebUI/total?style=flat-square&label=下载量)](https://github.com/LoosePrince/PF-MCDR-WebUI/releases)
[![最新发布下载量](https://img.shields.io/github/downloads/LoosePrince/PF-MCDR-WebUI/latest/total?style=flat-square&label=最新版本下载量)](https://github.com/LoosePrince/PF-MCDR-WebUI/releases/latest)

> [!NOTE]
> 由于 **GUGUbot** 和 **WebUI** 项目庞大，但迄今为止仅有开发者一名，所以我们从现在开始招募有志者加入我们！<br>
> 有意者请加 QQ[1377820366](http://wpa.qq.com/msgrd?v=3&uin=1377820366&site=qq&menu=yes) 或 QQ群[726741344](https://qm.qq.com/q/TqmRHmTmcU)

## 插件说明

- [x] **主要功能:** 为MCDR提供一个 `在线WebUI管理界面` 和 `MCDR插件管理` 和 `表单配置功能`（可选使用在线编辑器）。
- [x] **本地插件管理:** 提供列出全部插件、一键更新 、启动插件、停止插件、重载插件、插件配置修改（需要符合格式）。
- [x] **在线插件仓库:** 提供一个简化的在线插件仓库，可以查看来自在线仓库的插件的信息和一键安装。 
- [x] **配置修改:** 使用在线表单 **或** 在线编辑器进行配置文件的修改（在 **`所有插件`** 选项卡处修改）。
- [x] **支持的配置:** `yaml` 格式或者 `json` 文件。
  - `yml文件` 识别每项上一行注释作为中文标题，使用 `::` 分割，第二项为副标题，例 `标题::副标题` ，请注意，使用的是英文的符号；
  - `json文件` 需要创建同级文件 `需要加标题的配置文件名_lang.josn` 例如 `abc_lang.json` 则会为 `abc.json` 创建中文标题，使用 `[标题,副标题]` 创建标题和副标题，参考示例: [config_lang.json](https://github.com/LoosePrince/PF-MCDR-WebUI/blob/main/config_lang.json)
  - `html格式`, 使用 `main.json` 在其中使用键对值的方式指定每个配置文件对应的 `html文件` ，届时加载时会加载 `html文件内容` ，请不要使用相对路径的文件，如 `/1.css` 、`/2.js` 。
- [x] **服务器终端:** 提供服务器命令执行界面，支持RCON实时反馈和命令历史记录。
- [x] **AI辅助:** 集成DeepSeek AI接口，支持日志分析和问题解答，减少您的反复横跳。
- [x] **主题切换:** 支持`浅色主题`、`深色主题`、`自动`，默认为自动，需要登录后修改显示模式。
<!-- - [x] **自定义:** 支持 `全局css和js配置文件` ，在首页提供在线编辑。 -->

> [!IMPORTANT]
> **关于数据:** 重载插件 *本插件* **会** 自动更新 `guguwebui_static` 文件夹中的内容，如果您修改过内部的文件请自行保存，以防您的数据丢失。

> [!IMPORTANT]
> **关于V1.3.0版本:** 本项目于v1.3.0版本重构前端，更新请删除 `guguwebui_static` 文件夹中的内容，保留 `db.json` 即可。


## 依赖配置

**Python 包:** 请确保已安装 [Python™](https://www.python.org/) 和 [pip](https://pypi.org/project/pip/) (pip通常在安装完python后会默认安装)。

**Python 模块:** 参考插件目录内的 `requirements.txt` 文件，使用命令 `pip install -r requirements.txt` 进行安装。

**前置插件:** 无

## 使用方式

> 目前未对接GUGUbot账号系统；当账号为QQ号时会显示QQ头像和昵称作为管理员名称和头像。

**创建账户**

```bash
!!webui create <username> <password>
```

**更改密码**

```bash
!!webui change <username> <old password> <newpassword>
```

**临时密码**

```bash
!!webui temp
```

## Q&A 问答

Q:为什么要开发这个插件。<br>
A:因为我乐意。

Q:会支持MC服务器管理的功能吗？如模组管理，玩家管理，白名单等等..<br>
A:并不会深入涉及管理MC服务器，如有这方面的需求请查询MC服务器面板，仅可能会支持很小一部分，例如终端、重启服务器，更多的不在我们的范畴中。

Q:可以加入开发吗？<br>
A:当然可以，您可以提交 pr 或者 参与交流 来参与开发。

Q:UI为什么这么丑（不美观...）<br>
A:实力受限，但是我们提供自定义 css 和 js ，您可以自行修改甚至提交给我们以进行采纳，我们会将你加入贡献名单中。

Q:会支持多语言吗。<br>
A:我只会中文，你要是愿意可以参与。

Q:为什么有私货（有未使用的插件，如gugubot等）。<br>
A:因为这就是为它所开发。

Q:如何获取实时最新版<br>
A:自己打包`src`中的文件到`zip`，修改后缀为`.mcdr`，或者前往 [actions](https://github.com/LoosePrince/PF-MCDR-WebUI/actions/workflows/package-src.yml) 下载

Q:我有个插件，我觉得很适合WebUI，可以作为WebUI的前置吗？<br>
A:WebUI不打算使用任何插件前置，如果有好的方案我们会考虑直接加入WebUI并在关于页感谢贡献。

## 示例图

> 截图来源本地测试

![image](https://github.com/user-attachments/assets/bc13de19-4820-4a36-863a-d582a5562669)
![image](https://github.com/user-attachments/assets/07c5a028-aca8-44a4-bb9b-7905a34e4202)
![image](https://github.com/user-attachments/assets/cb611ca7-76a3-4bf7-a8b6-3442fff1289f)
![image](https://github.com/user-attachments/assets/65a57053-2c69-4055-9307-e4287efc21ae)
![image](https://github.com/user-attachments/assets/2d56a5b6-b032-4c69-8f78-fd9badec4bc3)
![image](https://github.com/user-attachments/assets/b7279f3e-cfd6-4b76-9e8d-cb2537a832fd)
![image](https://github.com/user-attachments/assets/64abc5d6-0a46-493c-a44c-0df529a28c60)
![image](https://github.com/user-attachments/assets/f881dece-af2e-40d4-bae6-dd9fe79339d1)
![image](https://github.com/user-attachments/assets/e6f0d65d-4aa4-4c75-a55a-77b7ceff3f56)
![image](https://github.com/user-attachments/assets/a73ec836-b3e1-4a0d-9502-bbbbe42e4006)



## 开发进度

- 首页:100%
  - 主要功能:100%
- GUGUbot管理:0%
  - 配置:0%
  - 附加功能:0%
- cq-qq-api:100%
  - 配置:100%
- MC服务器配置:100%
- MCDR配置:100%
- 本地插件管理:100%
  - 管理:100%
  - 更新:100%
  - 配置修改:100%
  - 附加功能:100%
- 在线插件（插件仓库）:100%
  - 一键安装:100%
  - 搜索:100%
- 服务器终端:100%
  - 命令执行:100%
  - RCON支持:100%
  - AI辅助:100%
- Fabric（部分）:0%

# TODO

- [ ] [[更新] 关于后续（饼）](https://github.com/LoosePrince/PF-MCDR-WebUI/issues/8) #8

# 有BUG或是新的IDEA

如果需要更多联动或提交想法和问题请提交 [issues](https://github.com/LoosePrince/PF-MCDR-WebUI/issues) 或 QQ [树梢 (1377820366)](http://wpa.qq.com/msgrd?v=3&uin=1377820366&site=qq&menu=yes) 提交！ <br />
如需要帮助或者交流请通过 QQ群 [726741344](https://qm.qq.com/q/TqmRHmTmcU) 进行询问或者交流 <br />
视情况添加，请勿联系他人。

# 贡献

| 贡献人 | 说明 |
|---|---|
| [树梢 (LoosePrince)](https://github.com/LoosePrince) | 功能设计、文档编写、Web设计、前端编写 |
| [雪开 (XueK66)](https://github.com/XueK66) | 代码开发、维护、功能设计 |


| 贡献项目 | 功能 | 备注 |
|---|---|---|
| [Ace Editor](https://ace.c9.io/) | 在线编辑器 | 已不再使用 |
| [CodeMirror](https://codemirror.net/) | 在线编辑器 | 目前使用 |
| [MC-Server-Info](https://github.com/Spark-Code-China/MC-Server-Info) | Python Minecraft 服务器信息查询 | 仓库被作者删除 |
| [DeepSeek AI](https://deepseek.com/) | AI辅助功能接口支持 | |


| 特别鸣谢 | 说明 |
|---|---|
| 反馈者 | 感谢你们的反馈 |
| [ChatGPT](https://chatgpt.com) | ChatGPT协助编写 |
| [Cursor](https://cursor.com/) | Cursor协助编写 |
