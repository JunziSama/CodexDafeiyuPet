# dsh-pet-indesktop 动画调度方案

## 1. 图片识别结论

- 分析图片：历史菜单截图（204×303，76.9 KB；临时文件未纳入交付包）。
- 视觉特征：蓝发女仆装 Q 版角色，双臂前伸、握拳，身体略向左倾，表情专注，气泡文字为“正在使用工具执行任务。”
- 场景判定：**WORKING / 工具执行**，对应动作池中的“原地敲击桌面互动 / 写代码 / 玩游戏气急败坏”等桌面操作类动画。

## 2. 状态优先级

| 状态 | 优先级 | 说明 |
|---|---:|---|
| ERROR | 100 | ERROR 状态动画 |
| WAITING | 90 | WAITING 状态动画 |
| WORKING | 80 | WORKING 状态动画 |
| THINKING | 70 | THINKING 状态动画 |
| SUCCESS | 60 | SUCCESS 状态动画 |
| IDLE | 10 | IDLE 状态动画 |
| DISCONNECTED | 0 | DISCONNECTED 状态动画 |

## 3. 场景映射

| 场景 | 默认动画 | 切换后动画 | 备选/兜底 |
|---|---|---|---|
| IDLE | 待机呼吸休闲 |  | 全部 91 个动画按 LRU 轮播 |
| THINKING | 深度思考碎碎念、原地专心玩魔方、写代码 | 下五子棋、轻快记录、吃Token、照镜子 | 全部动画 LRU 轮播（覆盖 100%） |
| WORKING | 原地敲击桌面互动、写代码、玩游戏气急败坏 | 原地跳跃抓碎头顶物品、玩水枪、变鸽子、凭空生花 | 全部动画 LRU 轮播（覆盖 100%） |
| WAITING | 原地小憩沉眠、打瞌睡被惊醒 | 哈欠连天、超大伸懒腰、女仆屈膝礼仪、悠闲哼歌 | 全部动画 LRU 轮播（覆盖 100%） |
| SUCCESS | 点击回应 - 开心跃动 | 点击回应 - 元气挥手、点击回应 - 害羞惊讶、点击回应 - 傲娇生气 | 全部动画 LRU 轮播（覆盖 100%） |
| ERROR | 被吓一跳、玩游戏气急败坏 | 被吓一跳、用鲸鱼尾巴拍打地面 | 全部动画 LRU 轮播（覆盖 100%） |
| DISCONNECTED | 原地小憩沉眠 |  | 全部动画 LRU 轮播（覆盖 100%） |

## 4. 动画清单与触发场景

动画总数：91；唯一动画：91。

### click（5）

| 动画 | 触发场景 |
|---|---|
| 点击回应-傲娇生气 | CLICK/SUCCESS |
| 点击回应-元气挥手 | CLICK/SUCCESS |
| 点击回应-害羞惊讶 | CLICK/SUCCESS |
| 点击回应-开心跃动 | CLICK/SUCCESS |
| 点击回应-挠痒咯咯笑 | CLICK/SUCCESS |

### drag（1）

| 动画 | 触发场景 |
|---|---|
| 被鼠标拖拽悬空反馈 | DRAG |

### idle（1）

| 动画 | 触发场景 |
|---|---|
| 待机呼吸休闲 | IDLE |

### move（3）

| 动画 | 触发场景 |
|---|---|
| 原地左转奔跑 | MOVE/IDLE |
| 原地漂浮踏步 | MOVE/IDLE |
| 螃蟹走路 | MOVE/IDLE |

### random（80）

| 动画 | 触发场景 |
|---|---|
| 三球抛接 | IDLE·LRU |
| 下五子棋 | IDLE·LRU、TASK、THINKING |
| 中秋赏月吃月饼 | IDLE·LRU |
| 优雅女仆舞 | IDLE、IDLE·LRU |
| 偷吃零食被抓住 | IDLE·LRU |
| 写代码 | IDLE·LRU、TASK、THINKING、WORKING |
| 写福字 | IDLE·LRU |
| 凭空生花 | IDLE·LRU、WORKING |
| 动物环绕 | IDLE·LRU |
| 原地专心玩魔方 | IDLE·LRU、TASK、THINKING |
| 原地小憩沉眠 | DISCONNECTED、IDLE、IDLE·LRU、WAITING |
| 原地敲击桌面互动 | IDLE·LRU、TASK、WORKING |
| 原地跳跃抓碎头顶物品 | IDLE·LRU、WORKING |
| 原地蹲下玩玩具汽车 | IDLE·LRU |
| 原地重力下蹲压缩 | IDLE·LRU |
| 变鸽子 | IDLE·LRU、WORKING |
| 可爱宅舞 | IDLE、IDLE·LRU |
| 吃Token | IDLE·LRU、TASK、THINKING |
| 吃冰淇淋融化 | IDLE·LRU |
| 吃午餐 | IDLE·LRU |
| 吃大闸蟹 | IDLE·LRU |
| 吃年糕 | IDLE·LRU |
| 吃早餐 | IDLE·LRU |
| 吃晚餐 | IDLE·LRU |
| 吃汤圆 | IDLE·LRU |
| 吃白饭 | IDLE·LRU |
| 吃粽子 | IDLE·LRU |
| 吃糖葫芦 | IDLE·LRU |
| 吃腊八粥 | IDLE·LRU |
| 吃西瓜 | IDLE·LRU |
| 吃重阳糕 | IDLE·LRU |
| 吃长寿面 | IDLE·LRU |
| 吃青团 | IDLE·LRU |
| 吃饺子 | IDLE·LRU |
| 吹气球 | IDLE·LRU |
| 吹笛子 | IDLE·LRU |
| 哈欠连天 | IDLE、IDLE·LRU、WAITING |
| 堆雪人 | IDLE·LRU |
| 大口吃零食 | IDLE·LRU |
| 女仆屈膝礼仪 | IDLE·LRU、WAITING |
| 小幅度原地360度旋转展示 | IDLE·LRU |
| 小提琴演奏 | IDLE、IDLE·LRU |
| 悠闲哼歌 | IDLE、IDLE·LRU、WAITING |
| 扑克魔术 | IDLE·LRU |
| 打瞌睡被惊醒 | IDLE·LRU、WAITING |
| 抽陀螺 | IDLE·LRU |
| 拆礼物 | IDLE·LRU |
| 插茱萸赏菊 | IDLE·LRU |
| 摇扇纳凉 | IDLE·LRU |
| 撸猫 | IDLE、IDLE·LRU |
| 收红包 | IDLE·LRU |
| 放孔明灯 | IDLE·LRU |
| 放河灯 | IDLE·LRU |
| 放烟花 | IDLE·LRU |
| 放风筝 | IDLE·LRU |
| 整体换装试色 | IDLE·LRU |
| 是啊，吃什么 | IDLE·LRU |
| 晨间刷牙 | IDLE·LRU |
| 涮火锅 | IDLE·LRU |
| 深度思考碎碎念 | IDLE·LRU、THINKING |
| 照镜子 | IDLE·LRU、THINKING |
| 玩水枪 | IDLE·LRU、WORKING |
| 玩游戏气急败坏 | ERROR、IDLE·LRU、TASK、WORKING |
| 用鲸鱼尾巴拍打地面 | ERROR、IDLE·LRU |
| 穿针乞巧 | IDLE·LRU |
| 舞狮头 | IDLE·LRU |
| 荡秋千 | IDLE·LRU |
| 萌化小幽灵 | IDLE·LRU |
| 蓝鲸现世 | IDLE·LRU |
| 蝴蝶蜜蜂环绕头顶开花 | IDLE·LRU |
| 被吓一跳 | ERROR、IDLE·LRU |
| 被落叶淹没 | IDLE·LRU |
| 装点圣诞树 | IDLE·LRU |
| 讨糖南瓜灯 | IDLE·LRU |
| 超大伸懒腰 | IDLE、IDLE·LRU、WAITING |
| 踢毽子 | IDLE·LRU |
| 轻快摇摆舞 | IDLE、IDLE·LRU |
| 轻快记录 | IDLE、IDLE·LRU、TASK、THINKING |
| 骑木马 | IDLE·LRU |
| 鲸鱼吐泡泡特效 | IDLE·LRU |

### turn（1）

| 动画 | 触发场景 |
|---|---|
| 东张西望 | IDLE |

## 5. 调度与互斥规则

- 高优先级状态可打断低优先级状态；低优先级不抢占正在播放的高优先级动画。
- 正在拖拽时禁止任何自动切换（保护鼠标交互）。
- 同一状态至少保持 2.8 秒，之后才允许切换到备选动画。
- 同一状态重复出现时，默认池与切换池交替选择。
- 选择器采用“最近最少使用（LRU）+ 使用次数 + 最近 2 个排除”策略，避免单一动画抢占。
- IDLE 池包含全部 91 个动画，按 LRU 轮播，因此每个动画均至少有一个触发场景，覆盖率 100%。
- CLICK / DRAG 动画仅由鼠标交互触发，不进入自动抢占。

## 6. 补充触发建议

- 未来可增加节假日/时间场景（例如春节播放“收红包”、中秋播放“中秋赏月吃月饼”）。
- 任务类型细分为“写代码 / 搜索 / 测试 / 命令”时，可把对应动作加入 WORKING 池。
- 长时间无任务时，可提高进食/才艺/节庆类动画的出现权重。
