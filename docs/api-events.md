# API 与事件契约

## HTTP API

### 鉴权

- `POST /api/v1/auth/admin/login`：`{username, password}`，返回管理员 Bearer JWT。
- 管理端接口要求 `Authorization: Bearer <admin-token>`；投稿接口要求 `Authorization: Bearer <参与会话令牌>`（join 返回的 `session_token`）。

### 参与者

- `GET /api/v1/public/activities/{code}`：获取活动公开信息。
- `POST /api/v1/public/activities/{code}/join`：创建匿名活动会话，返回 `session_token`。
- `POST /api/v1/public/danmaku`：提交弹幕（需参与者令牌），支持 `Idempotency-Key` 请求头去重。

### 管理端

- `GET /api/v1/activities`：活动列表（含全部显示设置字段），供控制台切换管理。
- `POST /api/v1/activities`：创建活动（`{name, public_code}`，活动码自动转大写，重复返回 409）。
- `PUT /api/v1/activities/{activity_id}`：更新活动（`{name?, status?, auto_moderation_enabled?}`，部分更新；状态变更广播 `activity.status_changed`）。
- `DELETE /api/v1/activities/{activity_id}`：删除活动（级联清除其事件、弹幕、参与者，返回 204）。
- `GET /api/v1/activities/{activity_id}/moderation-queue`：获取审核队列。
- `POST /api/v1/danmaku/{danmaku_id}/approve`：通过并广播。
- `POST /api/v1/danmaku/{danmaku_id}/reject`：拒绝并记录原因。
- `POST /api/v1/activities/{activity_id}/controls`：暂停、慢速或清屏。
- `PUT /api/v1/activities/{activity_id}/danmaku-settings`：弹幕颜色设置（`color_mode`：fixed/random，`default_color`，`allow_custom_color`）。
- `PUT /api/v1/activities/{activity_id}/overlay-settings`：大屏显示设置（`font_size`、`speed`、`opacity`、`font`），由大屏客户端按 `UseServerSettings` 决定是否采用。
- `GET /api/v1/activities/{activity_id}/stats`：统计（`online_count`、`published_count`）。
- `POST /api/v1/activities/{activity_id}/lottery/draw`：服务端开奖。
- `POST /api/v1/activities/{activity_id}/exports`：创建导出任务。

### 大屏

- `POST /api/v1/screens/pair`：一次性配对码换取设备令牌。
- `GET /api/v1/screens/{screen_id}/snapshot`：获取展示快照。
- `POST /api/v1/screens/{screen_id}/heartbeat`：设备心跳。

## WebSocket 事件

所有事件包含：`event_id`、`sequence`、`activity_id`、`type`、`occurred_at`、`payload`。

首版事件：`activity.status_changed`、`activity.control_changed`、`activity.danmaku_settings_changed`、`activity.overlay_settings_changed`、`danmaku.published`、`danmaku.revoked`、`screen.clear_requested`、`lottery.winner_selected`。

客户端保存最大确认序列号。重连时通过查询参数 `?last_sequence=N` 携带上次确认的序列号，服务端从该位置开始回放，避免重复渲染历史事件。连接建立后，客户端每收到一条事件应发送 `{"last_sequence": N}` 确认。

断线补偿（连接时回放的历史事件）在信封上附加 `"replay": true` 标记，客户端据此对补偿弹幕做随机延时错峰展示，避免一股脑刷屏；实时事件不带该标记，立即上屏。

### 自动审核

当活动开启 `auto_moderation_enabled` 时，提交弹幕将自动调用阿里云内容安全 API（`comment_detection` 服务）：
- `Labels` 为空 → 自动通过（`danmaku.published`）
- `riskLevel=high` → 自动拒绝（`danmaku.rejected`）
- `riskLevel=medium/low` → 保留人工复核（`danmaku.pending_created`）
- API 异常/超时 → 降级为人工复核

配置项：`CUTESTAR_ALIBABA_ACCESS_KEY_ID`、`CUTESTAR_ALIBABA_ACCESS_KEY_SECRET`、`CUTESTAR_ALIBABA_GREEN_ENDPOINT`、`CUTESTAR_ALIBABA_GREEN_SERVICE`。
