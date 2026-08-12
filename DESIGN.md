# 星萌弹幕姬（Cutestar）Design System

## Objective

让线下活动的参与者在几秒内扫码、输入昵称、发送弹幕；让运营人员在高压现场快速审核和控场；让大屏把“正在发生的互动”展示得清楚、克制、可信。

## Product Context

星萌弹幕姬（Cutestar）是纯互动型活动弹幕平台，不包含霸屏、礼物、付费曝光或商业化装饰。主要场景是会议、发布会、年会和婚礼。产品由移动参与者 Web、桌面运营控制台和 Windows WPF 大屏组成。

## Visual Foundations

- Ink: `#17211B`，近黑绿，作为主要文字与大屏底色。
- Paper: `#F4F6F0`，低饱和浅灰绿，作为 Web 工作区背景。
- Signal: `#E06B3C`，暖橙红，只用于主要操作、待审提醒和重要结果。
- Field: `#B9D7C1`，柔和浅绿，用于成功、在线和通过状态。
- Mist: `#DDE6DE`，分隔线、禁用背景和低强调区域。
- Type: Web 使用 `Avenir Next`, `Segoe UI`, system-ui；数据与活动码使用 `Cascadia Code`, Consolas, monospace。大屏使用 `Segoe UI Variable`, `Segoe UI`, sans-serif。
- Scale: 12 / 14 / 16 / 20 / 28 / 40px，正文行高 1.5，标题行高 1.1。
- Layout: Web 以 8px 间距节奏、窄边框和清晰状态为主；大屏采用宽松的文字排布，不使用装饰性卡片。

## Accessibility

状态不能只通过颜色传达；焦点环必须可见；操作控件最小触控尺寸 44px；正文对比度满足 WCAG AA；动画支持 `prefers-reduced-motion`。

## Voice & Tone

短句、直接、告诉用户下一步。使用“发送”“通过”“撤回”“清屏”等动作词。错误说明原因和修复方式，不使用模糊的“出了点问题”。

## Implementation Practices

优先使用语义 HTML、可复用状态组件和 CSS 变量。移动参与者页面先做窄屏布局，控制台先保证桌面审核效率。数据页面必须有加载、空状态、错误和断线状态。

大屏渲染层通过 `IDanmakuRenderer` 接口抽象，同时维护软件渲染基础版（DrawingVisual，任何机器可运行）与 GPU 加速性能版（DirectComposition + D3D11/DirectWrite）。两套实现的视觉效果必须一致：文本抗锯齿、阴影（黑 70% 透明度偏移 1.5px）、白色弹幕使用 Signal 以外的纯色，不因渲染后端不同而产生观感差异。GPU 版启动失败或设备丢失时自动降级到软件版，视觉不中断。

## Anti-Patterns

- 不使用渐变营销首屏、紫蓝科技风或发光粒子。
- 不使用六块同构圆角卡片作为功能说明。
- 不用 emoji 代替功能图标或状态含义。
- 不在大屏堆叠排行榜、商业入口和无关统计。
- 不把每个动作都做成实心主按钮；危险操作需要明确确认。

## Decision-Making

当“好看”和“现场可读、可控”冲突时，优先现场可读、可控。新增视觉元素必须解释它如何帮助参与者、运营或观众完成任务。

## Workflow

先冻结领域状态和实时事件，再实现页面；先验证 375px 参与者页面与 16:9 大屏，再扩展主题配置。每个活动主题只允许改变颜色、字号和动效速度，不改变交互层级。
