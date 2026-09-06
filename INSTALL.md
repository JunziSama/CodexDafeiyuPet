# 安装 / 配置 / 回滚

## 一键安装（当前电脑）

```powershell
# 1. 同步插件文件
node "$env:USERPROFILE\.dsh\projects\dsh-pet-indesktop\scripts\install-local.mjs"

# 2. 安装 Python 依赖（首次）
py -3 -m pip install -r "$env:USERPROFILE\.dsh\projects\dsh-pet-indesktop\requirements.txt"

# 3. 重启 dsh，刷新 EAC 页面
```

安装后进入 EAC 设置页 →「独立桌宠」：

- `+ 创建新卡片`：新增一个独立桌宠卡片。
- 卡片勾选框：显示 / 隐藏该卡片对应的桌面宠物。
- `移除`：删除该卡片并关闭对应宠物。
- 分区顶部开关：整体启用 / 停用该插件，不影响 `dsh-dafeiyu` 和 `dsh-pet`。

## 回滚

```powershell
# 1. 停用或移除 patch 行
#    %USERPROFILE%\.dsh\profiles\web-desktop\cordis.patch.yml
#    将 pet-indesktop 条目删除或设置 disabled: true

# 2. 删除已安装插件目录
Remove-Item -Recurse -Force "$env:USERPROFILE\.dsh\profiles\web-desktop\node_modules\dsh-pet-indesktop"

# 3. 重启 dsh
```

可选：删除运行配置目录 `%APPDATA%\dsh-pet-eac`。
